"""Independent read-only telemetry. Never arms a lease or dispatches an action."""
import asyncio
import json
import sys
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from autoengineer_config import mcp_parameters
from dashboard_feed import DashboardFeed, PREFIX
from session_safety import ConsoleControl


class ViewOnly:
    def __init__(self, session):
        self.session = session

    async def call_tool(self, name, arguments=None):
        if name != 'autoengineer_view' or arguments:
            raise PermissionError('Observer accepts only argument-free display reads')
        return await self.session.call_tool(name, arguments={})


async def observe(session, control, interval=2):
    feed = DashboardFeed()
    while not control.stop.is_set():
        try:
            response = await asyncio.wait_for(session.call_tool('autoengineer_view'), 2)
            if response.is_error:
                raise ValueError('Display unavailable')
            raw = next(json.loads(p.text) for p in response.content if p.type == 'text')
            feed.publish(raw)
        except Exception:
            print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
        try:
            await asyncio.wait_for(control.stop.wait(), interval)
        except TimeoutError:
            pass


async def main():
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


if __name__ == '__main__':
    asyncio.run(main())
