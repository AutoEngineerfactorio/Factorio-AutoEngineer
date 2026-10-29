"""Report the observed unlock-technology counts in the live catalog.

The read-only validator caps a recipe's unlock list at eight technologies.
A real Factorio 2.1.23 recipe can unlock more than eight at once, which
makes the validator reject a valid recipe. This probe measures the real
maximum from the observed live rows, so the bound is set from evidence
instead of from a guess.

Read-only: it reads the persisted live row dump.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "r06-final-int-b"
    path = EVIDENCE / f"{tag}-catalog-rows.json"
    if not path.is_file():
        print(f"ROWS_MISSING {path}")
        return 1
    rows = json.loads(path.read_text(encoding="utf-8"))

    counts: Counter[int] = Counter()
    over_eight: list[tuple[str, int]] = []
    missing = 0
    for name, row in rows.items():
        unlocks = row.get("unlock_technologies")
        if unlocks is None:
            missing += 1
            continue
        if not isinstance(unlocks, list):
            print(f"NOT_A_LIST {name}: {type(unlocks).__name__}")
            continue
        counts[len(unlocks)] += 1
        if len(unlocks) > 8:
            over_eight.append((name, len(unlocks)))

    print(f"rows={len(rows)}")
    print(f"rows_without_unlocks_key={missing}")
    print("UNLOCK COUNT DISTRIBUTION:")
    for size in sorted(counts):
        print(f"  {size} unlocks: {counts[size]} recipes")
    print(f"MAX_UNLOCKS={max(counts) if counts else 0}")
    print(f"RECIPES_OVER_EIGHT={len(over_eight)}")
    for name, size in sorted(over_eight, key=lambda pair: -pair[1])[:15]:
        print(f"  {name}: {size}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
