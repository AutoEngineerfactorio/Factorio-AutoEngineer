"""LIVE READ-ONLY probe: what geometry do resource and nature entities report?

This decides whether the dashboard can draw solid resource patches and
full tree marks the way the Factorio map does. It only reads.

Usage:
    python -B tests/live_r08c_geometry_probe.py
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
    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            answer = await asyncio.wait_for(
                session.call_tool("autoengineer_view", arguments={
                    "catalogPage": 1, "catalogPageSize": 1,
                    "mapChunkX": 0, "mapChunkY": 0,
                }),
                timeout=40,
            )
            raw = next((c.text for c in answer.content if c.type == "text"), "")
            data = json.loads(raw)
    entities = (data.get("terrain") or {}).get("entities") or []
    summary = {}
    samples = {}
    for entity in entities:
        kind = entity.get("kind")
        name = entity.get("name")
        key = "%s/%s" % (kind, name)
        entry = summary.setdefault(
            key,
            {
                "count": 0,
                "with_bounds": 0,
                "with_width_height": 0,
                "with_map_color": 0,
                "with_prototype_type": 0,
                "with_graphics_variation": 0,
                "distinct_widths": set(),
                "distinct_heights": set(),
            },
        )
        entry["count"] += 1
        if "bounds" in entity:
            entry["with_bounds"] += 1
        if "width" in entity and "height" in entity:
            entry["with_width_height"] += 1
            entry["distinct_widths"].add(entity.get("width"))
            entry["distinct_heights"].add(entity.get("height"))
        if "map_color" in entity:
            entry["with_map_color"] += 1
        if "prototype_type" in entity:
            entry["with_prototype_type"] += 1
        if "graphics_variation" in entity:
            entry["with_graphics_variation"] += 1
        samples.setdefault(key, entity)
    out = {}
    for key, entry in summary.items():
        entry["distinct_widths"] = sorted(entry["distinct_widths"], key=str)
        entry["distinct_heights"] = sorted(entry["distinct_heights"], key=str)
        out[key] = entry
    report = {
        "total_entities": len(entities),
        "by_kind_name": out,
        "samples": samples,
    }
    path = ROOT / "tests" / "r08c_geometry_live.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("WROTE=" + str(path))
    for key, entry in sorted(out.items()):
        print(
            "%-32s count=%-5d bounds=%-5d w/h=%-5d color=%-5d proto=%-5d var=%-5d w=%s h=%s"
            % (
                key, entry["count"], entry["with_bounds"], entry["with_width_height"],
                entry["with_map_color"], entry["with_prototype_type"],
                entry["with_graphics_variation"],
                entry["distinct_widths"], entry["distinct_heights"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
