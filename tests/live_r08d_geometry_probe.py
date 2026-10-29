"""LIVE READ-ONLY R08-D probe: ore node and tree geometry, for the map layers.

Safety contract:
* Never starts or stops Factorio. Attaches to the running 2.1.23.
* Calls ONLY ``autoengineer_view``. Read-only.
* Never writes to the save; the digest is compared before and after.
* Reports only geometry, names and counts.

Usage:
    python -B tests/live_r08d_geometry_probe.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
SAVE = PROFILE / "data" / "saves" / "autoengineer-test.zip"
DLL = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23" / "FactorioMCP.dll"
OUTPUT = ROOT / ".local" / "live-pillow-2.1.23" / "evidence" / "r08d-geometry-live.json"


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


def describe(entity):
    """Return the observed footprint of one entity in tiles."""
    bounds = entity.get("bounds")
    if isinstance(bounds, dict):
        a, b = bounds.get("left_top"), bounds.get("right_bottom")
        if isinstance(a, dict) and isinstance(b, dict):
            try:
                return (
                    round(float(b["x"]) - float(a["x"]), 3),
                    round(float(b["y"]) - float(a["y"]), 3),
                )
            except (KeyError, TypeError, ValueError):
                return None
    if entity.get("width") and entity.get("height"):
        return (round(float(entity["width"]), 3), round(float(entity["height"]), 3))
    return None


async def main() -> int:
    before = digest(SAVE)
    log(f"SAVE_DIGEST_BEFORE={before}")
    host, port, password = read_socket()
    report: dict = {"save_digest_before": before, "resources": {}, "nature": {}}

    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            base = await read_view(session, 0, 0)
            meta = (base.get("terrain") or {}).get("map_chunk") or {}
            cx, cy = int(meta.get("x", 0)), int(meta.get("y", 0))

            res_bounds: dict[str, Counter] = {}
            tree_bounds: dict[str, Counter] = {}
            res_pos: dict[str, list] = {}
            for dx in range(-1, 3):
                for dy in range(-1, 3):
                    chunk = await read_view(session, cx + dx, cy + dy)
                    for e in (chunk.get("terrain") or {}).get("entities") or []:
                        if e.get("kind") == "resource":
                            name = e.get("name")
                            size = describe(e)
                            res_bounds.setdefault(name, Counter())[size] += 1
                            res_pos.setdefault(name, []).append(
                                (e.get("x"), e.get("y"), size)
                            )
                        elif e.get("kind") == "nature" and (e.get("name") or "").startswith("tree-"):
                            name = e.get("name")
                            tree_bounds.setdefault(name, Counter())[describe(e)] += 1

            for name, counter in sorted(res_bounds.items()):
                report["resources"][name] = {str(k): v for k, v in counter.most_common()}
                log(f"RESOURCE {name} bounds={counter.most_common(6)}")
            for name, counter in sorted(tree_bounds.items()):
                report["nature"][name] = {str(k): v for k, v in counter.most_common()}
                log(f"TREE {name} bounds={counter.most_common(6)}")

            # Cluster analysis for the densest resource: are the nodes one
            # connected field or many separate deposits?
            for name, positions in sorted(res_pos.items()):
                if len(positions) < 40:
                    continue
                xs = [p[0] for p in positions]
                ys = [p[1] for p in positions]
                extent = (round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1))
                report.setdefault("resource_extent", {})[name] = {
                    "count": len(positions),
                    "extent_tiles": extent,
                }
                log(
                    f"EXTENT {name} count={len(positions)} "
                    f"extent_tiles={extent} "
                    f"area={round(extent[0] * extent[1])} "
                    f"density={round(len(positions) / max(1, extent[0] * extent[1]), 2)}"
                )

    after = digest(SAVE)
    report["save_digest_after"] = after
    report["save_unchanged"] = before == after
    log(f"SAVE_UNCHANGED={before == after}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"WROTE={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
