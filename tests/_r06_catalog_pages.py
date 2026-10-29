"""Inspect the page coverage of a live R06 run report.

The catalog is paged while the game clock runs, so a row that is
transiently unrepresentable on one tick is representable on another. This
check reports the measured page coverage and the distinct-page count so the
difference between two runs is explained rather than guessed.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    path = EVIDENCE / (f"{tag}.json" if tag else "")
    if not path.is_file():
        print(f"REPORT_MISSING {path}")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))

    total_pages = data.get("catalog_total_pages")
    rows = data.get("catalog_rows")
    print(f"total_pages={total_pages}")
    print(f"rows={rows}")
    if total_pages and rows:
        print(f"rows_per_page={rows / total_pages:.2f}")

    # Look for any page-oriented counters in the report.
    for key in sorted(data):
        if "page" in key.lower():
            value = data[key]
            if isinstance(value, (int, float, str, bool)) or value is None:
                print(f"{key}={value}")
            elif isinstance(value, list):
                print(f"{key}=list(len={len(value)})")
            else:
                print(f"{key}={type(value).__name__}")

    # The measured page latency proves how long the sweep took.
    for key in sorted(data):
        if "latency" in key.lower() or "elapsed" in key.lower() or "duration" in key.lower():
            print(f"{key}={data[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
