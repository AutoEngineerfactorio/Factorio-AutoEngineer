"""R07-A helper: size a pending edit against the chunk-guard baseline.

Not part of the agent package. Used only to measure how many changed lines a
planned edit will cost before the chunk guard blocks it.

Usage::

    python -B memory/r07_chunk_sizer.py <chunk-session-id> <project-relative-path>
"""
from __future__ import annotations

import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def diff_lines(before: str, after: str) -> int:
    matcher = difflib.SequenceMatcher(
        None, before.splitlines(), after.splitlines(), autojunk=False
    )
    return sum(
        (a1 - a0) + (b1 - b0)
        for tag, a0, a1, b0, b1 in matcher.get_opcodes()
        if tag != "equal"
    )


def snapshot(session: str, index: int = 0) -> str:
    path = ROOT / ".local" / "chunk-checkpoints" / session / f"before-{index}.txt"
    return path.read_text(encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: r07_chunk_sizer.py <chunk-session-id> <project-relative-path>")
        return 2
    session, target = argv[1], argv[2]
    before = snapshot(session)
    after = (ROOT / target).read_text(encoding="utf-8")
    print(f"{target} vs {session}: {diff_lines(before, after)} changed lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
