"""LIVE READ-ONLY R08-C multi-chunk verification against the running Factorio.

Safety contract enforced by this module:

* It NEVER starts or stops Factorio. It attaches to the already running
  Factorio 2.1.23 instance over its read-only RCON socket.
* It calls ONLY ``autoengineer_policy`` and ``autoengineer_view``. Both are
  read-only. No walk, no operation, no arm, no renew, no gameplay command.
* It never writes to the save. The save digest is compared before and after.
* It uses the freshly built patched backend from
  ``.local/live-pillow-2.1.23/backend-patched-2.1.23`` so the new chunk
  arguments are actually exercised.

Usage:
    python -B tests/live_r08c_chunk_probe.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from dashboard_chunk_grid import CHUNK_TILES  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
SAVE = PROFILE / "data" / "saves" / "autoengineer-test.zip"
DLL = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23" / "FactorioMCP.dll"
OUTPUT = ROOT / ".local" / "live-pillow-2.1.23" / "evidence" / "r08c-chunk-live.json"

EXPECTED_TOOLS = {
    "autoengineer_operation_preview",
    "autoengineer_operation",
    "autoengineer_view",
    "autoengineer_policy",
    "get_player_position",
    "scan_resources",
    "get_nearby_entities",
    "walk_to_position",
    "autoengineer_status",
    "autoengineer_arm",
    "autoengineer_renew",
    "autoengineer_stop",
}


def log(message: str) -> None:
    print(str(message), flush=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_socket() -> tuple[str, int, str]:
    """Read the RCON socket and password from the launcher profile config."""
    text = CONFIG.read_text(encoding="utf-8")
    socket_match = re.search(r"local-rcon-socket=(\S+)", text)
    password_match = re.search(r"local-rcon-password=(\S+)", text)
    if not socket_match or not password_match:
        raise SystemExit("RCON socket or password not found in config.ini")
    host, port = socket_match.group(1).rsplit(":", 1)
    return host, int(port), password_match.group(1)


def backend_params(host: str, port: int, password: str) -> StdioServerParameters:
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "DOTNET_ROOT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update(
        {
            "FACTORIO_RCON_HOST": host,
            "FACTORIO_RCON_PORT": str(port),
            "FACTORIO_RCON_PASSWORD": password,
            "AUTOENGINEER_BACKEND_MODE": "helper",
            "Logging__LogLevel__Default": "None",
            "Logging__LogLevel__Microsoft": "None",
        }
    )
    runtime = ROOT / ".local" / "live-pillow-2.1.23" / "backend-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return StdioServerParameters(command="dotnet", args=[str(DLL)], env=env, cwd=str(runtime))


def identity(entity: dict) -> tuple:
    return (
        entity.get("kind"),
        entity.get("name"),
        round(float(entity.get("x", 0.0)), 3),
        round(float(entity.get("y", 0.0)), 3),
    )


async def view(session, arguments: dict) -> dict:
    answer = await asyncio.wait_for(
        session.call_tool("autoengineer_view", arguments=arguments), timeout=40
    )
    if answer.is_error:
        raise RuntimeError("view failed: " + str(answer.content)[:300])
    raw = next((c.text for c in answer.content if c.type == "text"), "")
    return json.loads(raw)


async def run() -> int:
    host, port, password = read_socket()
    save_before = digest(SAVE)
    log("SAVE_DIGEST_BEFORE=" + save_before)
    report: dict = {
        "save_digest_before": save_before,
        "chunk_tiles": CHUNK_TILES,
        "read_only_tools_called": ["autoengineer_policy", "autoengineer_view"],
    }

    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await asyncio.wait_for(session.list_tools(), timeout=20)
            names = sorted(tool.name for tool in listed.tools)
            report["tools"] = names
            report["tool_count"] = len(names)
            report["tools_match_policy_v8"] = set(names) == EXPECTED_TOOLS
            log("TOOL_COUNT=" + str(len(names)))
            log("TOOLS_MATCH_POLICY_V8=" + str(report["tools_match_policy_v8"]))

            policy = await asyncio.wait_for(session.call_tool("autoengineer_policy"), timeout=20)
            policy_data = json.loads(
                next((c.text for c in policy.content if c.type == "text"), "{}")
            )
            report["policy"] = policy_data
            log("POLICY=" + json.dumps(policy_data))

            # -- the player's own chunk ---------------------------------
            base = await view(session, {"catalogPage": 1, "catalogPageSize": 1})
            terrain = base.get("terrain") or {}
            base_chunk = terrain.get("map_chunk") or {}
            report["base_chunk"] = base_chunk
            report["base_origin"] = terrain.get("origin")
            report["base_chunk_complete"] = terrain.get("chunk_complete")
            report["base_partial"] = terrain.get("partial")
            report["base_entity_count"] = len(terrain.get("entities") or [])
            report["base_tick"] = base.get("tick")
            report["surface"] = base.get("surface")
            log("BASE_CHUNK=" + json.dumps(base_chunk))
            log("BASE_ORIGIN=" + json.dumps(terrain.get("origin")))
            log("BASE_ENTITIES=" + str(report["base_entity_count"]))

            # -- a row of adjacent chunks --------------------------------
            start_x = int(base_chunk.get("x", 0))
            start_y = int(base_chunk.get("y", 0))
            requested = [
                (start_x + offset, start_y)
                for offset in range(-2, 3)
            ]
            chunks = {}
            latencies = []
            for chunk_x, chunk_y in requested:
                began = time.perf_counter()
                payload = await view(
                    session,
                    {"catalogPage": 1, "catalogPageSize": 1,
                     "mapChunkX": chunk_x, "mapChunkY": chunk_y},
                )
                elapsed = (time.perf_counter() - began) * 1000.0
                latencies.append(elapsed)
                chunk_terrain = payload.get("terrain") or {}
                meta = chunk_terrain.get("map_chunk") or {}
                origin = chunk_terrain.get("origin") or {}
                entities = chunk_terrain.get("entities") or []
                chunks[(chunk_x, chunk_y)] = {
                    "meta": meta,
                    "origin": origin,
                    "entity_count": len(entities),
                    "nature_count": sum(1 for e in entities if e.get("kind") == "nature"),
                    "resource_count": sum(1 for e in entities if e.get("kind") == "resource"),
                    "partial": chunk_terrain.get("partial"),
                    "chunk_complete": chunk_terrain.get("chunk_complete"),
                    "rows": len(chunk_terrain.get("rows") or []),
                    "row_width": len((chunk_terrain.get("rows") or [""])[0]),
                    "identities": {identity(e) for e in entities},
                    "tick": payload.get("tick"),
                }
                log(
                    "CHUNK %d,%d -> meta=%s origin=%s entities=%d nature=%d "
                    "rows=%d width=%d partial=%s complete=%s %.0fms"
                    % (
                        chunk_x,
                        chunk_y,
                        json.dumps(meta),
                        json.dumps(origin),
                        len(entities),
                        chunks[(chunk_x, chunk_y)]["nature_count"],
                        chunks[(chunk_x, chunk_y)]["rows"],
                        chunks[(chunk_x, chunk_y)]["row_width"],
                        chunk_terrain.get("partial"),
                        chunk_terrain.get("chunk_complete"),
                        elapsed,
                    )
                )
            report["chunks"] = {
                "%d,%d" % key: {k: v for k, v in value.items() if k != "identities"}
                for key, value in chunks.items()
            }
            report["chunk_latency_ms"] = {
                "min": round(min(latencies), 1),
                "max": round(max(latencies), 1),
                "mean": round(sum(latencies) / len(latencies), 1),
            }

            # -- coordinate and boundary checks ---------------------------
            alignment_ok = True
            for (chunk_x, chunk_y), value in chunks.items():
                origin = value["origin"]
                meta = value["meta"]
                if origin.get("x") != chunk_x * CHUNK_TILES:
                    alignment_ok = False
                if origin.get("y") != chunk_y * CHUNK_TILES:
                    alignment_ok = False
                if meta.get("x") != chunk_x or meta.get("y") != chunk_y:
                    alignment_ok = False
                if meta.get("size") != CHUNK_TILES:
                    alignment_ok = False
                if value["rows"] != CHUNK_TILES:
                    alignment_ok = False
                if value["row_width"] != CHUNK_TILES * 2:
                    alignment_ok = False
            report["chunk_alignment_ok"] = alignment_ok

            # An entity on a shared boundary must not be duplicated.
            duplicates = []
            for left in range(-2, 2):
                a = chunks.get((start_x + left, start_y))
                b = chunks.get((start_x + left + 1, start_y))
                if a is None or b is None:
                    continue
                shared = a["identities"] & b["identities"]
                if shared:
                    duplicates.append(
                        {"pair": [left, left + 1], "shared": len(shared)}
                    )
            report["boundary_duplicates"] = duplicates
            report["no_boundary_duplicates"] = not duplicates

            # Entities must stay inside their own chunk.
            outside = 0
            for (chunk_x, chunk_y), value in chunks.items():
                lo_x = chunk_x * CHUNK_TILES
                lo_y = chunk_y * CHUNK_TILES
                for ident in value["identities"]:
                    if not (lo_x <= ident[2] < lo_x + CHUNK_TILES):
                        outside += 1
                    elif not (lo_y <= ident[3] < lo_y + CHUNK_TILES):
                        outside += 1
            report["entities_outside_their_chunk"] = outside

            # -- the same chunk twice must be identical --------------------
            first = await view(
                session,
                {"catalogPage": 1, "catalogPageSize": 1,
                 "mapChunkX": start_x, "mapChunkY": start_y},
            )
            second = await view(
                session,
                {"catalogPage": 1, "catalogPageSize": 1,
                 "mapChunkX": start_x, "mapChunkY": start_y},
            )
            first_terrain = first.get("terrain") or {}
            second_terrain = second.get("terrain") or {}
            report["repeat_identical_rows"] = (
                (first_terrain.get("rows") or []) == (second_terrain.get("rows") or [])
            )
            report["repeat_identical_entities"] = (
                (first_terrain.get("entities") or [])
                == (second_terrain.get("entities") or [])
            )

            # -- an invalid chunk request must be rejected ------------------
            rejected = {}
            for label, arguments in (
                ("x_only", {"mapChunkX": 1}),
                ("y_only", {"mapChunkY": 1}),
                ("out_of_range", {"mapChunkX": 100001, "mapChunkY": 0}),
                ("negative_out_of_range", {"mapChunkX": 0, "mapChunkY": -100001}),
            ):
                try:
                    await view(session, dict(arguments, catalogPage=1, catalogPageSize=1))
                    rejected[label] = False
                except Exception:
                    rejected[label] = True
            report["invalid_requests_rejected"] = rejected
            log("INVALID_REQUESTS_REJECTED=" + json.dumps(rejected))

            # -- the player position must not have moved --------------------
            final = await view(session, {"catalogPage": 1, "catalogPageSize": 1})
            report["position_before"] = [base.get("x"), base.get("y")]
            report["position_after"] = [final.get("x"), final.get("y")]
            report["player_did_not_move"] = (
                base.get("x") == final.get("x") and base.get("y") == final.get("y")
            )
            log(
                "PLAYER_POSITION %s -> %s MOVED=%s"
                % (report["position_before"], report["position_after"],
                   not report["player_did_not_move"])
            )
            report["inventory_slots"] = len(final.get("slots") or [])
            report["telemetry_status"] = (final.get("telemetry") or {}).get("status")

    save_after = digest(SAVE)
    report["save_digest_after"] = save_after
    report["save_unchanged"] = save_before == save_after
    log("SAVE_DIGEST_AFTER=" + save_after)
    log("SAVE_UNCHANGED=" + str(report["save_unchanged"]))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log("WROTE=" + str(OUTPUT))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
