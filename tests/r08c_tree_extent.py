"""Find the live extent of the observed trees and resources in chunk 0,0.

The detail render must cover a rectangle that actually contains the trees, so
the forest coverage can be compared with the Factorio map at matching
coordinates.

Usage:
    python -B tests/r08c_tree_extent.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
sys.path.insert(0, str(ROOT / "agent"))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
DLL = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23" / "FactorioMCP.dll"


def read_socket():
    text = CONFIG.read_text(encoding="utf-8")
    socket_match = re.search(r"local-rcon-socket=(\S+)", text)
    if socket_match is None:
        raise ValueError("local-rcon-socket not found in config")
    socket_value = socket_match.group(1)
    host, port = socket_value.rsplit(":", 1)
    password_match = re.search(r"local-rcon-password=(\S+)", text)
    if password_match is None:
        raise ValueError("local-rcon-password not found in config")
    password = password_match.group(1)
    return host, int(port), password


def backend_params(host, port, password):
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "DOTNET_ROOT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update({
        "FACTORIO_RCON_HOST": host,
        "FACTORIO_RCON_PORT": str(port),
        "FACTORIO_RCON_PASSWORD": password,
        "AUTOENGINEER_BACKEND_MODE": "helper",
        "Logging__LogLevel__Default": "None",
        "Logging__LogLevel__Microsoft": "None",
    })
    runtime = ROOT / ".local" / "live-pillow-2.1.23" / "backend-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return StdioServerParameters(command="dotnet", args=[str(DLL)], env=env, cwd=str(runtime))


async def main():
    host, port, password = read_socket()
    chunks = {}
    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for chunk_x in (-1, 0, 1):
                answer = await asyncio.wait_for(
                    session.call_tool("autoengineer_view", arguments={
                        "catalogPage": 1, "catalogPageSize": 1,
                        "mapChunkX": chunk_x, "mapChunkY": 0,
                    }),
                    timeout=40,
                )
                raw = next((c.text for c in answer.content if c.type == "text"), "")
                data = json.loads(raw)
                chunks[chunk_x] = (data.get("terrain") or {}).get("entities") or []

    nature = []
    resources = []
    for chunk_x, entities in chunks.items():
        for entity in entities:
            entry = dict(entity, chunk_x=chunk_x)
            if entity.get("kind") == "nature":
                nature.append(entry)
            elif entity.get("kind") == "resource":
                resources.append(entry)

    def extent(items):
        if not items:
            return None
        xs = [e["x"] for e in items]
        ys = [e["y"] for e in items]
        return {
            "count": len(items),
            "x_min": min(xs), "x_max": max(xs),
            "y_min": min(ys), "y_max": max(ys),
        }

    report = {
        "nature_extent": extent(nature),
        "resource_extent": extent(resources),
        "nature_by_name": {},
        "trees_per_chunk": {},
    }
    for entity in nature:
        report["nature_by_name"].setdefault(entity.get("name"), 0)
        report["nature_by_name"][entity["name"]] += 1
    for chunk_x, entities in chunks.items():
        report["trees_per_chunk"][str(chunk_x)] = sum(
            1 for e in entities if e.get("kind") == "nature"
        )

    # A tight rectangle around the trees, so the forest can be compared.
    if nature:
        xs = [e["x"] for e in nature]
        ys = [e["y"] for e in nature]
        pad = 4
        report["tree_rectangle"] = {
            "x0": max(0, int(min(xs)) - pad),
            "y0": max(0, int(min(ys)) - pad),
            "x1": int(max(xs)) + pad,
            "y1": int(max(ys)) + pad,
        }

    path = ROOT / "tests" / "r08c_extent_live.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("WROTE=" + str(path))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
