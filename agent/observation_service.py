"""The async face of the shared observation coordinator.

The coordinator in :mod:`observation_coordinator` is synchronous by design so
it can be tested offline. The active observers are ``asyncio`` tasks, so
this module is the thin bridge between the two.

The bridge keeps the game round trip off the event loop. The whole
coordinator call runs on a worker thread, and the request itself is awaited
on that same worker thread. Because the worker thread has no running event
loop of its own, the request coroutine is created and awaited there, which
is what ``asyncio`` requires.

The service adds nothing that widens a read. It only ever requests the
tools the restricted backend already allows, and it never issues a gameplay
command.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable

from observation_coordinator import (
    CATALOG,
    DEFAULT_TTL,
    MAP,
    STATUS,
    TELEMETRY,
    Observation,
    ObservationCoordinator,
    ObservationPending,
)
from runtime_settings import max_in_flight_limit, requests_per_minute_budget

#: How long one observation request may take before it is abandoned.
DEFAULT_REQUEST_TIMEOUT = 12.0

#: The observation kinds and their default freshness, from the coordinator.
_KIND_TTL = dict(DEFAULT_TTL)


class ObservationService:
    """One shared coordinator for every non-safety observation request."""

    def __init__(
        self,
        coordinator: ObservationCoordinator | None = None,
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        workers: int = 2,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Invalid observation request timeout")
        if workers < 1:
            raise ValueError("Invalid observation worker count")
        self.coordinator = coordinator or ObservationCoordinator(
            requests_per_minute=requests_per_minute_budget(),
            max_in_flight=max_in_flight_limit())
        self.timeout = timeout
        # One worker per permitted in-flight request, so the coordinator's
        # concurrency limit is the real limit.
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="ae-observation")

    def close(self) -> None:
        """Release the worker pool."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def observe(
        self,
        kind: str,
        factory: Callable[[], Awaitable[Any]],
        *,
        key: tuple[Any, ...] | None = None,
        ttl: float | None = None,
        allow_partial: bool = True,
    ) -> Observation:
        """Return the observation for ``kind``, fetching it when needed.

        ``factory`` builds the coroutine to run. It is called on a worker
        thread, so the coroutine is created and awaited in the same thread.

        A fresh cached observation is returned without calling the factory.
        A failed, backed-off or over-budget request returns the last known
        value marked **stale**, never as a current one.
        """
        lifetime = ttl if ttl is not None else _KIND_TTL.get(kind, 1.0)
        timeout = self.timeout

        def perform() -> Any:
            awaitable = factory()
            if not inspect.isawaitable(awaitable):
                # A synchronous stand-in is accepted, so a caller may pass
                # a plain value without wrapping it.
                return awaitable
            future = asyncio.run_coroutine_threadsafe(
                _await_with_timeout(awaitable, timeout), loop)
            try:
                return future.result(timeout=timeout + 1)
            except TimeoutError:
                future.cancel()
                raise

        def decide() -> Observation:
            # The coordinator is synchronous, so its whole decision runs on
            # the worker thread together with the request it may make.
            return self.coordinator.observe(
                kind,
                perform,
                key=key,
                ttl=lifetime,
                allow_partial=allow_partial,
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, decide)

    async def observe_tool(
        self,
        session: Any,
        tool: str,
        arguments: dict[str, Any],
        *,
        kind: str,
        key: tuple[Any, ...] | None = None,
        ttl: float | None = None,
        timeout: float | None = None,
    ) -> Observation:
        """Observe one backend tool through the coordinator."""
        limit = timeout if timeout is not None else self.timeout

        def factory() -> Awaitable[Any]:
            async def fetch() -> Any:
                response = session.call_tool(tool, arguments=arguments)
                # The MCP session is asynchronous, but a caller may supply a
                # synchronous stand-in, so both are accepted.
                if inspect.isawaitable(response):
                    response = await asyncio.wait_for(response, limit)
                if response.is_error:
                    raise ValueError(f"{tool} failed")
                for part in response.content:
                    if part.type == "text":
                        payload = json.loads(part.text)
                        if not isinstance(payload, dict):
                            raise ValueError("Observation must be a document")
                        if payload.get("status") == "pending":
                            if kind == CATALOG and payload.get("reason") == "catalog_building":
                                raise ObservationPending("catalog_building")
                            raise ValueError("Unexpected pending observation")
                        if payload.get("status") in ("unavailable", "error"):
                            raise ValueError("Backend observation unavailable")
                        return payload
                raise ValueError(f"{tool} returned no text")

            return fetch()

        if key is None:
            key = self.coordinator.key(
                kind, tool=tool,
                arguments=json.dumps(arguments, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False))
        return await self.observe(kind, factory, key=key, ttl=ttl)

    def stats(self) -> dict[str, Any]:
        """Return a bounded summary of the coordinator's state."""
        return self.coordinator.stats()


async def _await_with_timeout(awaitable: Awaitable[Any], timeout: float) -> Any:
    """Await one awaitable with a timeout."""
    return await asyncio.wait_for(awaitable, timeout)


__all__ = [
    "CATALOG",
    "MAP",
    "ObservationService",
    "STATUS",
    "TELEMETRY",
]
