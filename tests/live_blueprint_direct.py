"""Build real entities from a reviewed pY community blueprint on an isolated save.

This is CREATIVE placement of the decoded blueprint layout, rather than
robot construction or unreliable historical ghost revival. Exact entity
names, directions, positions and recipes are sourced from the blueprint.
No non-disposable game session, user save or mod directory is modified.
"""
from __future__ import annotations

import base64
import json
import re
import zlib
from pathlib import Path

from live_blueprint_stress import inspect_blueprint


def _send(rcon, statement: str) -> str:
    return str(rcon.command("/c " + statement)).strip()


def _require(rcon, statement: str, expected: str) -> str:
    reply = _send(rcon, statement)
    if expected not in reply:
        raise RuntimeError("Creative build not confirmed: " + reply[:150])
    return reply


def source_layout(path: Path) -> tuple[dict, str]:
    metadata = inspect_blueprint(path)
    string = metadata.pop("exchange")
    decoded = json.loads(zlib.decompress(base64.b64decode(string[1:])))
    elements = decoded["blueprint"]["entities"]
    names = sorted({x["name"] for x in elements})
    recipes = sorted({x["recipe"] for x in elements if x.get("recipe")})
    xmin = min(x["position"]["x"] for x in elements)
    xmax = max(x["position"]["x"] for x in elements)
    ymin = min(x["position"]["y"] for x in elements)
    ymax = max(x["position"]["y"] for x in elements)
    center_x, center_y = (xmin + xmax) / 2, (ymin + ymax) / 2
    records = [
        [names.index(e["name"]) + 1,
         round(e["position"]["x"] - center_x, 2),
         round(e["position"]["y"] - center_y, 2),
         e.get("direction", 0),
         recipes.index(e["recipe"]) + 1 if e.get("recipe") else 0]
        for e in elements
    ]
    payload = json.dumps({"names": names, "recipes": recipes, "items": records},
                         separators=(",", ":"))
    metadata["build_method"] = "decoded_blueprint_creative_direct"
    metadata["original_entity_count"] = len(elements)
    return metadata, payload


