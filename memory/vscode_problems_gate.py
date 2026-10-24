"""Fail-closed VS Code Problems regression gate for Zoo/MiniMax coding chunks.

Usage:
  python -B memory/vscode_problems_gate.py baseline
  python -B memory/vscode_problems_gate.py check
The diagnostic file is owned by VS Code, not this script.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / ".zoo-diagnostics" / "vscode-problems.json"
BASELINE = ROOT / ".local" / "vscode-problems-baseline.json"
MAX_AGE_SECONDS = 180
MAX_ISSUES = 20000


def fingerprint(issue):
    return "|".join(str(issue.get(key, "")).strip() for key in
                    ("severity", "file", "source", "code", "message"))


def load_snapshot(path=SNAPSHOT, max_age=MAX_AGE_SECONDS):
    if not path.is_file():
        raise ValueError("VS Code Problems snapshot missing; bridge must be running")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("VS Code Problems snapshot unreadable") from exc
    if not isinstance(data, dict) or data.get("available") is not True:
        raise ValueError("VS Code diagnostics unavailable")
    if data.get("truncated") is not False:
        raise ValueError("VS Code Problems snapshot truncated or unknown")
    issues = data.get("issues")
    if not isinstance(issues, list) or len(issues) > MAX_ISSUES:
        raise ValueError("Invalid Problems issue list")
    for item in issues:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(k), str) for k in ("severity", "file", "message", "source")
        ):
            raise ValueError("Invalid diagnostic entry")
    errors = sum(i["severity"].lower() == "error" for i in issues)
    warnings = sum(i["severity"].lower() == "warning" for i in issues)
    if any(type(data.get(k)) is not int for k in ("errors", "warnings", "total", "shown")):
        raise ValueError("Invalid diagnostic counts")
    if (errors, warnings, len(issues)) != (
        data["errors"], data["warnings"], data["total"]
    ) or data["shown"] != len(issues):
        raise ValueError("Inconsistent diagnostic counts")
    from datetime import datetime, timezone
    try:
        updated = datetime.fromisoformat(data["updatedAt"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - updated).total_seconds()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid diagnostic timestamp") from exc
    if age < -30 or age > max_age:
        raise ValueError(f"VS Code Problems snapshot stale (age {age:.0f}s)")
    return data


def counts(data):
    return Counter(fingerprint(i) for i in data["issues"]
                   if i["severity"].lower() in ("error", "warning"))


def capture(path=BASELINE, source=SNAPSHOT):
    data = load_snapshot(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"captured_at": time.time(), "updatedAt": data["updatedAt"],
               "diagnostics": dict(counts(data)),
               "errors": data["errors"], "warnings": data["warnings"]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def check(path=BASELINE, source=SNAPSHOT):
    current = load_snapshot(source)
    if not path.is_file():
        raise ValueError("Problems baseline missing; run baseline before editing")
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Problems baseline unreadable") from exc
    if not isinstance(baseline, dict) or not isinstance(baseline.get("diagnostics"), dict):
        raise ValueError("Invalid Problems baseline")
    if baseline.get("updatedAt") == current["updatedAt"]:
        raise ValueError("VS Code has not published refreshed diagnostics since baseline")
    before = Counter(baseline["diagnostics"])
    after = counts(current)
    added = after - before
    return current, added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("baseline", "check"))
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    args = parser.parse_args()
    try:
        if args.action == "baseline":
            data = capture(args.baseline, args.snapshot)
            print(f"PROBLEMS BASELINE: {data['errors']} errors, {data['warnings']} warnings")
        else:
            data, added = check(args.baseline, args.snapshot)
            print(f"CURRENT PROBLEMS: {data['errors']} errors, {data['warnings']} warnings")
            for message, number in sorted(added.items()):
                print(f"NEW {number}x {message[:350]}")
            if added:
                print("PROBLEMS GATE: FAIL — new diagnostics detected")
                return 1
            print("PROBLEMS GATE: PASS — no new errors or warnings")
        return 0
    except ValueError as exc:
        print(f"PROBLEMS GATE: BLOCKED — {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
