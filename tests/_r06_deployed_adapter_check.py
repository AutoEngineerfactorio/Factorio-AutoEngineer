"""Compare the deployed backend DLL with the current adapter source.

The live catalog acceptance uses the deployed backend. This check proves the
deployed build carries the current adapter source, so a live observation
reflects the code in the repository.

It is a read-only check. It never starts or stops a process.
"""

from __future__ import annotations

import datetime
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEPLOYED = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23"
SOURCE = ROOT / "backend-safety" / "Tools" / "RecipeResearchAdapter.cs"


def main() -> int:
    dll = DEPLOYED / "FactorioMCP.dll"
    if not dll.is_file():
        print(f"DEPLOYED_MISSING {dll}")
        return 1
    if not SOURCE.is_file():
        print(f"SOURCE_MISSING {SOURCE}")
        return 1

    dll_time = dll.stat().st_mtime
    source_time = SOURCE.stat().st_mtime
    print(f"dll_mtime={dll_time}")
    print(f"source_mtime={source_time}")
    print(f"dll_date={datetime.datetime.fromtimestamp(dll_time).isoformat()}")
    print(f"source_date={datetime.datetime.fromtimestamp(source_time).isoformat()}")
    if source_time > dll_time:
        print("SOURCE_NEWER=True  the deployed build predates the adapter source")
    else:
        print("SOURCE_NEWER=False the deployed build is not older than the source")

    # The adapter's distinguishing marker: the accepted 2.1.23 fields.
    text = SOURCE.read_text(encoding="utf-8")
    for marker in (
        "ignored_by_productivity",
        "extra_count_fraction",
        "independent_probability",
        "shared_probability",
        "affected_by_quality",
        "amount_min",
        "amount_max",
        "percent_spoiled",
    ):
        print(f"adapter_has_{marker}={marker in text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
