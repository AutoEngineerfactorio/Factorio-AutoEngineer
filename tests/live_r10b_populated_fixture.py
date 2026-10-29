"""Populate a disposable full-Pyanodons test host with robot/rail inventory fixtures.

Extends the already reviewed 4,900-entity external community blueprint stress
with real creative roboports, chests, robots, rails and filled train wagons.
Only the freshly generated stress save is mutated. Live R10-B observers remain
read-only; an independent registered observation checks exact contents.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "agent"))

import live_blueprint_direct as direct  # noqa: E402
import live_r10b_observer_stress as stress  # noqa: E402
from live_long_stress import OUTPUT  # noqa: E402

SURFACE = "ae-r10b-populated-logistics"
NETWORKS = 8
CENTER_GAP = 160
MARKER = "AE_R10B_FIXTURE:"
OBSERVED = "AE_R10B_OBSERVED:"
ROWS_REQUIRED = 4


def _command(rcon, statement: str, marker: str = MARKER) -> dict:
    """Execute an explicitly confined creative action and parse its receipt."""
    answer = str(rcon.command("/c " + statement))
    found = re.search(re.escape(marker) + r"(\{.*\})", answer)
    if not found:
        raise RuntimeError("Missing creative command receipt: " + answer[:170])
    return json.loads(found.group(1))


def initialize(rcon, networks: int = NETWORKS) -> dict:
    """Create a unique surface, generate modest chunks and move the test player."""
    if not 1 <= networks <= NETWORKS:
        raise ValueError("Fixture network count must be between 1 and 8")
    statement = (
        "local p=game.connected_players[1];"
        "if not p or not p.character then error('No connected disposable player') end;"
        f"local s=game.surfaces['{SURFACE}'] or "
        f"game.create_surface('{SURFACE}',{{water=0}});"
        f"for i=0,{networks-1} do "
        f"s.request_to_generate_chunks({{100+i*{CENTER_GAP},0}},3) end;"
        "s.force_generate_chunk_requests();"
        "p.teleport({100,0},s);"
        "rcon.print('" + MARKER + "'..helpers.table_to_json({"
        "surface=s.name,networks_requested=" + str(networks) + ","
        "player_surface=p.surface.name}))"
    )
    result = _command(rcon, statement)
    if result.get("player_surface") != SURFACE:
        raise RuntimeError("Player did not enter isolated logistics fixture")
    return result


def construct_network(rcon, number: int) -> dict:
    """Place an independent roboport network, storage and several rail cars."""
    if not 0 <= number < NETWORKS:
        raise ValueError("Unknown fixture network")
    # Keep the packet size modest and generated coordinates deterministic.
    prefix = (
        f"local s=game.surfaces['{SURFACE}'];"
        "if not s then error('No disposable test surface') end;"
        "local f=game.connected_players[1].force;"
        f"local x={100+number*CENTER_GAP};"
        "local built={};"
        "local function add(n,dx,dy) "
        "local ok,e=pcall(function()return s.create_entity{"
        "name=n,position={x+dx,dy},force=f,"
        "direction=(n=='straight-rail' or n=='cargo-wagon' or "
        "n=='fluid-wagon') and defines.direction.east or nil}end);"
        "if ok and e and e.valid then "
        "built[n]=(built[n] or 0)+1;return e end end;"
    )
    power = (
        "local g=add('electric-energy-interface',0,0);"
        "if g then g.power_production=250000000;g.power_usage=0 end;"
        "add('substation',4,0);add('substation',4,10);"
        "local rb=add('roboport',9,1);add('roboport',9,14);"
        "local bots=0;"
        "if rb then local inv=rb.get_inventory(defines.inventory.roboport_robot);"
        "if inv then bots=bots+inv.insert{name='logistic-robot',count=40};"
        "bots=bots+inv.insert{name='construction-robot',count=25} end end;"
    )
    chests = (
        "local iron=0;local copper=0;"
        "for j=0,11 do "
        "local c=add('passive-provider-chest',18+j*3,1);"
        "if c then iron=iron+c.insert{name='iron-plate',count=400};"
        "copper=copper+c.insert{name='copper-plate',count=150} end end;"
        "for j=0,3 do add('storage-chest',18+j*3,6);"
        "add('requester-chest',18+j*3,-5) end;"
    )
    rails = (
        "local rail=0;"
        "for j=0,30 do "
        "if add('straight-rail',j*2,46) then rail=rail+1 end end;"
        "local cargo=0;local fluid=0;local wagons=0;"
        "for j=0,1 do "
        "local w=add('cargo-wagon',10+j*17,46);"
        "if w then wagons=wagons+1;"
        "cargo=cargo+w.insert{name='iron-plate',count=900} end end;"
        "local fw=add('fluid-wagon',47,46);"
        "if fw then wagons=wagons+1;"
        "local ok,v=pcall(function()return fw.insert_fluid{"
        "name='water',amount=15000}end);"
        "if ok then fluid=v or 0 end end;"
    )
    ending = (
        "rcon.print('" + MARKER + "'..helpers.table_to_json({"
        "index=" + str(number) + ",built=built,bots=bots,iron=iron,"
        "copper=copper,rails=rail,wagons=wagons,"
        "cargo_iron=cargo,fluid_water=fluid}))"
    )
    return _command(rcon, prefix + power + chests + rails + ending)


def _observed(rcon, operation: str, args: str = "") -> dict:
    """Call the game-registered read-only observation, never Lua inspection."""
    body = str(rcon.command("/autoengineer-observe " + operation + args))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"status": "parse_error", "body": body[:250]}


def verify_live(rcon, receipts: list[dict]) -> dict:
    """Independently inspect populated logistics and railway observations."""
    # Give robot networks time to update their members.
    time.sleep(3)
    network = _observed(rcon, "logistics", " page=1 page_size=16")
    robots = _observed(rcon, "robots")
    transport = _observed(rcon, "transport", " page=1 page_size=64")
    machines = _observed(rcon, "machine_inventories", " page=1 page_size=64")
    network_rows = network.get("rows") or []
    train_rows = transport.get("rows") or []
    item_rows = [item for row in network_rows for item in row.get("items", [])
                 if isinstance(item, dict)]
    named_items = {str(item.get("name")): sum(
        int(row.get("count") or 0) for row in item_rows
        if row.get("name") == item.get("name")) for item in item_rows}
    wagon_rows = [r for r in train_rows if r.get("type") in ("cargo-wagon", "fluid-wagon")]
    cargo_items = [
        entry for row in wagon_rows for inventory in row.get("inventories", [])
        for entry in inventory.get("items", []) if isinstance(entry, dict)]
    fluid_rows = [
        fluid for row in wagon_rows for fluid in row.get("fluids", [])
        if isinstance(fluid, dict)]
    robot_count = int(robots.get("total_logistic_robots") or 0) + int(
        robots.get("total_construction_robots") or 0)
    has_iron = any(i.get("name") == "iron-plate" and i.get("count", 0) > 0
                   for i in cargo_items)
    has_water = any(i.get("name") == "water" and i.get("amount", 0) > 0
                    for i in fluid_rows)
    result = {
        "status_by_section": {k: v.get("status") for k, v in (
            ("logistics", network), ("robots", robots),
            ("transport", transport), ("machine_inventories", machines))},
        "networks_reported": network.get("total"),
        "network_rows": len(network_rows),
        "logistic_contents": named_items,
        "total_logistic_robots": robots.get("total_logistic_robots"),
        "total_construction_robots": robots.get("total_construction_robots"),
        "transport_total": transport.get("total"),
        "wagon_rows": len(wagon_rows),
        "wagon_iron_found": has_iron,
        "wagon_water_found": has_water,
        "machine_rows": machines.get("row_count"),
        "built_wagons": sum(int(r.get("wagons") or 0) for r in receipts),
        "built_rails": sum(int(r.get("rails") or 0) for r in receipts),
        "bots_inserted": sum(int(r.get("bots") or 0) for r in receipts),
    }
    result["contents_verified"] = (
        all(x == "ok" for x in result["status_by_section"].values())
        and len(network_rows) >= 1
        and robot_count >= 1
        and bool(named_items.get("iron-plate", 0))
        and bool(named_items.get("copper-plate", 0))
        and len(wagon_rows) >= 1
        and has_iron and has_water
    )
    return result


def run(*, replicas: int, seconds: int, networks: int) -> int:
    """Reuse the accepted creative/AI/R10-B observer stack with a richer world."""
    if not 1 <= replicas <= 4 or not 1 <= networks <= 8:
        raise ValueError("Bounded replicas and networks required")
    previous = direct.creative_place
    before = {p.name for p in OUTPUT.glob("py-*")}
    fixture: dict = {}

    def place(rcon, blueprint, copies):
        base = previous(rcon, blueprint, copies)
        fixture["init"] = initialize(rcon, networks)
        fixture["receipts"] = []
        for i in range(networks):
            receipt = construct_network(rcon, i)
            fixture["receipts"].append(receipt)
            print(f"[rail-bots] network {i+1}/{networks}: {receipt}", flush=True)
        fixture["observed"] = verify_live(rcon, fixture["receipts"])
        print("[rail-bots] REGISTERED_OBSERVATION=" +
              json.dumps(fixture["observed"], sort_keys=True), flush=True)
        base["logistics_rail_fixture"] = {
            "networks": networks,
            "built": fixture["receipts"],
            "observed": fixture["observed"],
        }
        return base

    direct.creative_place = place
    try:
        rc = stress.run(replicas, seconds)
    finally:
        direct.creative_place = previous
        fresh = [p for p in OUTPUT.glob("py-*") if p.name not in before]
        if fresh:
            work = sorted(fresh, key=lambda p: p.name)[-1]
            (work / "populated-fixture.json").write_text(
                json.dumps(fixture, indent=2, default=str), encoding="utf-8")
    if not fixture.get("observed", {}).get("contents_verified"):
        print("[rail-bots] PARTIAL: populated robot/wagon observation not fully proven",
              flush=True)
        return 1
    return rc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicas", type=int, default=4)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--networks", type=int, default=8)
    args = parser.parse_args()
    raise SystemExit(run(replicas=args.replicas, seconds=args.seconds,
                         networks=args.networks))
