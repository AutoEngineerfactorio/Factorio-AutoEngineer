"""Layered, read-only coding verification for AutoEngineer.

Each gate reports PASS, FAIL, or BLOCKED. Never install tools implicitly.
Run from workspace root: python -B memory/layered_quality.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def luals_executable():
    """Find installed LuaLS, including VS Code's bundled Windows binary."""
    installed = shutil.which("lua-language-server")
    if installed:
        return installed
    root = Path.home() / ".vscode" / "extensions"
    candidates = sorted(root.glob("sumneko.lua-*/server/bin/lua-language-server.exe"),
                        reverse=True)
    return str(candidates[0]) if candidates else "lua-language-server"


def command(label, argv, *, timeout=180, required=True):
    if not shutil.which(argv[0]) and not Path(argv[0]).is_file():
        return label, "BLOCKED" if required else "SKIP", f"{argv[0]} unavailable"
    try:
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return label, "BLOCKED", str(exc)[:200]
    output = (result.stdout + "\n" + result.stderr).strip()
    return label, "PASS" if result.returncode == 0 else "FAIL", output[-1200:]


def run_checks(*, problems=True, typing=False, tests=True,
               lua=False, backend=None, live=False):
    checks = [
        ("Ruff", ["ruff", "check", "agent", "tests", "memory"], 90, True),
        ("Patch whitespace", ["git", "diff", "--check"], 40, True),
    ]
    if tests:
        checks.append(("Unit tests", [sys.executable, "-B", "-m", "unittest",
                                       "discover", "-s", "tests", "-q"], 240, True))
    if typing:
        # CLI Pyright is supplementary to the VS Code Problems bridge. Never
        # silently ignore it if requested and unavailable.
        checks.append(("Pyright", ["pyright", "--outputjson"], 180, True))
    if problems:
        checks.append(("VS Code Problems", [sys.executable, "-B",
                       "memory/vscode_problems_gate.py", "check"], 30, True))
    if lua:
        config = ROOT / "tests" / "lua_diagnostics_probe.lua"
        mod = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
        log = ROOT / ".local" / "lua-check-log"
        checks.append(("Factorio LuaLS", [luals_executable(), f"--check={mod}",
                       f"--configpath={config}", f"--logpath={log}",
                       "--checklevel=Warning", "--check_format=pretty"], 180, True))
    if backend is not None:
        checks.append(("Isolated .NET backend", [sys.executable, "-B",
                       "memory/code_quality_gate.py", "--stage", "backend-build",
                       "--upstream", str(backend)], 240, True))
    if live:
        checks.append(("Read-only Factorio smoke", [sys.executable, "-B",
                       "tests/live_r08d_map_probe.py"], 180, True))
    return [command(name, args, timeout=timeout, required=required)
            for name, args, timeout, required in checks]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-problems", action="store_true",
                        help="Only for initial bootstrap, never final acceptance")
    parser.add_argument("--typing", action="store_true",
                        help="Include project-wide Pyright CLI check")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--lua", action="store_true",
                        help="Require Factorio 2.1.23 LuaLS diagnostics")
    parser.add_argument("--backend-upstream", type=Path,
                        help="Build isolated pinned backend from this clean source checkout")
    parser.add_argument("--live", action="store_true",
                        help="Explicit opt-in read-only Factorio 2.1.23 smoke test")
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    results = run_checks(problems=not args.skip_problems, typing=args.typing,
                         tests=not args.skip_tests, lua=args.lua,
                         backend=args.backend_upstream, live=args.live)
    for label, status, info in results:
        line = f"{status}: {label}\n{info[:600]}"
        print(line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace"))
    report = {"results": [{"name": name, "status": status, "detail": detail}
                          for name, status, detail in results],
              "passed": all(status == "PASS" for _, status, _ in results)}
    if args.json_output:
        path = args.json_output.resolve()
        if not path.is_relative_to((ROOT / ".local").resolve()):
            parser.error("--json-output must be within ignored .local/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("LAYERED QUALITY:", "PASS" if report["passed"] else "NOT PASSED")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
