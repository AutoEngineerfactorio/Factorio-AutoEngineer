"""LIVE READ-ONLY R08-D probe: exact enemy entity payloads and positions.

Safety contract:
* Never starts or stops Factorio. Attaches to the running 2.1.23.
* Calls ONLY ``autoengineer_policy`` and ``autoengineer_view``. Both read-only.
* Never writes to the save; the digest is compared before and after.
* Records only positions, prototype names and counts.

Usage:
    python -B tests/live_r08d_enemy_probe.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
SAVE = PROFILE / "data" / "saves" / "autoengineer-test.zip"
DLL = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23" / "FactorioMCP.dll"
OUTPUT = ROOT / ".local" / "live-pillow-2.1.23" / "evidence" / "r08d-enemy-live.json"


def log(message: str) -> None:
    print(str(message), flush=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_socket() -> tuple[str, int, str]:
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
    return StdioServerParameters(
        command="dotnet", args=[str(DLL)], env=env, cwd=str(runtime)
    )


async def read_view(session: ClientSession, chunk_x: int, chunk_y: int) -> dict:
    result = await session.call_tool(
        "autoengineer_view", {"mapChunkX": chunk_x, "mapChunkY": chunk_y}
    )
    text = next(
        str(getattr(c, "text"))
        for c in result.content
        if getattr(c, "type", "") == "text"
    )
    return json.loads(text)


async def main() -> int:
    before = digest(SAVE)
    log(f"SAVE_DIGEST_BEFORE={before}")
    host, port, password = read_socket()
    report: dict = {"save_digest_before": before, "enemies": []}

    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            base = await read_view(session, 0, 0)
            base_terrain = base.get("terrain") or {}
            base_meta = base_terrain.get("map_chunk") or {}
            cx, cy = int(base_meta.get("x", 0)), int(base_meta.get("y", 0))
            log(f"BASE_CHUNK={base_meta}")
            report["base_chunk"] = base_meta

            for dx in range(-2, 4):
                for dy in range(-2, 3):
                    chunk = await read_view(session, cx + dx, cy + dy)
                    terrain = chunk.get("terrain") or {}
                    for e in terrain.get("entities") or []:
                        if e.get("kind") != "enemy":
                            continue
                        record = dict(e)
                        record["chunk"] = f"{cx+dx},{cy+dy}"
                        report["enemies"].append(record)
                        log(
                            f"ENEMY chunk={cx+dx},{cy+dy} name={e.get('name')} "
                            f"pos=({e.get('x')}, {e.get('y')}) "
                            f"type={e.get('entity_type')} "
                            f"proto_type={e.get('prototype_type')} "
                            f"map_color={e.get('map_color')} "
                            f"bounds={e.get('bounds')} "
                            f"w={e.get('width')} h={e.get('height')}"
                        )

    after = digest(SAVE)
    report["save_digest_after"] = after
    report["save_unchanged"] = before == after
    log(f"ENEMY_COUNT={len(report['enemies'])}")
    log(f"SAVE_DIGEST_AFTER={after}")
    log(f"SAVE_UNCHANGED={before == after}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"WROTE={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
