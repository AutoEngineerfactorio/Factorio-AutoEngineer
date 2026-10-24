import asyncio
import json
import os
import sys

from autoengineer_config import mcp_parameters
from catalog_assembly import CatalogAssemblyError, assemble_catalog
from dashboard_chunk_grid import chunks_for_viewport, validate_chunk_request
from dashboard_feed import (
    PREFIX,
    VIEWPORT_PREFIX,
    DashboardFeed,
    decode_viewport_request,
)
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from session_safety import ConsoleControl

VIEW_ARGUMENTS = {"catalogPage", "catalogPageSize", "mapChunkX", "mapChunkY"}

MAX_CHUNKS_PER_CYCLE = 8
"""Upper bound on chunks observed in one observer cycle."""


class ViewOnly:
    """Read-only wrapper around the restricted backend view tool."""

    def __init__(self, session):
        self.session = session

    async def call_tool(self, name, arguments=None):
        args = dict(arguments or {})
        if name != "autoengineer_view" or set(args) - VIEW_ARGUMENTS:
            raise PermissionError("Observer accepts only bounded display reads")
        page = args.get("catalogPage", 1)
        page_size = args.get("catalogPageSize", 16)
        if type(page) is not int or not 1 <= page <= 10000:
            raise ValueError("Invalid catalog page")
        if type(page_size) is not int or not 1 <= page_size <= 32:
            raise ValueError("Invalid catalog page size")
        chunk_x = args.get("mapChunkX")
        chunk_y = args.get("mapChunkY")
        if (chunk_x is None) != (chunk_y is None):
            raise ValueError("Map chunk coordinates must be given together")
        if chunk_x is not None:
            validate_chunk_request((chunk_x, chunk_y))
        return await self.session.call_tool(name, arguments=args)


class ViewportRequests:
    """Latest-wins viewport request channel.

    The dashboard sends the world rectangle it currently shows. Only the most
    recent request matters, so a pan that outruns the observer supersedes the
    older request instead of queueing it. That keeps the observer bounded and
    makes an obsolete request cost nothing.
    """

    def __init__(self):
        self._pending: dict | None = None
        self._event = asyncio.Event()

    def offer(self, request: dict) -> None:
        self._pending = request
        self._event.set()

    def take(self) -> dict | None:
        request = self._pending
        self._pending = None
        self._event.clear()
        return request

    async def wait(self, timeout: float) -> dict | None:
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except TimeoutError:
            return None
        return self.take()

    def read_line(self, line: str) -> bool:
        """Accept a viewport request line. Return True when it was one."""
        if not isinstance(line, str) or not line.startswith(VIEWPORT_PREFIX):
            return False
        try:
            request = decode_viewport_request(line)
        except ValueError:
            # A malformed request is ignored; the observer keeps its current
            # viewport rather than guessing a new one.
            return True
        if request is not None:
            self.offer(request)
        return True


def start_viewport_reader(stream, requests: ViewportRequests, control=None) -> None:
    """Route viewport and safety commands through ONE stdin reader."""
    import threading

    loop = asyncio.get_running_loop()

    def read():
        try:
            while True:
                line = stream.readline()
                if line.startswith(VIEWPORT_PREFIX):
                    # asyncio.Event and the latest-wins mailbox belong to the
                    # event-loop thread, never the background stdin thread.
                    loop.call_soon_threadsafe(requests.read_line, line)
                    continue
                if control is not None:
                    loop.call_soon_threadsafe(control.feed, line)
                if not line:
                    return
        except (OSError, ValueError):
            if control is not None:
                loop.call_soon_threadsafe(control.stop.set)

    threading.Thread(target=read, daemon=True).start()


def chunk_arguments(chunk_x: int, chunk_y: int) -> dict:
    """Return the bounded backend arguments for one aligned chunk."""
    return {"mapChunkX": chunk_x, "mapChunkY": chunk_y}


async def observe_chunk(session, chunk_x: int, chunk_y: int) -> dict | None:
    """Observe exactly one aligned map chunk."""
    response = await asyncio.wait_for(
        session.call_tool("autoengineer_view", arguments=chunk_arguments(chunk_x, chunk_y)),
        12,
    )
    if response.is_error:
        return None
    for part in response.content:
        if part.type == "text":
            raw = json.loads(part.text)
            return raw if isinstance(raw, dict) else None
    return None


async def observe(session, control, interval: float = 2, requests=None):
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
            await observe_viewport(session, feed, control, requests)
        except Exception as exc:
            print(f'Observer read error: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
            print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
        try:
            await asyncio.wait_for(control.stop.wait(), interval)
        except TimeoutError:
            pass


async def observe_viewport(session, feed, control, requests) -> None:
    """Observe the chunks the dashboard is currently showing.

    Only chunks that are missing, stale or partial are requested, so a
    viewport that was already observed is not fetched again. A newer viewport
    request supersedes the older one before any further request is made.
    """
    if requests is None:
        return
    request = requests.take()
    if request is None:
        return
    center = request["center"]
    radius = request["radius"]
    wanted = chunks_for_viewport(
        center["x"],
        center["y"],
        radius["x"],
        radius["y"],
        limit=request["limit"],
    )
    outstanding = []
    for chunk_x, chunk_y in wanted:
        if control.stop.is_set():
            return
        if not feed.cache.needs_refresh(chunk_x, chunk_y):
            continue
        if len(outstanding) >= MAX_CHUNKS_PER_CYCLE:
            break
        outstanding.append((chunk_x, chunk_y))
    for chunk_x, chunk_y in outstanding:
        if control.stop.is_set():
            return
        # A newer viewport request supersedes the remaining chunks.
        if requests._pending is not None:
            # Preserve the newest viewport for the next cycle. Consuming it
            # here caused panned regions never to be fetched.
            return
        try:
            raw = await observe_chunk(session, chunk_x, chunk_y)
        except Exception:
            raw = None
        if raw is None:
            continue
        try:
            feed.publish(raw)
        except ValueError:
            continue


async def main():
    os.environ["AUTOENGINEER_MODE"] = "helper"
    control = ConsoleControl()
    requests = ViewportRequests()
    start_viewport_reader(sys.stdin, requests, control)
    while not control.stop.is_set():
        try:
            async with stdio_client(mcp_parameters()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    await observe(ViewOnly(session), control, requests=requests)
        except Exception:
            print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
            try:
                await asyncio.wait_for(control.stop.wait(), 3)
            except TimeoutError:
                pass


if __name__ == "__main__":
    asyncio.run(main())
