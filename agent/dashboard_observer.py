"""Independent read-only telemetry. Never arms a lease or dispatches an action."""

import asyncio
import json
import os
import sys

from autoengineer_config import mcp_parameters
from catalog_assembly import CatalogAssemblyError, assemble_catalog
from dashboard_feed import PREFIX, DashboardFeed
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from session_safety import ConsoleControl


class ViewOnly:
    def __init__(self, session):
        self.session = session

    async def call_tool(self, name, arguments=None):
        args = dict(arguments or {})
        if name != "autoengineer_view" or set(args) - {"catalogPage", "catalogPageSize"}:
            raise PermissionError("Observer accepts only bounded display reads")
        page = args.get("catalogPage", 1)
        page_size = args.get("catalogPageSize", 16)
        if type(page) is not int or not 1 <= page <= 10000:
            raise ValueError("Invalid catalog page")
        if type(page_size) is not int or not 1 <= page_size <= 32:
            raise ValueError("Invalid catalog page size")
        return await self.session.call_tool(name, arguments=args)


async def observe(session, control, interval=2):
    feed = DashboardFeed()
    while not control.stop.is_set():
        try:
            response = await asyncio.wait_for(session.call_tool("autoengineer_view"), 12)
            if response.is_error:
                raise ValueError("Display unavailable")
            raw = next(json.loads(p.text) for p in response.content if p.type == "text")
            # Publish the bounded first-page observation immediately. Recipe catalog
            # assembly can take longer and must not block live telemetry readiness.
            feed.publish(raw)
            if isinstance(raw, dict) and isinstance(raw.get("catalog_status"), dict):
                if raw["catalog_status"].get("status") == "ok":
                    try:
                        raw = await assemble_catalog(session, raw, stop_event=control.stop)
                    except CatalogAssemblyError:
                        raw = dict(raw)
                        raw.pop("capabilities", None)
                        raw["catalog_status"] = dict(
                            raw["catalog_status"], status="assembly_failed"
                        )
            # The assembled catalog is a second optional update, not a prerequisite
            # for displaying the already validated live world observation.
            if isinstance(raw, dict) and raw.get('catalog_status', {}).get('status') in ('assembled', 'assembly_failed'):
                feed.publish(raw)
        except Exception as exc:
            print(f'Observer read error: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
            print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
        try:
            await asyncio.wait_for(control.stop.wait(), interval)
        except TimeoutError:
            pass


async def main():
    os.environ["AUTOENGINEER_MODE"] = "helper"
    control = ConsoleControl()
    control.start_reader(sys.stdin)
    while not control.stop.is_set():
        try:
            async with stdio_client(mcp_parameters()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await observe(ViewOnly(session), control)
        except Exception:
            print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
            try:
                await asyncio.wait_for(control.stop.wait(), 3)
            except TimeoutError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
