"""Report the raw JSON type of a live row's unlock_technologies field.

The row dump is written with ``default=list``, so a non-serializable value
is turned into a list on the way out. This probe reads the dump's raw text
and reports the exact JSON token that follows the key, so the field's real
shape is known.

Read-only: it reads the persisted live row dump.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else "r06-final-int-b"
    path = EVIDENCE / f"{tag}-catalog-rows.json"
    if not path.is_file():
        print(f"ROWS_MISSING {path}")
        return 1
    text = path.read_text(encoding="utf-8")
    marker = '"unlock_technologies"'
    index = text.find(marker)
    if index < 0:
        print("MARKER_NOT_FOUND")
        return 1
    # Show the raw text right after the key, so the JSON type is visible.
    print("RAW_AFTER_KEY=" + repr(text[index:index + 260]))

    data = json.loads(text)
    types: dict[str, int] = {}
    for name, row in data.items():
        kind = type(row.get("unlock_technologies")).__name__
        types[kind] = types.get(kind, 0) + 1
    print(f"JSON_TYPES={types}")
    # A representative row.
    for name in sorted(data)[:3]:
        print(f"  {name}: {json.dumps(data[name].get('unlock_technologies'))[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
