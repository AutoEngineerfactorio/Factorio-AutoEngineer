"""Compare the observer's launch parameters with the harness's working ones.

The observer's bounded read returns "unavailable" while the harness's read
of the same backend succeeds. This probe calls the same tool twice: once
with the observer's parameters and once with the harness's parameters, and
reports both outcomes side by side.

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


async def try_read(label: str, params) -> None:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await asyncio.wait_for(
                    session.call_tool("autoengineer_view", {}), 90)
                if getattr(response, "is_error", False):
                    print(f"{label}: IS_ERROR")
                    for item in getattr(response, "content", []) or []:
                        if getattr(item, "type", "") == "text":
                            print(f"  {str(item.text)[:400]}")
                    return
                text = next(
                    item.text for item in response.content if item.type == "text")
                payload = json.loads(text)
                capabilities = payload.get("capabilities") or {}
                print(
                    f"{label}: status={payload.get('status')} "
                    f"recipes={len(capabilities.get('recipes') or [])} "
                    f"catalog={(payload.get('catalog_status') or {}).get('status')}"
                )
    except Exception as exc:
        print(f"{label}: FAILED {type(exc).__name__}: {exc}")


async def main() -> int:
    import autoengineer_config
    import live_r06_game_side_verify as harness
    import r06_live_environment as live_env

    secret = json.loads(
        (RUNTIME / "rcon.secret.json").read_text(encoding="utf-8"))
    password = secret["rcon_password"]
    os.environ["FACTORIO_RCON_PASSWORD"] = password
    os.environ["AUTOENGINEER_MODE"] = "helper"
    os.environ["AUTOENGINEER_CONFIG"] = str(
        ROOT / ".local" / "dashboard-observer-config.json")

    from mcp import StdioServerParameters

    observer_params = autoengineer_config.mcp_parameters()
    harness_params = StdioServerParameters(
        command="dotnet",
        args=[str(harness.RESTRICTED_BACKEND)],
        env=live_env.backend_launch_environment(27161, password, "helper"),
        cwd=str(live_env.BACKEND_RUNTIME),
    )
    print(f"observer cwd={observer_params.cwd}")
    print(f"harness  cwd={harness_params.cwd}")
    await try_read("observer_params", observer_params)
    await try_read("harness_params", harness_params)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
