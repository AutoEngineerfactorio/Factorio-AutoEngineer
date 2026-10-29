"""Regenerate the ``RconConnectionService.cs`` section of the shared patch.

``backend-safety/backend-safety.patch`` is a **combined integration artifact**
shared with the telemetry owner. Only one section may be rewritten at a time,
and every other section must stay byte-identical.

``tests/synthesize_backend_patch.py`` owns the sections that create a **new**
file. ``FactorioMCP/Services/RconConnectionService.cs`` already exists in the
pinned upstream tree, so its section is a **modification** diff. This script
regenerates exactly that one section, from the pinned upstream file and the
readable source in ``backend-safety/``, and leaves every other section
untouched.

Usage:
    python -B tests/synthesize_rcon_service_patch.py [--upstream PATH]
"""

from __future__ import annotations

import argparse
import difflib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
SOURCE = ROOT / "backend-safety" / "RconConnectionService.cs"
TARGET = "FactorioMCP/Services/RconConnectionService.cs"
DEFAULT_UPSTREAM = Path(r"D:\AI\Factorio-AutoEngineer\FactorioMCP")


def split_sections(patch_text: str) -> list[tuple[str, str]]:
    """Split a combined patch into ``(target path, section text)`` pairs.

    The patch uses plain ``--- a/`` / ``+++ b/`` headers without ``diff --git``
    lines, so a section is delimited by its ``+++ b/`` header and runs up to
    the next section's ``--- a/`` header.
    """
    lines = patch_text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("--- ")]
    sections: list[tuple[str, str]] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        chunk = lines[start:end]
        target = None
        for line in chunk:
            if line.startswith("+++ b/"):
                target = line[len("+++ b/"):].rstrip("\n")
                break
        if target is not None:
            sections.append((target, "".join(chunk)))
    return sections


def upstream_text(upstream: Path) -> str:
    """Return the pinned upstream file's text.

    The file is read from the upstream **worktree**, not with ``git show``,
    because the worktree is what the patch is applied to and it carries the
    **CRLF** line endings that the patch's context lines must match.
    """
    target = upstream / TARGET
    if not target.is_file():
        raise SystemExit(f"the pinned upstream file is missing: {target}")
    return normalize(target.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    """Return the text with **CRLF** line endings, preserving its content.

    The patch is applied to the upstream worktree, where the file carries
    **CRLF** line endings, so a diff whose context lines use LF does not match
    that file. The content itself is **not** altered: stripping trailing
    whitespace from a line that the upstream also carries would turn an
    unchanged line into a removed-and-added pair, and the added empty line
    would then be reported as trailing whitespace by the quality gate.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\r\n".join(lines)


def build_section(before_text: str) -> str:
    """Return the unified diff that turns the baseline file into the source.

    The diff is computed on the **exact bytes** of both files, with their
    CRLF line endings preserved. A diff whose context lines use different
    line endings than the file the patch is applied to cannot be applied, and
    a tool that normalises the line endings makes an unchanged blank line
    look like a change.
    """
    before = before_text
    after = SOURCE.read_text(encoding="utf-8")
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="a/" + TARGET,
            tofile="b/" + TARGET,
            n=3,
        )
    )
    if not diff.strip():
        raise SystemExit("the readable source and the upstream file are identical")
    # The patch is stored with LF line endings, but the diff's **content**
    # keeps the CRLF that the upstream file uses, because the patch is
    # applied to that file. Each diff line therefore ends with CRLF in the
    # source text; only the line's own terminator is reduced to LF, which
    # leaves the content's CRLF intact.
    lines = diff.splitlines(keepends=True)
    reduced: list[str] = []
    for line in lines:
        if line.endswith("\r\n"):
            reduced.append(line[:-2] + "\n")
        elif line.endswith("\n"):
            reduced.append(line)
        else:
            reduced.append(line + "\n")
    return "".join(reduced)


def read_patch() -> str:
    """Return the shared patch's text with its LF line endings preserved.

    The shared patch is stored with **LF** line endings. Reading it with the
    default text mode would translate them to CRLF on this platform, and
    writing it back would then store CRLF. A patch whose context lines carry
    CRLF does not apply to the file it targets, so the patch is read and
    written without any newline translation.
    """
    with PATCH.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_patch(text: str) -> None:
    """Write the shared patch with **LF** line endings preserved."""
    with PATCH.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def capture_baseline(upstream: Path) -> str:
    """Return the file the **current** patch section produces.

    The baseline is obtained by applying the whole shared patch to a scratch
    clone of the pinned upstream tree and reading the resulting file. The
    shared patch is known to apply cleanly, so this is exact.
    """
    work = Path(tempfile.mkdtemp(prefix="r06-rcon-baseline-"))
    try:
        clone = work / "clone"
        cloned = subprocess.run(
            ["git", "clone", "--quiet", "--no-hardlinks", str(upstream),
             str(clone)],
            cwd=work, capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )
        if cloned.returncode != 0:
            raise SystemExit(f"the upstream clone failed: {cloned.stderr.strip()[:300]}")
        applied = subprocess.run(
            ["git", "apply", str(PATCH)],
            cwd=clone, capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )
        if applied.returncode != 0:
            raise SystemExit(
                "the shared patch did not apply to the pinned upstream, so the "
                f"baseline cannot be captured: {applied.stderr.strip()[:300]}"
            )
        target = clone / TARGET
        return target.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def rebuild(upstream: Path) -> int:
    """Rewrite only the RconConnectionService section of the shared patch."""
    patch_text = read_patch()
    sections = split_sections(patch_text)
    if not any(target == TARGET for target, _ in sections):
        raise SystemExit(f"the patch has no section for {TARGET}")

    baseline = upstream_text(upstream)
    new_section = build_section(baseline)

    rebuilt: list[str] = []
    for target, text in sections:
        rebuilt.append(new_section if target == TARGET else text)
    result = "".join(rebuilt)

    if result == patch_text:
        print("PATCH_ALREADY_CURRENT")
        print(f"PATCH_BYTES={len(patch_text)}")
        return 0

    write_patch(result)
    print("PATCH_SECTION_UPDATED")
    print(f"PATCH_BYTES={len(result)}")
    print(f"SECTION_BYTES={len(new_section)}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", default=str(DEFAULT_UPSTREAM))
    options = parser.parse_args(argv)
    upstream = Path(options.upstream)
    if not (upstream / ".git").exists():
        raise SystemExit(f"the upstream checkout is missing: {upstream}")
    return rebuild(upstream)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
