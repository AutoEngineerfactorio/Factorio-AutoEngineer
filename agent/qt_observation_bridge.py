"""The Qt dashboard's bridge to the real observation path.

The dashboard must show **real** Factorio observations. The path that
delivers them already exists and is not re-implemented here:

    Factorio mod -> restricted C# backend -> observation coordinator/cache
                 -> validated UI frame -> Qt dashboard

This module is the last hop. It **reuses** the R09 observation coordinator
and service, so the deduplication, the validated cache, the request budgets
and the bounded backoff all stay in effect. It adds no tool, no argument and
no gameplay capability.

Four rules define the bridge:

* **No gameplay write.** The bridge only ever asks for the two read-only
  backend tools the restricted backend already allows. It never issues Lua,
  never issues RCON and never touches a save.
* **No UI blocking.** Every request runs on a worker thread through the
  existing :class:`~observation_service.ObservationService`, and the result
  is handed back to the UI thread as a plain object. The UI thread never
  waits for the game.
* **No full-catalog polling.** The frequent poll uses the cheap status and
  telemetry requests. The recipe catalog is requested on demand only, so a
  telemetry refresh never walks the catalog.
* **No fabricated data.** A coordinator observation is translated into the
  dashboard's own truthfulness states: *observed*, *stale*, *partial* or
  *unavailable*. A value that was never observed stays unknown.

The module deliberately contains **no Qt import**. It is pure logic, so the
whole path is verifiable offline, without a display server and without a
running Factorio.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from observation_coordinator import (
    CATALOG,
    INVENTORY,
    MAP,
    STATUS,
    TELEMETRY,
    catalog_request,
    inventory_request,
    map_request,
    status_request,
    telemetry_request,
)
from observation_coordinator import (
    Observation as CoordinatorObservation,
)
from performance_governor import guard_from_settings
from qt_observation import (
    OBSERVED,
    STALE,
    UNAVAILABLE,
    Observation,
)
from runtime_settings import observation_interval

#: The kinds the bridge polls. The catalog is **not** in this list: a
#: telemetry refresh must never walk the recipe catalog.
POLLED_KINDS: tuple[str, ...] = (STATUS, TELEMETRY)

#: The default pause between two poll rounds, in seconds.
DEFAULT_INTERVAL = 2.0

#: The default number of frames the coalescer remembers.
DEFAULT_COALESCE_WINDOW = 8


@dataclass(frozen=True)
class UiFrame:
    """One validated frame the dashboard can display.

    The frame carries the truthfulness of every part of it, so the UI can
    distinguish a **disconnected**, an **unavailable**, a **stale**, a
    **partial**, an **observed** and an **estimated** value.
    """

    kind: str
    value: Any = None
    state: str = UNAVAILABLE
    detail: str = "Not observed"
    tick: int | None = None
    age_seconds: float = float("inf")
    partial: bool = False
    source: str = ""
    observed_at: float = 0.0
    derived_ups: float | None = None

    @property
    def known(self) -> bool:
        """Whether this frame carries a real value."""
        return self.value is not None and self.state != UNAVAILABLE

    @property
    def observed(self) -> bool:
        """Whether this frame is a current, fresh observation."""
        return self.state == OBSERVED

    @property
    def stale(self) -> bool:
        """Whether this frame is an aged-out observation."""
        return self.state == STALE

    @property
    def disconnected(self) -> bool:
        """Whether the observer reported that it is not connected."""
        return self.state == UNAVAILABLE and "disconnect" in self.detail.lower()

    def display(self, formatter=None) -> str:
        """Return the text the interface shows for this frame."""
        return Observation(
            value=self.value, state=self.state, detail=self.detail,
            observed_at=self.observed_at, age_seconds=self.age_seconds,
            source=self.source,
        ).display(formatter)

    def badge(self) -> str:
        """Return the short state badge for this frame."""
        return Observation(
            value=self.value, state=self.state,
        ).badge()


@dataclass
class BridgeStats:
    """A bounded summary of what the bridge has done."""

    polls: int = 0
    emitted: int = 0
    coalesced: int = 0
    rejected_out_of_order: int = 0
    failures: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return the summary as a plain mapping."""
        return {
            "polls": self.polls,
            "emitted": self.emitted,
            "coalesced": self.coalesced,
            "rejected_out_of_order": self.rejected_out_of_order,
            "failures": self.failures,
        }


