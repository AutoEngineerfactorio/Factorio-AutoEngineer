"""Build the patched restricted backend into an isolated local directory.

Clones the pinned upstream, applies the combined backend-safety patch, and
builds Release offline. The result is written to .local/live-pillow-2.1.23/
backend-patched-2.1.23/ so the previously installed isolated backend stays
untouched and can be compared. The vendor checkout and the installed backend
are never modified.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
UPSTREAM = Path(r"D:\AI\Factorio-AutoEngineer\FactorioMCP")
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
WORK = ROOT / ".local" / "backend-build"
CLONE = WORK / "FactorioMCP"
OUT = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23"

# The only upstream project AutoEngineer builds and ships.
PRODUCT_PROJECT = Path("FactorioMCP") / "FactorioMCP.csproj"
# The pinned vendor tree also carries upstream-author scratch projects (for
# example TempInspect, which targets net10.0). A folder- or solution-wide
# restore inside the clone sweeps them in and the installed SDK fails with
# NETSDK1045. They are removed before any restore or build so only the
# product project is ever compiled.
SCRATCH_PROJECT_DIRS = ("TempInspect",)
TFM_PATTERN = re.compile(r"<TargetFramework>([^<]+)</TargetFramework>")


def run(argv, cwd, timeout=300):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          timeout=timeout)


def prune_scratch_projects(clone):
    """Delete upstream scratch projects from the isolated clone.

    Returns the removed directory names. Only the isolated clone is touched;
    the vendor checkout is never modified.
    """
    removed = []
    for name in SCRATCH_PROJECT_DIRS:
        target = clone / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            if not target.exists():
                removed.append(name)
    return removed


def target_frameworks(project):
    """Read the TargetFramework values declared by a project file."""
    try:
        text = project.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return []
    return TFM_PATTERN.findall(text)


def installed_sdk_max_tfm():
    """Return the highest TFM the installed .NET SDK can target, or None.

    The SDK compares a requested framework against NETCoreAppMaximumVersion,
    so the installed SDK version is the authoritative ceiling. The version is
    read from `dotnet --list-sdks` rather than a build to keep this offline.
    """
    listed = run(["dotnet", "--list-sdks"], ROOT, 60)
    versions = re.findall(r"(\d+)\.(\d+)\.(\d+)", listed.stdout)
    if not versions:
        return None
    best = max(tuple(int(part) for part in v) for v in versions)
    return f"net{best[0]}.{best[1]}"


def tfm_is_supported(tfm, max_tfm):
    """Compare a declared TFM against the SDK maximum without building."""
    if not max_tfm:
        return True

    def parts(value):
        match = re.match(r"net(\d+)\.(\d+)", value.strip())
        return (int(match.group(1)), int(match.group(2))) if match else None

    declared = parts(tfm)
    ceiling = parts(max_tfm)
    if declared is None or ceiling is None:
        return True
    return declared <= ceiling


def main():
    if not UPSTREAM.is_dir():
        print("MISSING_UPSTREAM")
        return 2
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    cloned = run(["git", "clone", "--quiet", "--no-hardlinks", str(UPSTREAM), str(CLONE)], ROOT, 120)
    if cloned.returncode:
        print("CLONE_FAILED", cloned.stderr[-600:])
        return 3
    head = run(["git", "rev-parse", "HEAD"], CLONE).stdout.strip()
    print("CLONE_HEAD=" + head)
    applied = run(["git", "apply", str(PATCH)], CLONE)
    print("APPLY_EXIT=" + str(applied.returncode))
    if applied.returncode:
        print(applied.stderr[-1500:])
        return 4
    project = CLONE / PRODUCT_PROJECT
    removed = prune_scratch_projects(CLONE)
    if removed:
        print("PRUNED_SCRATCH=" + ",".join(removed))
    if not project.is_file():
        print("MISSING_PRODUCT_PROJECT", str(project))
        return 7
    max_tfm = installed_sdk_max_tfm()
    print("SDK_MAX_TFM=" + str(max_tfm))
    declared = target_frameworks(project)
    for tfm in declared:
        if not tfm_is_supported(tfm, max_tfm):
            # Fail closed with a clear cause instead of an opaque NETSDK1045.
            print("UNSUPPORTED_TARGET_FRAMEWORK", tfm,
                  "installed SDK supports up to", max_tfm)
            return 8
    empty_source = WORK / "nuget-empty"
    empty_source.mkdir(exist_ok=True)
    restored = run(["dotnet", "restore", str(project), "--locked-mode", "--source",
                    str(empty_source), "--verbosity", "quiet"], CLONE, 200)
    print("RESTORE_EXIT=" + str(restored.returncode))
    if restored.returncode:
        print("RESTORE_FAILED", (restored.stdout + restored.stderr)[-800:])
        return 5
    built = run(["dotnet", "build", str(project), "-c", "Release", "--no-restore",
                 "--verbosity", "minimal"], CLONE, 300)
    print("BUILD_EXIT=" + str(built.returncode))
    print((built.stdout + built.stderr)[-1500:])
    if built.returncode:
        return 6
    produced = project.parent / "bin" / "Release" / (declared[0] if declared else "net9.0")
    if not produced.is_dir():
        print("MISSING_BUILD_OUTPUT", str(produced))
        return 9
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(produced, OUT)
    dll = OUT / "FactorioMCP.dll"
    print("OUTPUT_DLL=" + str(dll))
    print("OUTPUT_EXISTS=" + str(dll.is_file()))
    print("OUTPUT_BYTES=" + str(dll.stat().st_size if dll.is_file() else 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
