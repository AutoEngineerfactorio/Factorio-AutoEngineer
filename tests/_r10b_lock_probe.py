"""R10-B diagnostic: which chunk owns which file lock.

The chunk guard refuses a new chunk that touches a file another session
already owns. This diagnostic reports the owner so the work can be placed
in the right chunk instead of forcing a lock.

Temporary diagnostic; not part of the test suite.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / ".local" / "chunk-checkpoints"
TARGET = "observation_logistics.lua"


def main() -> int:
    """Report the owner of the mod file and of the active sessions."""
    import hashlib

    print("=== lock owners")
    locks = STORE / "locks"
    for name in ("factorio-mod/autoengineer-input_2.1.23/observation_logistics.lua",
                 "tests/test_r10b_mod_logistics.py",
                 "tests/live_r10b_inventory_acceptance.py"):
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        path = locks / (digest + ".lock")
        if path.is_file():
            print(f"  {name} -> {path.read_text(encoding='utf-8').strip()}")
        else:
            print(f"  {name} -> free")

    print("=== sessions that name the R10-B mod module")
    for path in sorted(STORE.glob("*/manifest.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        names = [entry.get("name", "") for entry in data.get("files", [])]
        if any(TARGET in name for name in names):
            print(f"  {data.get('session')} status={data.get('status')} "
                  f"files={[n for n in names if TARGET in n]}")

    print("=== active sessions")
    for path in sorted(STORE.glob("*/manifest.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("status") == "active":
            print(f"  {data.get('session')} {data.get('goal')}")
            for entry in data.get("files", []):
                print(f"      {entry.get('name')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
