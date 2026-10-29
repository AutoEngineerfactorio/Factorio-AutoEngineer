"""Apply a fetched, externally sourced pY blueprint to a disposable save.

Factorio 2.1.23 registered RCON observes status; creative commands are
explicitly user-authorized for this isolated stress save only. A small
non-mutating console marker clears the first-command achievement gate.
No commands target a non-disposable session.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import zlib
from collections import Counter
from pathlib import Path

EXPECTED_NAMES = {
    "niobium-pipe-to-ground", "niobium-pipe", "medium-electric-pole",
    "distilator", "vacuum-pump-mk01", "py-gas-vent", "big-electric-pole",
}
_SOURCE = "https://factoriobin.com/post/u1wmtx/44"


def inspect_blueprint(path: Path) -> dict:
    exchange = path.read_text(encoding="utf-8").strip()
    if not exchange.startswith("0") or not re.fullmatch(r"0[A-Za-z0-9+/=]+", exchange):
        raise ValueError("Not a safe Factorio 2.x blueprint exchange string")
    decoded = json.loads(zlib.decompress(base64.b64decode(exchange[1:])))
    blueprint = decoded.get("blueprint")
    if not isinstance(blueprint, dict):
        raise ValueError("Only one standalone blueprint is accepted")
    entities = blueprint.get("entities")
    if not isinstance(entities, list) or not 1000 <= len(entities) <= 2000:
        raise ValueError("Unexpected blueprint size")
    names = Counter(e.get("name") for e in entities)
    if set(names) != EXPECTED_NAMES or names["distilator"] != 72:
        raise ValueError("Downloaded blueprint did not match the reviewed pY plant")
    return {
        "source_url": _SOURCE,
        "exchange_sha256": hashlib.sha256(exchange.encode()).hexdigest(),
        "entities_per_copy": len(entities),
        "names": dict(names),
        "recipes": dict(Counter(e.get("recipe") for e in entities if e.get("recipe"))),
        "exchange": exchange,
    }


def _send(rcon, lua: str) -> str:
    return str(rcon.command("/c " + lua)).strip()


def _ack(rcon, lua: str, expected: str) -> str:
    result = _send(rcon, lua)
    if expected not in result:
        raise RuntimeError("Creative Factorio command failed: " + result[:150])
    return result


def build_disposable_blueprint(rcon, path: Path, replicas: int) -> dict:
    """Import in bounded pieces and revive ghosts on a new private surface."""
    if not 1 <= replicas <= 4:
        raise ValueError("Only 1–4 reviewed blueprint copies allowed")
    details = inspect_blueprint(path)
    gate = "/c rcon.print('AE_BP_GATE_READY')"
    result = str(rcon.command(gate)).strip()
    if "AE_BP_GATE_READY" not in result:
        result = str(rcon.command(gate)).strip()
    if "AE_BP_GATE_READY" not in result:
        raise RuntimeError("Factorio console gate not confirmed, no write attempted")

    # Bounded transfer. Each chunk has independent ACK; never retry a
    # state-mutating command if its execution is uncertain.
    _ack(rcon, "storage.ae_bp_chunks={};rcon.print('AE_BP_INIT_OK')",
         "AE_BP_INIT_OK")
    exchange = details.pop("exchange")
    for index, start in enumerate(range(0, len(exchange), 900)):
        piece = exchange[start:start + 900]
        _ack(rcon, "storage.ae_bp_chunks[#storage.ae_bp_chunks+1]='"
             + piece + "';rcon.print('AE_BP_ACK_" + str(index) + "')",
             "AE_BP_ACK_" + str(index))

    _ack(rcon, (
        "local p=game.connected_players[1];"
        "if not p or not p.character then error('No player') end;"
        "p.force.research_all_technologies();"
        "local s=game.surfaces['ae-py-blueprint-stress'] "
        "or game.create_surface('ae-py-blueprint-stress',{water=0});"
        "p.teleport({0,0},s);"
        "rcon.print('AE_BP_SURFACE_OK')"
    ), "AE_BP_SURFACE_OK")
    result_data = []
    for i in range(replicas):
        center = i * 360
        # Phase separated per blueprint so a large creative construction
        # never becomes part of the measured ongoing UPS test window.
        lua = (
            "local p=game.connected_players[1];"
            "local s=game.surfaces['ae-py-blueprint-stress'];"
            "local x=" + str(center) + ";"
            "s.request_to_generate_chunks({x,0},6);"
            "s.force_generate_chunk_requests();"
            "local inv=game.create_inventory(1);"
            "local b=inv[1];"
            "local code=b.import_stack(table.concat(storage.ae_bp_chunks));"
            "if code==1 or not b.is_blueprint_setup() then "
            "rcon.print('AE_BP_ERROR_IMPORT:'..tostring(code));return end;"
            "local imported=b.get_blueprint_entities();"
            "local expected=imported and #imported or 0;"
            "if expected<1100 then rcon.print('AE_BP_BAD_IMPORT:'..expected);return end;"
            "local ghosts=b.build_blueprint{surface=s,force=p.force,"
            "position={x=x,y=0},"
            "build_mode=defines.build_mode.superforced,skip_fog_of_war=false};"
            "local total=#ghosts;local built=0;"
            "for _,g in pairs(ghosts) do "
            "if g.valid and g.type=='entity-ghost' then "
            "local _,entity=g.silent_revive();"
            "if entity and entity.valid then built=built+1 end end end;"
            # Place private high-capacity creative power adjacent to
            # blueprint's eastern big-electric-pole network.
            "local gen=s.create_entity{name='electric-energy-interface',"
            "position={x=x+182,y=0},force=p.force};"
            "if gen then gen.power_production=250000000;gen.power_usage=0 end;"
            "local pole=s.create_entity{name='big-electric-pole',"
            "position={x=x+175,y=0},force=p.force};"
            "rcon.print('AE_BP_BUILT:'..total..':'..built..':'.."
            "(gen and 1 or 0)..':'..(pole and 1 or 0));"
            "inv.destroy()"
        )
        reply = _send(rcon, lua)
        match = re.search(r"AE_BP_BUILT:(\d+):(\d+):(\d+):(\d+)", reply)
        if match is None:
            raise RuntimeError("Pyanodons blueprint did not build: " + reply[:190])
        ghosts, built, generators, poles = map(int, match.groups())
        result_data.append({"copy": i + 1, "ghosts": ghosts,
                            "revived": built, "creative_generators": generators,
                            "extra_poles": poles})
        if ghosts < 650 or built < 550:
            raise RuntimeError(f"Blueprint build below usable threshold: {built}/{ghosts}")
    # Player's surface determines in-game mod telemetry scopes.
    details["copies"] = result_data
    details["actual_revived"] = sum(copy["revived"] for copy in result_data)
    details["requested_entities"] = details["entities_per_copy"] * replicas
    details["revival_coverage"] = round(
        details["actual_revived"] / details["requested_entities"], 3)
    details["placement_complete"] = (
        details["actual_revived"] >= details["requested_entities"])
    return details


def measure_activity(rcon) -> dict:
    """Verify that machines are actually working, not just decorative ghosts."""
    response = _send(rcon, (
        "local s=game.surfaces['ae-py-blueprint-stress'];"
        "if not s then rcon.print('AE_BP_ACTIVITY:NO_SURFACE');return end;"
        "local dist=s.find_entities_filtered{name='distilator'};"
        "local pump=s.find_entities_filtered{name='vacuum-pump-mk01'};"
        "local working=0;local recipes=0;"
        "for _,e in pairs(dist) do "
        "if e.get_recipe() then recipes=recipes+1 end;"
        "if e.status==defines.entity_status.working then working=working+1 end end;"
        "local pumping=0;"
        "for _,e in pairs(pump) do "
        "if e.status==defines.entity_status.working then pumping=pumping+1 end end;"
        "rcon.print('AE_BP_ACTIVITY:'..#dist..':'..recipes..':'.."
        "working..':'..#pump..':'..pumping)"
    ))
    match = re.search(r"AE_BP_ACTIVITY:(\d+):(\d+):(\d+):(\d+):(\d+)", response)
    if not match:
        raise RuntimeError("Unable to verify active blueprint machinery: " + response[:150])
    dist, recipes, working, pumps, pumping = map(int, match.groups())
    return {"distilators": dist, "distilators_with_recipe": recipes,
            "working_distilators": working, "vacuum_pumps": pumps,
            "working_pumps": pumping}
