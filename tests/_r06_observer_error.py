"""Report the real exception behind the observer's "unavailable" status.

The observer swallows its exception, so the cause is not visible in the
dashboard. This probe calls the observer's own ``mcp_parameters`` and then
the bounded display read, and reports the exact exception.

Read-only: it only calls the bounded display read.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tests"))

RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"
PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"


async def main() -> int:
    import autoengineer_config
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    secret = json.loads(
        (RUNTIME / "rcon.secret.json").read_text(encoding="utf-8"))
    os.environ["FACTORIO_RCON_PASSWORD"] = secret["rcon_password"]
    os.environ["AUTOENGINEER_MODE"] = "helper"
    os.environ["AUTOENGINEER_CONFIG"] = str(
        ROOT / ".local" / "dashboard-observer-config.json")

    try:
        params = autoengineer_config.mcp_parameters()
        print("MCP_PARAMETERS_OK")
        print(f"  command={params.command}")
        print(f"  args={params.args}")
        print(f"  cwd={params.cwd}")
        env = params.env or {}
        for key in sorted(env):
            if "PASSWORD" in key:
                print(f"  env {key}=<len {len(str(env[key]))}>")
            else:
                print(f"  env {key}={env[key]}")
    except Exception as exc:
        print(f"MCP_PARAMETERS_FAILED {type(exc).__name__}: {exc}")
        return 1

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await asyncio.wait_for(
                    session.call_tool("autoengineer_view", {}), 60)
                if getattr(response, "is_error", False):
                    print("VIEW_IS_ERROR")
                    for item in getattr(response, "content", []) or []:
                        if getattr(item, "type", "") == "text":
                            print(f"  {str(item.text)[:600]}")
                    return 2
                text = next(
                    item.text for item in response.content
                    if item.type == "text")
                payload = json.loads(text)
                print(f"VIEW_STATUS={payload.get('status')}")
                capabilities = payload.get("capabilities") or {}
                print(f"  capabilities_keys={sorted(capabilities)[:12]}")
                print(f"  recipes={len(capabilities.get('recipes') or [])}")
                print(f"  view_status={(payload.get('catalog_status') or {}).get('status')}")
    except Exception as exc:
        print(f"VIEW_FAILED {type(exc).__name__}: {exc}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
