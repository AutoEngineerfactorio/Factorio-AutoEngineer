"""Summarise a live R06 run report without dumping the whole payload.

The report contains the catalog rows, so only the measured counters and a
bounded sample of the rows are printed.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"

COUNTERS = (
    "run_tag",
    "backend_mode",
    "server_reused",
    "client_joined",
    "client_join_waited_seconds",
    "player_ready",
    "save_unchanged",
    "server_left_running",
    "catalog_status",
    "catalog_total_count",
    "catalog_total_pages",
    "catalog_rows",
    "catalog_unique_names",
    "catalog_pages_read",
    "catalog_paging_errors",
    "catalog_globally_sorted",
    "catalog_single_tick",
    "view_game_version",
    "view_enabled_content_count",
    "research_observed",
    "source_fingerprint",
    "craft_executed",
    "craft_skipped_reason",
    "backend_mode_reason",
)


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    path = EVIDENCE / (f"{tag}.json" if tag else "")
    if not path.is_file():
        print(f"REPORT_MISSING {path}")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"REPORT={path.name}")
    for key in COUNTERS:
        if key in data:
            print(f"  {key}={data[key]}")
    for key, value in sorted(data.items()):
        if key in COUNTERS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            print(f"  {key}={value}")
        elif isinstance(value, list):
            print(f"  {key}=list(len={len(value)})")
        elif isinstance(value, dict):
            print(f"  {key}=dict(keys={sorted(value)[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