class FrameCoalescer:
    """Suppresses frames that say nothing new.

    The observation coordinator already caches, so a fresh cached
    observation costs no request. The coalescer answers the remaining
    question: when the coordinator does hand back the **same** value twice,
    the dashboard must not redraw for it.

    The window is bounded, so a long-running session cannot grow the
    remembered fingerprints without limit.
    """

    def __init__(self, window: int = DEFAULT_COALESCE_WINDOW):
        if window < 1:
            raise ValueError("The coalesce window must be positive")
        self.window = window
        self._seen: list[str] = []

    @staticmethod
    def fingerprint(kind: str, value: Any, tick: int | None) -> str:
        """Return the fingerprint of one frame."""
        try:
            body = json.dumps(value, sort_keys=True, default=str,
                               allow_nan=False)
        except (TypeError, ValueError):
            body = repr(value)
        return f"{kind}|{tick}|{body}"

    def accept(self, kind: str, value: Any, tick: int | None) -> bool:
        """Whether a frame says something new.

        A frame whose fingerprint is already in the window is **not**
        accepted, so the caller can skip the redraw.
        """
        mark = self.fingerprint(kind, value, tick)
        if mark in self._seen:
            return False
        self._seen.append(mark)
        while len(self._seen) > self.window:
            self._seen.pop(0)
        return True

    def reset(self) -> None:
        """Forget every remembered fingerprint."""
        self._seen.clear()


def frame_tick(value: Any) -> int | None:
    """Return the game tick of an observed payload, when it has one.

    The tick is what orders two frames. A payload without a tick cannot be
    ordered, so it is reported as ``None``.
    """
    if not isinstance(value, Mapping):
        return None
    for key in ("tick", "game_tick", "gameTick"):
        raw = value.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float) and raw.is_integer():
            return int(raw)
    return None


def translate(observation: CoordinatorObservation, *,
              source: str = "") -> UiFrame:
    """Turn a coordinator observation into a displayable frame.

    The coordinator reports a value as **stale** when it could not be
    refreshed and as **unknown** when it was never observed. Both states are
    carried through; neither is turned into a current value.
    """
    age = observation.age()
    if not observation.known:
        reason = observation.reason or "Not observed"
        detail = "Disconnected" if "disconnect" in reason.lower() else reason
        return UiFrame(
            kind=observation.kind, value=None, state=UNAVAILABLE,
            detail=detail, age_seconds=age, source=source or observation.kind)
    value = observation.value
    tick = frame_tick(value)
    if observation.stale:
        detail = observation.reason or f"Last observed {age:.0f}s ago"
        state = STALE
    else:
        detail = "Observed"
        state = OBSERVED
    if observation.partial:
        detail = f"{detail} - partial coverage"
    return UiFrame(
        kind=observation.kind, value=value, state=state, detail=detail,
        tick=tick, age_seconds=age, partial=observation.partial,
        source=source or observation.kind, observed_at=observation.observed_at)


