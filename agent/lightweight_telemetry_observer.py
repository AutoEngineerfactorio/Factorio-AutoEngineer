"""Map-free, bounded read-only telemetry observer. No recipe or terrain queries."""
import asyncio
import json
import os

from autoengineer_config import mcp_parameters
from dashboard_feed import PREFIX
from mcp import ClientSession
from mcp.client.stdio import stdio_client


async def observe(session, interval=4.0):
    while True:
        try:
            response = await asyncio.wait_for(
                session.call_tool("autoengineer_telemetry", arguments={}), timeout=8
            )
            if response.is_error:
                raise ValueError("Telemetry read failed")
            raw = next(json.loads(p.text) for p in response.content if p.type == "text")
            if not isinstance(raw, dict) or raw.get("status") != "ok":
                raise ValueError("Telemetry unavailable")
            # Keep bounded samples separately labelled, never as full production history.
            print(PREFIX + json.dumps({"schema": 1, "telemetry_only": True, **raw}, separators=(",", ":")), flush=True)
        except Exception as exc:
            print(f"Telemetry read error: {type(exc).__name__}: {exc}", flush=True)
            print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
        await asyncio.sleep(interval)


async def main():
    os.environ["AUTOENGINEER_MODE"] = "helper"
    while True:
        try:
            async with stdio_client(mcp_parameters()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await observe(session)
        except Exception:
            print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
            await asyncio.sleep(4)


if __name__ == "__main__":
    asyncio.run(main())