def creative_place(rcon, path: Path, replicas: int) -> dict:
    if not 1 <= replicas <= 4:
        raise ValueError("Creative construction limited to four blueprint copies")
    details, payload = source_layout(path)
    marker = "/c rcon.print('AE_DIRECT_GATE_READY')"
    reply = str(rcon.command(marker))
    if "AE_DIRECT_GATE_READY" not in reply:
        reply = str(rcon.command(marker))
    if "AE_DIRECT_GATE_READY" not in reply:
        raise RuntimeError("Cannot confirm Factorio creative console permission gate")
    _require(rcon, "storage.ae_direct_bp_chunks={};rcon.print('AE_DIRECT_INIT')",
             "AE_DIRECT_INIT")
    for index, start in enumerate(range(0, len(payload), 780)):
        part = payload[start:start + 780]
        # JSON uses only double-quoted values, no single quotes in payload.
        if "'" in part:
            raise ValueError("Unexpected unsafe apostrophe in blueprint transfer")
        _require(
            rcon, "storage.ae_direct_bp_chunks[#storage.ae_direct_bp_chunks+1]='"
            + part + "';rcon.print('AE_DIRECT_ACK_" + str(index) + "')",
            "AE_DIRECT_ACK_" + str(index),
        )

    _require(rcon, (
        "local p=game.connected_players[1];"
        "if not p or not p.character then error('No connected test player') end;"
        "p.force.research_all_technologies();"
        "local s=game.surfaces['ae-py-blueprint-stress'] or "
        "game.create_surface('ae-py-blueprint-stress',{water=0});"
        "p.teleport({0,0},s);"
        "rcon.print('AE_DIRECT_SURFACE_READY')"
    ), "AE_DIRECT_SURFACE_READY")

    records = []
    for index in range(replicas):
        center = index * 360
        # All data comes from the external blueprint. This command affects
        # only the freshly created, isolated creative test surface.
        statement = (
            "local p=game.connected_players[1];"
            "local s=game.surfaces['ae-py-blueprint-stress'];"
            "local x=" + str(center) + ";"
            "s.request_to_generate_chunks({x,0},6);"
            "s.force_generate_chunk_requests();"
            "local area={{x-180,-40},{x+180,40}};"
            "for _,e in pairs(s.find_entities_filtered{area=area,"
            "type={'tree','simple-entity','resource'}}) do e.destroy() end;"
            "local d=helpers.json_to_table(table.concat(storage.ae_direct_bp_chunks));"
            "if not d or #d.items~=1225 then error('Blueprint rows missing') end;"
            "local built=0;local recipes=0;local missing=0;"
            "for _,a in pairs(d.items) do "
            "local o={name=d.names[a[1]],position={x+a[2],a[3]},"
            "direction=a[4],force=p.force};"
            "local ok,e=pcall(function()return s.create_entity(o)end);"
            "if ok and e and e.valid then "
            "built=built+1;"
            "if a[5]>0 and e.type=='assembling-machine' then "
            "local yes=pcall(function()e.set_recipe(d.recipes[a[5]])end);"
            "if yes then recipes=recipes+1 end end "
            "else missing=missing+1 end end;"
            "local pole=s.create_entity{name='big-electric-pole',"
            "position={x+174,0},force=p.force};"
            "local sub=s.create_entity{name='substation',"
            "position={x+174,6},force=p.force};"
            "local gen=s.create_entity{name='electric-energy-interface',"
            "position={x+174,10},force=p.force};"
            "if gen then gen.power_production=250000000;gen.power_usage=0 end;"
            "rcon.print('AE_DIRECT_BUILT:'..built..':'..missing..':'..recipes.."
            "':'..(pole and 1 or 0)..':'..(gen and 1 or 0).."
            "':'..(sub and 1 or 0))"
        )
        reply = _send(rcon, statement)
        match = re.search(r"AE_DIRECT_BUILT:(\d+):(\d+):(\d+):(\d+):(\d+):(\d+)",
                          reply)
        if match is None:
            raise RuntimeError("Decoded creative blueprint failed: " + reply[:220])
        built, missing, recipes, pole, generator, substation = map(int, match.groups())
        row = {"copy": index + 1, "placed": built, "missing": missing,
               "recipes_set": recipes, "extra_poles": pole,
               "creative_generators": generator, "substations": substation}
        records.append(row)
        if built < 1000 or recipes < 50:
            raise RuntimeError("Decoded blueprint below working-size target: "
                               + str(row))
    details["copies"] = records
    details["requested_entities"] = 1225 * replicas
    details["actual_revived"] = sum(row["placed"] for row in records)
    details["revival_coverage"] = round(
        details["actual_revived"] / details["requested_entities"], 3)
    details["placement_complete"] = all(row["missing"] == 0 for row in records)
    return details


def diagnose_machines(rcon) -> dict:
    """Read machine state on the disposable surface without changing gameplay."""
    statement = (
        "local s=game.surfaces['ae-py-blueprint-stress'];"
        "local info={};"
        "for _,n in pairs({'distilator','vacuum-pump-mk01',"
        "'medium-electric-pole','big-electric-pole','electric-energy-interface'}) do "
        "local es=s.find_entities_filtered{name=n};"
        "local e=es[1];local row={count=#es};"
        "if e and e.valid then "
        "local ok,stat=pcall(function()return e.status end);"
        "if ok then for k,v in pairs(defines.entity_status) do "
        "if v==stat then row.status=k end end end;"
        "local oe,en=pcall(function()return e.energy end);"
        "if oe then row.energy=en end;"
        "local orc,rec=pcall(function()return e.get_recipe() end);"
        "if orc and rec then row.recipe=rec.name end;"
        "local of,len=pcall(function()return #e.fluidbox end);"
        "row.fluidbox_count=of and len or -1;"
        "end;info[n]=row end;"
        "rcon.print('AE_BP_STATE:'..helpers.table_to_json(info))"
    )
    response = _send(rcon, statement)
    if not response:
        response = _send(rcon, statement)  # Read-only verification can be repeated.
    marker = "AE_BP_STATE:"
    if marker not in response:
        raise RuntimeError("Unable to inspect creative factory status: " + response[:180])
    return json.loads(response.split(marker, 1)[1])
