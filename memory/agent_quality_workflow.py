"""Agent coding-chunk workflow: baseline and verified final checks.

Run 'begin' before code changes and 'finish' after VS Code refreshes diagnostics.
No code is staged, committed, executed in Factorio, or pushed by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".local" / "vscode-problems-baseline.json"
REPORT = ROOT / ".local" / "agent-quality-report.json"
FILE_BASELINE = ROOT / ".local" / "coding-files-baseline.json"


def file_digests(root=ROOT):
    """Fingerprint code and regression tests, excluding ignored/private files."""
    cmd = subprocess.run(["git", "ls-files", "--cached", "--others",
                          "--exclude-standard", "-z"], cwd=root,
                         capture_output=True, check=False)
    if cmd.returncode:
        raise ValueError("Unable to enumerate changed code")
    output = {}
    for raw in cmd.stdout.split(b"\0"):
        if not raw:
            continue
        name = raw.decode("utf-8", errors="replace").replace("\\", "/")
        if not name.startswith(("agent/", "backend-safety/", "factorio-mod/", "tests/")):
            continue
        if not name.endswith((".py", ".cs", ".lua")):
            continue
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        output[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return output


def regression_check(before, after):
    changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    source = {p for p in changed if p.startswith(("agent/", "backend-safety/", "factorio-mod/"))}
    tests = {p for p in changed if p.startswith("tests/test_") and p.endswith(".py")}
    return not source or bool(tests), len(source), len(tests)


def run(argv):
    return subprocess.run(argv, cwd=ROOT, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("begin", "finish"))
    args = parser.parse_args()
    if args.stage == "begin":
        result = run([sys.executable, "-B", "memory/vscode_problems_gate.py", "baseline"])
        if result.returncode:
            print("BLOCKED: VS Code Problems baseline unavailable")
            return result.returncode
        FILE_BASELINE.parent.mkdir(parents=True, exist_ok=True)
        FILE_BASELINE.write_text(json.dumps(file_digests(), indent=2), encoding="utf-8")
        return 0
    if not BASELINE.is_file() or not FILE_BASELINE.is_file():
        print("BLOCKED: Begin the coding chunk before editing")
        return 2
    try:
        accepted, code_files, test_files = regression_check(
            json.loads(FILE_BASELINE.read_text(encoding="utf-8")), file_digests())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"BLOCKED: Invalid coding file baseline: {exc}")
        return 2
    if not accepted:
        print(f"BLOCKED: {code_files} source files changed without a changed regression test")
    checks = [
        [sys.executable, "-B", "memory/layered_quality.py", "--typing",
         "--json-output", ".local/layered-quality-result.json"],
        [sys.executable, "-B", "memory/code_quality_gate.py", "--stage", "quick",
         "--problems-check"],
    ]
    codes = [run(argv).returncode for argv in checks]
    report = {"stage": "finish", "passed": accepted and all(c == 0 for c in codes),
              "exit_codes": codes, "regression_tests_changed": test_files,
              "code_files_changed": code_files}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("AGENT QUALITY:", "PASS" if report["passed"] else "BLOCKED")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
