"""Optional read-only MCP observer for an RCON-enabled Factorio session."""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from autoengineer_config import mcp_parameters
from mcp import ClientSession, stdio_client
from observation_service import ObservationService
from qt_observation_bridge import ObservationBridge


class LocalGameObserver:
    """Own an isolated MCP connection while reusing the bounded UI bridge."""

    def __init__(self, on_ready: Callable[[ObservationBridge], None],
                 on_frame: Callable[[Any], None],
                 on_error: Callable[[BaseException], None]) -> None:
        self.on_ready = on_ready
        self.on_frame = on_frame
        self.on_error = on_error
        self.stop_event = threading.Event()
        self.bridge: ObservationBridge | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._worker, daemon=True,
                                       name="ae-single-player-observer")
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _worker(self) -> None:
        async def run() -> None:
            # The session lives in this event loop. ObservationBridge
            # proxies tool requests back to this loop from its worker pool.
            async with stdio_client(mcp_parameters()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    bridge = ObservationBridge(ObservationService())
                    self.bridge = bridge
                    bridge.start(session, self.on_frame, on_error=self.on_error)
                    self.on_ready(bridge)
                    try:
                        while not self.stop_event.is_set():
                            await asyncio.sleep(0.25)
                    finally:
                        bridge.stop()
                        self.bridge = None

        try:
            asyncio.run(run())
        except Exception as error:
            if not self.stop_event.is_set():
                self.on_error(error)