class ObservationBridge:
    """Polls the shared coordinator and hands validated frames to the UI.

    The bridge owns **no** transport. The session it polls is supplied by
    the caller, and the only tools it ever names are the two read-only
    ones the restricted backend already allows.
    """

    def __init__(self, service: Any = None, *,
                 interval: float | None = None,
                 coalescer: FrameCoalescer | None = None,
                 clock: Callable[[], float] = time.monotonic):
        if interval is None:
            # The observation interval comes from the Settings, so the
            # screen really controls how often the game is polled.
            interval = observation_interval()
        poll_interval = float(interval)
        if poll_interval <= 0:
            raise ValueError("The poll interval must be positive")
        if service is None:
            # A bridge with no service can never observe anything. That is a
            # misconfiguration, so it is refused here rather than turning
            # into an endless stream of empty frames.
            raise ValueError("The bridge has no observation service")
        self.service = service
        self.interval = poll_interval
        self.coalescer = coalescer or FrameCoalescer()
        self.clock = clock
        self.stats = BridgeStats()
        # The guard uses the configured UPS thresholds, so the Settings
        # really change when the background work is reduced.
        self.ups_guard = guard_from_settings()
        self.recommended_interval = max(self.interval, self.ups_guard.budget().telemetry_seconds)
        self._last_tick: int | None = None
        self._last_ticks: dict[str, int] = {}
        self._status_current = False
        self._status_epoch = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._catalog_request: tuple[int, int] | None = None
        self._catalog_event = threading.Event()
        self._catalog_frame: UiFrame | None = None
        self._catalog_auto = False
        self._catalog_generation = 0
        self._catalog_serving = False
        self._last_inventory_poll = self.clock()
        self._pending_tools: set[Any] = set()
        self._map_requests: list[tuple[int, int]] = []
        self._last_map_poll = float("-inf")

    # -- ordering --------------------------------------------------------

    def accept_tick(self, tick: int | None, kind: str = STATUS) -> bool:
        """Whether a frame with this tick may be shown.

        A frame whose tick is **older** than the newest one already shown
        is rejected: an out-of-order frame must never overwrite a newer
        observation. A frame without a tick cannot be ordered, so it is
        accepted and the ordering is left to the next frame that has one.
        """
        if tick is None:
            return True
        with self._lock:
            previous = self._last_ticks.get(kind)
            if previous is not None and tick < previous:
                self.stats.rejected_out_of_order += 1
                return False
            self._last_ticks[kind] = tick
            if kind == STATUS:
                self._last_tick = tick
            return True

    def reset_ordering(self) -> None:
        """Forget the newest tick, for a reconnect or a telemetry reset."""
        with self._lock:
            self._last_tick = None
            self._last_ticks.clear()
            self.coalescer.reset()

    # -- polling ---------------------------------------------------------

    def update_poll_budget(self, frame: UiFrame) -> None:
        """Slow optional telemetry polling when observed game UPS degrades.

        Reuses the already-received STATUS frame; does not create a second
        RCON poller. Unknown/disconnected status is conservatively slow.
        """
        if frame.kind != STATUS:
            return
        if not frame.observed or type(frame.tick) is not int:
            if self._status_current:
                self._status_epoch += 1
                self.reset_ordering()
            self._status_current = False
            self.ups_guard.reset()
        else:
            self._status_current = True
            try:
                self.ups_guard.observe(frame.tick, self.clock())
            except ValueError:
                self.ups_guard.reset()
        self.recommended_interval = max(
            self.interval, self.ups_guard.budget().telemetry_seconds)

    async def poll_once(self, session: Any) -> list[UiFrame]:
        """Poll every polled kind once and return the accepted frames.

        The catalog is **not** polled here. A telemetry refresh therefore
        never walks the recipe catalog.

        A request that raises does not abort the round. It becomes an
        **unknown** frame, so the dashboard shows that the value is
        missing rather than keeping a misleading number or crashing.
        """
        frames: list[UiFrame] = []
        self.stats.polls += 1
        for kind in POLLED_KINDS:
            if kind == STATUS:
                tool, arguments = status_request()
            else:
                if not self._status_current:
                    frames.append(UiFrame(kind=kind, value=None, state=UNAVAILABLE,
                                          detail="Current world status unavailable"))
                    continue
                tool, arguments = telemetry_request()
            try:
                observation = await self._observe(session, tool, arguments, kind)
            except Exception as exc:  # noqa: BLE001 - a failure is reported
                self.stats.failures += 1
                failed = UiFrame(
                    kind=kind, value=None, state=UNAVAILABLE,
                    detail=f"Observation failed: {type(exc).__name__}",
                    source=tool)
                self.update_poll_budget(failed)
                frames.append(failed)
                continue
            frame = translate(observation, source=tool)
            self.update_poll_budget(frame)
            if frame.kind == STATUS and frame.observed:
                frame = replace(frame, derived_ups=self.ups_guard.budget().estimated_ups)
            if not frame.observed:
                # A failed, backed-off or over-budget request is reported as
                # unknown or stale. It is never shown as a current value.
                if observation.reason:
                    self.stats.failures += 1
                if frame.disconnected:
                    self.reset_ordering()
                frames.append(frame)
                continue
            if not self.accept_tick(frame.tick, frame.kind):
                continue
            coalesce_value = (frame.value, frame.derived_ups) if frame.kind == STATUS else frame.value
            if not self.coalescer.accept(frame.kind, coalesce_value, frame.tick):
                self.stats.coalesced += 1
                continue
            self.stats.emitted += 1
            frames.append(frame)
        inventory_period = max(10.0, self.recommended_interval * 3)
        if (self.clock() - self._last_inventory_poll >= inventory_period
                and self._status_current and self._last_tick is not None
                and not any(frame.disconnected for frame in frames)):
            self._last_inventory_poll = self.clock()
            frames.append(await self.poll_inventory(session, machine_page_size=8,
                                                    logistics_page_size=8))
        return frames

    async def _observe(self, session: Any, tool: str, arguments: dict[str, Any],
                       kind: str, *, key: tuple[Any, ...] | None = None
                       ) -> CoordinatorObservation:
        """Ask the coordinator for one observation."""
        if self.service is None:
            raise ValueError("The bridge has no observation service")
        if kind != STATUS:
            key = (kind, "status_epoch", self._status_epoch,
                   key or (tool, json.dumps(arguments, sort_keys=True)))
        return await self.service.observe_tool(
            session, tool, arguments, kind=kind, key=key)

    async def poll_catalog(self, session: Any, *, page: int = 1,
                           page_size: int = 32) -> UiFrame:
        """Request one bounded catalog page on demand.

        The frequent poll never walks the catalog. This explicit method is
        used by the Recipes & Research workspace when the user asks for the
        authoritative observed catalog. It still goes through the shared
        coordinator, so the request is deduplicated, cached and bounded.
        """
        tool = "autoengineer_view"
        try:
            tool, arguments = catalog_request(page=page, page_size=page_size)
            observation = await self._observe(
                session, tool, arguments, CATALOG,
                key=(CATALOG, self._catalog_generation, page, page_size))
        except Exception as exc:  # noqa: BLE001 - a failure is reported
            self.stats.failures += 1
            return UiFrame(
                kind=CATALOG, value=None, state=UNAVAILABLE,
                detail=f"Observation failed: {type(exc).__name__}", source=tool)
        return translate(observation, source=tool)

    # -- the user-driven catalog path ------------------------------------

    async def poll_inventory(self, session: Any, *, machine_page: int = 1,
                             machine_page_size: int = 16,
                             logistics_page: int = 1,
                             logistics_page_size: int = 16) -> UiFrame:
        """Request one bounded inventory and logistics observation.

        This request walks bounded entities. Besides explicit paging, the
        bridge requests a small first page at most once per ten seconds,
        with longer intervals under low UPS. It shares the coordinator,
        cache and request budgets with the other read-only observations.
        """
        tool = "autoengineer_inventory"
        try:
            tool, arguments = inventory_request(
                machine_page=machine_page, machine_page_size=machine_page_size,
                logistics_page=logistics_page,
                logistics_page_size=logistics_page_size)
            observation = await self._observe(session, tool, arguments,
                                              INVENTORY)
        except Exception as exc:  # noqa: BLE001 - a failure is reported
            self.stats.failures += 1
            return UiFrame(
                kind=INVENTORY, value=None, state=UNAVAILABLE,
                detail=f"Observation failed: {type(exc).__name__}", source=tool)
        return translate(observation, source=tool)

    def request_catalog(self, page: int = 1, *, page_size: int = 16,
                        refresh: bool = False) -> bool:
        """Ask the worker thread for one catalog page.

        This is the path the Recipes & Research workspace uses when the
        user presses **Refresh** or **Load more**. The request is queued
        for the worker thread, so the interface never waits for the game.

        A request for a page that is already in flight is **coalesced**:
        the second press does not start a second backend request. The
        method returns whether a new request was started.
        """
        if type(page) is not int or page < 1:
            raise ValueError("Invalid catalog page")
        if type(page_size) is not int or not 1 <= page_size <= 128:
            raise ValueError("Invalid catalog page size")
        with self._lock:
            if refresh:
                self._catalog_request = None
                self._catalog_auto = True
                self._catalog_generation += 1
            if self._catalog_request is not None or (self._catalog_serving and not refresh):
                self.stats.coalesced += 1
                return False
            self._catalog_request = (int(page), int(page_size))
            self._catalog_event.set()
        return True

    def _take_catalog_request(self) -> tuple[int, int] | None:
        """Take the pending catalog request, if there is one."""
        with self._lock:
            request = self._catalog_request
            self._catalog_request = None
            return request

    async def serve_catalog_request(self, session: Any) -> UiFrame | None:
        """Serve one pending catalog request on the worker thread.

        The method returns ``None`` when nothing was requested, so the
        worker loop can simply call it every round.
        """
        request = self._take_catalog_request()
        if request is None:
            return None
        page, page_size = request
        generation = self._catalog_generation
        self._catalog_serving = True
        try:
            frame = await self.poll_catalog(session, page=page, page_size=page_size)
        finally:
            self._catalog_serving = False
        if (self._catalog_auto and generation == self._catalog_generation
                and not frame.observed and frame.detail in
                {"budget_exhausted", "in_flight", "concurrency_limited", "backoff"}):
            self.request_catalog(page, page_size=page_size)
            return None
        self._catalog_frame = frame
        if self._catalog_auto and generation == self._catalog_generation:
            status = frame.value.get("catalog_status", {}) if isinstance(frame.value, Mapping) else {}
            total = status.get("total_pages")
            if frame.observed and type(total) is int and page < total and page < 1024:
                self.request_catalog(page + 1, page_size=page_size)
            else:
                self._catalog_auto = False
        return frame

    def request_map(self, chunks: list[tuple[int, int]]) -> None:
        """Replace pending work with at most sixteen visible, validated chunks."""
        selected = list(dict.fromkeys(chunks[:16]))
        for x, y in selected:
            map_request(x, y)
        with self._lock:
            self._map_requests = selected

    async def serve_map_request(self, session: Any) -> UiFrame | None:
        """Read one visible chunk under the shared UPS and request budgets."""
        if not self._status_current:
            return None
        now = self.clock()
        if now - self._last_map_poll < self.ups_guard.budget().map_seconds:
            return None
        with self._lock:
            if not self._map_requests:
                return None
            chunk = self._map_requests.pop(0)
        self._last_map_poll = now
        tool, arguments = map_request(*chunk)
        try:
            observation = await self._observe(session, tool, arguments, MAP)
            return translate(observation, source=tool)
        except Exception as exc:
            self.stats.failures += 1
            return UiFrame(kind=MAP, value=None, state=UNAVAILABLE,
                           detail=f"Map observation failed: {type(exc).__name__}")

    # -- the worker thread -----------------------------------------------

    def start(self, session: Any, on_frame: Callable[[UiFrame], None],
              *, on_error: Callable[[BaseException], None] | None = None
              ) -> threading.Thread:
        """Start the polling worker and return its thread.

        The worker runs its own event loop, so the caller's event loop and
        the UI thread are never blocked by a game round trip.
        """
        import asyncio
        import inspect

        try:
            owner_loop = asyncio.get_running_loop()
        except RuntimeError:
            owner_loop = None
        supplied_session = session
        bridge = self
        if owner_loop is not None:
            class BoundSession:
                async def call_tool(self, *args, **kwargs):
                    async def invoke():
                        response = supplied_session.call_tool(*args, **kwargs)
                        return await response if inspect.isawaitable(response) else response

                    future = asyncio.run_coroutine_threadsafe(invoke(), owner_loop)
                    with bridge._lock:
                        bridge._pending_tools.add(future)
                        if bridge._stop.is_set():
                            future.cancel()
                    try:
                        return await asyncio.wrap_future(future)
                    finally:
                        with bridge._lock:
                            bridge._pending_tools.discard(future)
            session = BoundSession()
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("The observation bridge is already running")
        self._stop.clear()

        def worker() -> None:
            import asyncio

            async def run() -> None:
                next_poll = next_catalog = 0.0
                while not self._stop.is_set():
                    try:
                        frames: list[UiFrame] = []
                        catalog = map_frame = None
                        if self.clock() >= next_poll:
                            frames = await self.poll_once(session)
                            next_poll = self.clock() + self.recommended_interval
                        if self.clock() >= next_catalog:
                            catalog = await self.serve_catalog_request(session)
                            # Leave room for cheap status/telemetry within the
                            # shared 120/minute allowance, including retries.
                            next_catalog = self.clock() + 1.5
                        map_frame = await self.serve_map_request(session)
                    except BaseException as exc:  # noqa: BLE001
                        self.stats.failures += 1
                        if on_error is not None:
                            on_error(exc)
                    else:
                        for frame in frames:
                            on_frame(frame)
                        if catalog is not None:
                            on_frame(catalog)
                        if map_frame is not None:
                            on_frame(map_frame)
                    # Wake regularly for queued work without repolling status
                    # on every catalog page or spinning during a budget pause.
                    self._catalog_event.clear()
                    if self._stop.wait(0.05):
                        return

            asyncio.run(run())

        thread = threading.Thread(
            target=worker, name="ae-qt-observation", daemon=True)
        self._thread = thread
        thread.start()
        return thread

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the polling worker and release the service."""
        self._stop.set()
        with self._lock:
            pending = list(self._pending_tools)
        for future in pending:
            future.cancel()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout)
        self._thread = None
        service = self.service
        if service is not None and hasattr(service, "close"):
            service.close()


__all__ = [
    "DEFAULT_COALESCE_WINDOW",
    "DEFAULT_INTERVAL",
    "POLLED_KINDS",
    "BridgeStats",
    "FrameCoalescer",
    "ObservationBridge",
    "UiFrame",
    "frame_tick",
    "translate",
]
