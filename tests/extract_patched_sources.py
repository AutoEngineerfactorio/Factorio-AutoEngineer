"""Extract the patched upstream files from the isolated clone for exact comparison.

Applies the current combined patch to a fresh clone of the pinned upstream and
copies the resulting patched files into .local/patch-regen/patched/ so the
readable copies in backend-safety/ can be compared byte-for-byte.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
UPSTREAM = Path(r"D:\AI\Factorio-AutoEngineer\FactorioMCP")
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
WORK = ROOT / ".local" / ("patch-regen-" + str(os.getpid()))
CLONE = WORK / "FactorioMCP"
OUT = ROOT / ".local" / "patched-extract"

TARGETS = [
    "FactorioMCP/Services/RconConnectionService.cs",
    "FactorioMCP/Tools/AutoEngineerTools.cs",
    "FactorioMCP/Tools/SafetyTools.cs",
    "FactorioMCP/Tools/RecipeResearchAdapter.cs",
    "FactorioMCP/Services/OperationService.cs",
]


def run(argv, cwd):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    cloned = run(["git", "clone", "--quiet", "--no-hardlinks", str(UPSTREAM), str(CLONE)], ROOT)
    if cloned.returncode:
        print("CLONE_FAILED", cloned.stderr[-400:])
        return 3
    applied = run(["git", "apply", str(PATCH)], CLONE)
    print("APPLY_EXIT=" + str(applied.returncode))
    if applied.returncode:
        print(applied.stderr[-1200:])
        return 4
    OUT.mkdir(parents=True, exist_ok=True)
    for relative in TARGETS:
        source = CLONE / relative
        if not source.is_file():
            print("MISSING=" + relative)
            continue
        destination = OUT / Path(relative).name
        shutil.copy2(source, destination)
        print("EXTRACTED=" + relative + " -> " + str(destination))
    return 0


if __name__ == "__main__":
    sys.exit(main())
