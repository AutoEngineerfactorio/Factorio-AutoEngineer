"""Probe the live 2.1.23 runtime for the quality-multiplier tables.

Read-only. The live prototype exposes ``crafting_speed_quality_multiplier``
and ``module_slots_quality_bonus`` as tables. If the multiplier table holds
the quality-1 multiplier of 1.0, it does not reveal the base crafting speed;
this probe reports the observed contents so the planner's remaining speed gap
is characterised by evidence instead of assumption.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))

from launcher_services import Rcon  # noqa: E402

from tests.r06_console_executor import (  # noqa: E402
    ConsoleExecutor,
    new_marker,
)


def build_probe_command(marker: str) -> str:
    """Return a read-only probe of the observed multiplier tables."""
    safe = marker.replace("-", "")
    return (
        "/silent-command local ok, err = pcall(function() "
        f"local P='{safe}' "
        "local function say(k,v) rcon.print(P..':'..k..'='..tostring(v)) end "
        "local function get(o,k) local a,b=pcall(function() return o[k] end) "
        "if a then return b end return nil end "
        "local function dump(t) "
        "  local parts = {} "
        "  for k, v in pairs(t or {}) do "
        "    parts[#parts+1] = tostring(k)..'='..tostring(v) end "
        "  table.sort(parts) return table.concat(parts, ',') end "
        "for _, name in ipairs({'assembling-machine-1','stone-furnace',"
        "'electric-furnace','character','assembling-machine-3'}) do "
        "  local p = prototypes.entity[name] "
        "  if p ~= nil then "
        "    say(name..'.speed_qmult', dump(get(p,'crafting_speed_quality_multiplier'))) "
        "    say(name..'.slots_qbonus', dump(get(p,'module_slots_quality_bonus'))) "
        "    say(name..'.module_inv', tostring(get(p,'module_inventory_size'))) "
        "    say(name..'.type', tostring(get(p,'type'))) end end "
        "end) "
        f"if not ok then rcon.print('{safe}:error='..tostring(err)) end"
    )


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 27161
    secret = json.loads(
        (ROOT / ".local" / "live-pillow-2.1.23" / "rcon.secret.json")
        .read_text(encoding="utf-8-sig"))
    password = secret["rcon_password"]

    client = Rcon(port, password)
    executor = ConsoleExecutor(client.command)
    try:
        marker = new_marker()
        outcome = executor.execute(build_probe_command(marker), marker)
        print("EXECUTED:", outcome.executed)
        print("REASON:", outcome.reason)
        print("--- response ---")
        print(outcome.response)
        return 0 if outcome.executed else 1
    finally:
        try:
            client.sock.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    raise SystemExit(main())
