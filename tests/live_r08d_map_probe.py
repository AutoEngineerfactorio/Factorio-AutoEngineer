"""LIVE READ-ONLY R08-D diagnostic: enemy, ore, forest and decorative evidence.

Safety contract:
* Never starts or stops Factorio. Attaches to the already running 2.1.23.
* Calls ONLY ``autoengineer_policy`` and ``autoengineer_view``. Both read-only.
* Never writes to the save; the digest is compared before and after.
* Uses the patched backend in .local/live-pillow-2.1.23/backend-patched-2.1.23.

Usage:
    python -B tests/live_r08d_map_probe.py
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
OUTPUT = ROOT / ".local" / "live-pillow-2.1.23" / "evidence" / "r08d-map-live.json"


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
        command="dotnet",
        args=[str(DLL)],
        env=env,
        cwd=str(runtime),
    )


async def read_view(session: ClientSession, chunk_x: int, chunk_y: int) -> dict:
    result = await session.call_tool(
        "autoengineer_view", {"mapChunkX": chunk_x, "mapChunkY": chunk_y}
    )
    text = "".join(
        getattr(item, "text", "") for item in (result.content or []) if hasattr(item, "text")
    )
    return json.loads(text)


async def main() -> int:
    before = digest(SAVE)
    log(f"SAVE_DIGEST_BEFORE={before}")
    host, port, password = read_socket()
    report: dict = {"save_digest_before": before, "chunks": {}}

    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            log(f"TOOL_COUNT={len(names)}")
            report["tools"] = names

            policy = await session.call_tool("autoengineer_policy", {})
            policy_text = "".join(
                getattr(i, "text", "") for i in (policy.content or []) if hasattr(i, "text")
            )
            report["policy"] = policy_text[:400]
            log(f"POLICY={policy_text[:200]}")

            # The player's own chunk defines the interesting window.
            base = await read_view(session, 0, -1)
            base_terrain = base.get("terrain") or {}
            base_meta = base_terrain.get("map_chunk") or {}
            report["base_chunk"] = base_meta
            report["base_origin"] = base_terrain.get("origin")
            report["surface"] = base.get("surface")
            report["tick"] = base.get("tick")
            log(f"BASE_CHUNK={base_meta} origin={base_terrain.get('origin')}")
            log(f"SURFACE={base.get('surface')} TICK={base.get('tick')}")

            # Probe a window of chunks around the player, one 64x64 chunk each.
            cx = int(base_meta.get("x", 0))
            cy = int(base_meta.get("y", 0))
            for dx in range(-2, 4):
                for dy in range(-2, 3):
                    try:
                        chunk = await read_view(session, cx + dx, cy + dy)
                    except Exception as exc:  # noqa: BLE001
                        log(f"CHUNK {cx+dx},{cy+dy} FAILED {exc}")
                        continue
                    terrain = chunk.get("terrain") or {}
                    entities = terrain.get("entities") or []
                    kinds: dict[str, int] = {}
                    names_by_kind: dict[str, list[str]] = {}
                    for e in entities:
                        k = e.get("kind")
                        kinds[k] = kinds.get(k, 0) + 1
                        names_by_kind.setdefault(k, []).append(e.get("name"))
                    sample = {}
                    for k, listed in names_by_kind.items():
                        uniq: dict[str, int] = {}
                        for n in listed:
                            uniq[n] = uniq.get(n, 0) + 1
                        sample[k] = dict(sorted(uniq.items(), key=lambda kv: -kv[1])[:12])
                    rows = terrain.get("rows") or []
                    palette = terrain.get("palette") or []
                    # Count non-black palette entries actually used in the raster.
                    black = 0
                    for row in rows:
                        for i in range(0, len(row), 2):
                            if row[i:i + 2] == "00":
                                black += 1
                    total_tiles = sum(len(r) for r in rows) // 2
                    key = f"{cx+dx},{cy+dy}"
                    report["chunks"][key] = {
                        "meta": terrain.get("map_chunk"),
                        "origin": terrain.get("origin"),
                        "entity_kinds": kinds,
                        "name_samples": sample,
                        "rows": len(rows),
                        "palette": palette[:8],
                        "unexplored_tiles": black,
                        "total_tiles": total_tiles,
                        "partial": terrain.get("partial"),
                    }
                    log(
                        f"CHUNK {key} kinds={kinds} tiles={total_tiles} "
                        f"black={black} palette={len(palette)}"
                    )
                    for k, v in sample.items():
                        log(f"    {k}: {v}")

    after = digest(SAVE)
    report["save_digest_after"] = after
    report["save_unchanged"] = before == after
    log(f"SAVE_DIGEST_AFTER={after}")
    log(f"SAVE_UNCHANGED={before == after}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"WROTE={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
