"""Small, fail-closed AutoEngineer coding quality gate for Zoo/VS Code.

Run from the project's isolated Python. Never modifies project source, installed
Factorio/backend, model settings, game saves, Git branches or staging state.
Backend mode uses a separate temporary source clone for optional .NET validation.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SECRET_PATH = re.compile(
    r"(?:^|/)(?:\.env(?:\.|$)|test-world(?:/|$)|\.local(?:/|$)|"
    r"launcher\.local\.json$|config\.local\.json$|rcon\.secret(?:\.|$)|"
    r"[^/]+\.(?:gguf|safetensors|key|pem)$)", re.I
)
MAX_STDOUT = 6000


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def is_sensitive_path(path: str) -> bool:
    """Detect files that must not accidentally be staged or sent to GitHub."""
    return bool(SECRET_PATH.search(path.replace("\\", "/")))


def decode_paths(raw: bytes) -> list[str]:
    """Git -z output supports spaces and Unicode without splitting paths."""
    return [item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item]


def run(argv: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout,
                          check=False, text=True, encoding="utf-8", errors="replace")


def short_output(result: subprocess.CompletedProcess) -> str:
    content = (result.stdout + "\n" + result.stderr).strip()
    return content[-MAX_STDOUT:] if content else f"exit={result.returncode}"


def changed_files(root: Path) -> tuple[list[str], list[str]]:
    """Only query Git; no resets, checkouts, stashes, index modifications."""
    all_files: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", "-z"],
        ["git", "diff", "--cached", "--name-only", "-z"],
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
    ):
        result = subprocess.run(args, cwd=root, capture_output=True,
                                timeout=15, check=False)
        if result.returncode:
            raise RuntimeError(f"Git file scan failed (exit {result.returncode})")
        all_files.update(decode_paths(result.stdout))
    staged = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"],
                            cwd=root, capture_output=True, timeout=15, check=False)
    if staged.returncode:
        raise RuntimeError("Unable to inspect staged files")
    return sorted(all_files), decode_paths(staged.stdout)


def check_syntax(root: Path, names: list[str]) -> Result:
    checked: list[str] = []
    errors: list[str] = []
    for name in names:
        if not name.endswith(".py"):
            continue
        resolved = (root / name).resolve()
        if not resolved.is_relative_to(root.resolve()):
            errors.append(f"Unsafe relative path: {name}")
            continue
        if not resolved.is_file():
            continue  # deleted files
        if resolved.stat().st_size > 2_000_000:
            errors.append(f"Python file is oversized: {name}")
            continue
        try:
            # Compile only; no import, no script execution, no bytecode files.
            compile(resolved.read_bytes(), name, "exec")
            checked.append(name)
        except (SyntaxError, UnicodeError, ValueError) as exc:
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:200]}")
    return Result("Python syntax", not errors,
                  "; ".join(errors) if errors else f"{len(checked)} changed .py files compile")


def check_structured_files(root: Path, names: list[str]) -> Result:
    """Validate changed JSON/Zoo mode files and reject zero-byte source patches."""
    checked = 0
    problems = []
    for name in names:
        relative = name.replace("\\", "/")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            problems.append(f"Unsafe path: {relative}")
            continue
        if not path.is_file() or is_sensitive_path(relative):
            continue
        if relative.endswith((".patch", ".patch.new", ".cs", ".py")) and path.stat().st_size == 0:
            problems.append(f"Empty source/patch file: {relative}")
        if relative.endswith(".json") or relative.endswith(".roomodes"):
            if path.stat().st_size > 2_000_000:
                problems.append(f"Oversized structured file: {relative}")
                continue
            try:
                json.loads(path.read_text(encoding="utf-8"))
                checked += 1
            except (ValueError, UnicodeError) as exc:
                problems.append(f"Bad JSON {relative}: {str(exc)[:130]}")
    return Result("JSON and empty patch sanity", not problems,
                  "; ".join(problems) if problems else f"{checked} structured files validated")


def run_quick(root: Path) -> list[Result]:
    results: list[Result] = []
    files, staged = changed_files(root)
    unsafe = [name for name in staged if is_sensitive_path(name)]
    results.append(Result("Staged private files", not unsafe,
                          "BLOCKED protected paths: " + ", ".join(unsafe)
                          if unsafe else "no protected filenames staged"))
    results.append(check_syntax(root, files))
    results.append(check_structured_files(root, files))
    diff = run(["git", "diff", "--check"], root)
    staged_diff = run(["git", "diff", "--cached", "--check"], root)
    results.append(Result("Whitespace and patch markers",
                          diff.returncode == 0 and staged_diff.returncode == 0,
                          "clean" if not diff.returncode and not staged_diff.returncode
                          else short_output(diff) + "; staged: " + short_output(staged_diff)))
    print(f"Changed/untracked visible paths: {len(files)}; staged paths: {len(staged)}")
    return results


def run_full(root: Path, python: Path) -> Result:
    runner = root / "memory" / "test_runner.py"
    if not runner.is_file():
        return Result("Full offline QA", False, "missing memory/test_runner.py")
    if not python.is_file():
        return Result("Full offline QA", False, "missing pinned .venv interpreter")
    result = run([str(python), "-B", str(runner), "--stage", "all-offline"],
                 root, timeout=300)
    return Result("Full offline QA", result.returncode == 0, short_output(result))


def check_backend(root: Path, upstream: Path, build: bool) -> list[Result]:
    baseline = root / "backend-safety" / "BASELINE.json"
    patch = root / "backend-safety" / "backend-safety.patch"
    if not upstream.is_dir() or not baseline.is_file() or not patch.is_file():
        return [Result("Pinned backend", False, "upstream/baseline/patch missing")]
    try:
        pinned = json.loads(baseline.read_text(encoding="utf-8"))["revision"]
    except (OSError, ValueError, KeyError):
        return [Result("Pinned backend", False, "baseline revision unreadable")]
    sha = run(["git", "rev-parse", "HEAD"], upstream)
    if sha.returncode or sha.stdout.strip() != pinned:
        return [Result("Pinned backend", False, "upstream HEAD differs from BASELINE.json")]
    status = run(["git", "status", "--porcelain"], upstream)
    if status.returncode or status.stdout.strip():
        return [Result("Pinned backend", False, "upstream is not clean; refusing patch test")]
    application = run(["git", "apply", "--check", str(patch)], upstream)
    results = [Result("Patch against pinned source", application.returncode == 0,
                      "applies cleanly" if application.returncode == 0
                      else short_output(application))]
    if application.returncode or not build:
        return results
    # Do not run dotnet in a live/vendor checkout. Clone into an isolated temp dir.
    with tempfile.TemporaryDirectory(prefix="ae-backend-qa-") as temp:
        destination = Path(temp) / "FactorioMCP"
        cloned = run(["git", "clone", "--quiet", "--no-hardlinks", str(upstream),
                      str(destination)], root, timeout=40)
        if cloned.returncode:
            return results + [Result("Isolated backend build", False, short_output(cloned))]
        applied = run(["git", "apply", str(patch)], destination)
        if applied.returncode:
            return results + [Result("Isolated backend build", False, short_output(applied))]
        project = destination / "FactorioMCP" / "FactorioMCP.csproj"
        if not project.is_file():
            return results + [Result("Isolated backend build", False, "project missing")]
        # Offline NuGet source prevents network fetches and unplanned dependency changes.
        empty_source = Path(temp) / "nuget-empty"
        empty_source.mkdir()
        restore = run(["dotnet", "restore", str(project), "--locked-mode", "--source",
                       str(empty_source), "--verbosity", "quiet"], destination, timeout=150)
        if restore.returncode:
            return results + [Result("Isolated backend build", False,
                                     "offline dependency restore unavailable: " + short_output(restore))]
        compile_result = run(["dotnet", "build", str(project), "-c", "Release",
                              "--no-restore", "--verbosity", "minimal"],
                             destination, timeout=180)
        return results + [Result("Isolated backend build", compile_result.returncode == 0,
                                 short_output(compile_result))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("quick", "full", "backend", "backend-build"),
                        default="quick")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--upstream", type=Path,
                        help="Required clean pinned FactorioMCP checkout for backend stages")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "agent").is_dir() or not (root / "backend-safety").is_dir():
        parser.error("Not a recognized Factorio AutoEngineer source workspace")
    try:
        results = run_quick(root)
        if args.stage == "full":
            python = root / ".venv" / "Scripts" / "python.exe"
            results.append(run_full(root, python))
        if args.stage.startswith("backend"):
            if args.upstream is None:
                parser.error("--upstream CLEAN_PINNED_FACTORIOMCP_DIR is required")
            results.extend(check_backend(root, args.upstream.resolve(),
                                         build=args.stage == "backend-build"))
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        results = [Result("Quality gate runtime", False,
                          f"{type(exc).__name__}: {str(exc)[:240]}")]
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        print(f"{marker} {result.name}: {result.detail}")
    print("CODE QUALITY GATE:", "PASS" if all(x.ok for x in results) else "FAIL")
    return 0 if all(x.ok for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
