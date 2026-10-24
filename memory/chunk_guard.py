"""Review-gated small-edit sessions for AutoEngineer/Zoo Code.

This helper snapshots *explicit* source paths into ignored .local state and
verifies their net edits before releasing ownership. It never edits those
source files, stages Git, calls models, or touches Factorio. It is opt-in;
Zoo/VS Code must invoke it for every scoped chunk for enforcement to apply.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from code_quality_gate import (
    check_backend,
    check_structured_files,
    check_syntax,
    is_sensitive_path,
    run_quick,
)

MAX_FILES = 2  # Standard/local agent default
MAX_CHANGED_LINES = 200
MINIMAX_MAX_FILES = 3
MINIMAX_MAX_CHANGED_LINES = 400
PROFILES = ("standard", "minimax")
MAX_FILE_BYTES = 250_000
SAFE_PATH = re.compile(r"^[a-zA-Z0-9_./-]{1,200}$")
TEST_NAME = re.compile(r"^test_[a-z0-9_]+\.py$")
SESSION_NAME = re.compile(r"^[a-f0-9]{32}$")
CODE_EXTENSIONS = (".py", ".cs", ".patch")
BACKEND_EXTENSIONS = (".cs", ".patch")


class ChunkError(ValueError):
    """Invalid plan, overlapping work, or failed verification."""


def safe_file(root: Path, name: str) -> Path:
    """Allow only ordinary, explicitly scoped project paths."""
    if (not isinstance(name, str) or not SAFE_PATH.fullmatch(name)
            or name.startswith("/") or ".." in name.split("/")
            or "//" in name or name.startswith((".git/", ".local/"))
            or name.endswith("/") or name in (".git", ".local")):
        raise ChunkError(f"Invalid project-relative path: {name!r}")
    p = root / name
    if not p.resolve().is_relative_to(root.resolve()) or p.is_symlink():
        raise ChunkError(f"Refusing escape or symbolic link: {name}")
    if not any(name.startswith(prefix) for prefix in
               ("agent/", "tests/", "memory/", "docs/", "backend-safety/",
                "handoff/", ".roo/", ".vscode/", "factorio-mod/")):
        raise ChunkError(f"Path outside permitted source folders: {name}")
    if is_sensitive_path(name):
        raise ChunkError("Cannot snapshot credentials")
    if p.exists() and (not p.is_file() or p.stat().st_size > MAX_FILE_BYTES):
        raise ChunkError(f"Non-file or oversized file: {name}")
    return p


def sessions_root(root: Path) -> Path:
    return root / ".local" / "chunk-checkpoints"


def manifest_file(root: Path, session: str) -> Path:
    if not SESSION_NAME.fullmatch(session):
        raise ChunkError("Invalid chunk session identifier")
    p = sessions_root(root) / session / "manifest.json"
    if not p.is_file():
        raise ChunkError("Unknown chunk session")
    return p


def update_manifest(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def lock_path(root: Path, name: str) -> Path:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return sessions_root(root) / "locks" / (digest + ".lock")


def acquire_lock(path: Path, session: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(session + "\n")
    except FileExistsError as exc:
        raise ChunkError("Another chunk owns a planned file; review before aborting it") from exc


def release_locks(root: Path, names: list[str], session: str) -> None:
    for name in names:
        p = lock_path(root, name)
        if p.is_file() and p.read_text(encoding="utf-8").strip() == session:
            p.unlink()


def sensitive_chunk_file(name: str) -> bool:
    """Keep backend, game-control and guard/policy edits on the smaller budget."""
    if (name.startswith(("backend-safety/", ".roo/rules/")) or name in (
        "memory/chunk_guard.py", "memory/code_quality_gate.py",
        "docs/ZOO_CODE_TASK_PROTOCOL.md",
    ) or (name.startswith("factorio-mod/") and name.endswith("/control.lua"))):
        return True
    if name.startswith("agent/"):
        stem = Path(name).stem.lower()
        return bool(set(re.split(r"[_-]", stem)) & {
            "rcon", "policy", "approval", "stop", "lease", "dispatch",
            "movement", "auth", "authorization", "safety", "guard",
            "supervision", "supervisor", "execution", "control",
        })
    return False


def chunk_limits(names: list[str], profile: str) -> tuple[int, int]:
    if profile not in PROFILES:
        raise ChunkError(f"Unknown chunk profile {profile!r}")
    if profile == "minimax" and not any(sensitive_chunk_file(n) for n in names):
        return MINIMAX_MAX_FILES, MINIMAX_MAX_CHANGED_LINES
    return MAX_FILES, MAX_CHANGED_LINES


def begin_chunk(root: Path, names: list[str], label: str, *,
                profile: str = "standard") -> str:
    file_cap, line_cap = chunk_limits(names, profile)
    if not 1 <= len(names) <= file_cap or len(set(names)) != len(names):
        raise ChunkError(f"Each {profile} chunk must name 1-{file_cap} distinct files")
    if not isinstance(label, str) or not (5 <= len(label.strip()) <= 120):
        raise ChunkError("Provide a brief concrete chunk goal (5-120 characters)")
    paths = [safe_file(root, name) for name in names]
    store = sessions_root(root)
    session = uuid.uuid4().hex
    dest = store / session
    dest.mkdir(parents=True, exist_ok=False)
    acquired: list[str] = []
    try:
        for name in names:
            acquire_lock(lock_path(root, name), session)
            acquired.append(name)
        records = []
        for i, (name, p) in enumerate(zip(names, paths)):
            raw = p.read_bytes() if p.is_file() else b""
            if b"\x00" in raw:
                raise ChunkError("Binary file cannot be edited through text chunk guard")
            raw.decode("utf-8", errors="strict")
            (dest / f"before-{i}.txt").write_bytes(raw)
            records.append({"name": name, "existed": p.is_file(),
                            "sha256": hashlib.sha256(raw).hexdigest()})
        update_manifest(dest / "manifest.json", {
            "schema": 1, "session": session, "goal": label.strip(),
            "status": "active", "files": records, "profile": profile,
            "limits": {"max_files": file_cap, "max_changed_lines": line_cap},
        })
    except (OSError, UnicodeError, ValueError):
        release_locks(root, acquired, session)
        raise
    return session


def diff_line_count(before: str, after: str) -> int:
    matcher = difflib.SequenceMatcher(None, before.splitlines(), after.splitlines(),
                                      autojunk=False)
    # Count additions and deletions; replacements count both sides.
    return sum((a1 - a0) + (b1 - b0)
               for tag, a0, a1, b0, b1 in matcher.get_opcodes() if tag != "equal")


def measure_chunk(root: Path, session: str) -> tuple[list[str], int, list[str], dict, Path]:
    mf = manifest_file(root, session)
    m = json.loads(mf.read_text(encoding="utf-8"))
    if m.get("status") != "active" or m.get("session") != session:
        raise ChunkError("Chunk is already complete or aborted")
    changed: list[str] = []
    total = 0
    for i, rec in enumerate(m["files"]):
        name = rec["name"]
        p = safe_file(root, name)
        before = (mf.parent / f"before-{i}.txt").read_text(encoding="utf-8")
        if not p.is_file():
            raise ChunkError(f"Planned file was deleted: {name}; reconcile manually")
        after = p.read_text(encoding="utf-8")
        diff = diff_line_count(before, after)
        total += diff
        if diff:
            changed.append(name)
        if lock_path(root, name).read_text(encoding="utf-8").strip() != session:
            raise ChunkError("Lost edit ownership; another task may have intervened")
    return changed, total, [rec["name"] for rec in m["files"]], m, mf


def run_checks(root: Path, *, test_file: str | None, test_stage: str | None,
               upstream: Path | None, changed: list[str]) -> list[tuple[str, bool, str]]:
    checks = []
    for result in (check_syntax(root, changed), check_structured_files(root, changed),
                   *run_quick(root)):
        checks.append((result.name, result.ok, result.detail))
    has_backend = any(x.endswith(BACKEND_EXTENSIONS) for x in changed)
    has_python = any(x.endswith(".py") for x in changed)
    if has_backend:
        if upstream is None:
            checks.append(("Backend build", False, "C# or patch edit requires clean pinned --upstream"))
        else:
            for result in check_backend(root, upstream.resolve(), build=True):
                checks.append((result.name, result.ok, result.detail))
    if has_python and not (test_file or test_stage):
        checks.append(("Focused regression", False, "Python edit requires --test-file or --test-stage"))
    if test_file or test_stage:
        if test_file:
            if (not TEST_NAME.fullmatch(test_file)
                    or not (root / "tests" / test_file).is_file()):
                raise ChunkError("Targeted test filename must be an existing tests/test_*.py file")
            pattern = test_file
        else:
            patterns = {
                "offline": "test_*.py",
                "dashboard": "test_dashboard_*.py",
                "safety": "test_mode_policy.py",
                "reality": "test_factory_*.py",
            }
            if test_stage not in patterns:
                raise ChunkError(
                    "Unsupported QA stage in this checkout; use --test-file or one of "
                    "offline/dashboard/safety/reality"
                )
            pattern = patterns[test_stage]
        if not list((root / "tests").glob(pattern)):
            checks.append(("Targeted tests", False,
                           f"No tests matching {pattern!r} in this checkout"))
        else:
            argv = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests",
                    "-p", pattern, "-q"]
            try:
                proc = subprocess.run(argv, cwd=root, timeout=180, check=False,
                                      capture_output=True, text=True, encoding="utf-8", errors="replace")
                detail = ((proc.stdout + "\n" + proc.stderr).strip())[-1600:]
                checks.append(("Targeted tests", proc.returncode == 0, detail))
            except (OSError, subprocess.TimeoutExpired) as exc:
                checks.append(("Targeted tests", False, type(exc).__name__))
    return checks


def verify_chunk(root: Path, session: str, *, test_file: str | None = None,
                 test_stage: str | None = None, upstream: Path | None = None) -> tuple[bool, str]:
    if test_file and test_stage:
        raise ChunkError("Select exactly one of --test-file and --test-stage")
    changed, total, names, manifest, mf = measure_chunk(root, session)
    profile = manifest.get("profile", "standard")  # Existing sessions retain standard limits.
    file_cap, line_cap = chunk_limits(names, profile)
    recorded = manifest.get("limits", {})
    if (type(recorded.get("max_files")) is not int
            or type(recorded.get("max_changed_lines")) is not int
            or recorded["max_files"] < 1 or recorded["max_changed_lines"] < 1):
        raise ChunkError("Invalid recorded chunk limits")
    file_cap = min(file_cap, recorded["max_files"])
    line_cap = min(line_cap, recorded["max_changed_lines"])
    if len(names) > file_cap:
        return False, f"BLOCKED: {len(names)} files exceeds {file_cap} for {profile}"
    if not changed:
        return False, "BLOCKED: no changes in this chunk; do not claim work is complete"
    if total > line_cap:
        return False, (f"BLOCKED: {total} changed lines exceeds {line_cap}. "
                       "Stop, checkpoint and split into smaller tasks.")
    checks = run_checks(root, test_file=test_file, test_stage=test_stage,
                        upstream=upstream, changed=changed)
    lines = [f"CHUNK {session} | profile={profile} | changed={len(changed)}/{file_cap} | lines={total}/{line_cap}"]
    lines += [f"{'PASS' if ok else 'FAIL'} {name}: {detail}" for name, ok, detail in checks]
    success = all(ok for _, ok, _ in checks)
    if success:
        manifest["status"] = "verified"
        manifest["actual_files"] = changed
        manifest["changed_lines"] = total
        manifest["verification"] = [{"check": label, "status": "PASS"} for label, _, _ in checks]
        update_manifest(mf, manifest)
        release_locks(root, names, session)
        lines.append("CHUNK VERIFIED: ready to checkpoint before next chunk")
    else:
        lines.append("CHUNK FAILED: keep same scope; fix and retry. No next chunk.")
    return success, "\n".join(lines)


def abort_chunk(root: Path, session: str, reason: str) -> None:
    if not isinstance(reason, str) or len(reason.strip()) < 8:
        raise ChunkError("Provide a concrete reason; preserve a checkpoint before aborting")
    mf = manifest_file(root, session)
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    if manifest["status"] != "active":
        raise ChunkError("Only active sessions can be aborted")
    manifest["status"] = "aborted"
    manifest["abort_reason"] = reason.strip()[:200]
    update_manifest(mf, manifest)
    release_locks(root, [x["name"] for x in manifest["files"]], session)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    task = parser.add_mutually_exclusive_group(required=True)
    task.add_argument("--begin", action="store_true")
    task.add_argument("--verify", metavar="CHUNK_ID")
    task.add_argument("--abort", metavar="CHUNK_ID")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--label")
    parser.add_argument("--profile", choices=PROFILES, default="standard",
                        help="Opt-in larger MiniMax budget; default is standard/local")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--test-file")
    parser.add_argument("--test-stage")
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--reason")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "agent").is_dir() or not (root / "memory" / "chunk_guard.py").is_file():
        parser.error("Expected AutoEngineer source workspace and chunk guard")
    try:
        if args.begin:
            session = begin_chunk(root, args.file, args.label, profile=args.profile)
            file_cap, line_cap = chunk_limits(args.file, args.profile)
            print("CHUNK STARTED:", session)
            print(f"Profile: {args.profile}; max {file_cap} named files, "
                  f"{line_cap} changed lines; verification required")
        elif args.verify:
            ok, report = verify_chunk(root, args.verify, test_file=args.test_file,
                                      test_stage=args.test_stage, upstream=args.upstream)
            print(report)
            return 0 if ok else 1
        else:
            abort_chunk(root, args.abort, args.reason)
            print("CHUNK ABORTED: changes preserved; record checkpoint before continuing")
    except (ChunkError, OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        print("CHUNK BLOCKED:", str(exc)[:350])
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
