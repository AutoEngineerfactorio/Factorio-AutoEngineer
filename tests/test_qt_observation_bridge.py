"""Regression tests for the Qt observation bridge.

The bridge is the last hop of the real observation path, so these tests
check that it:

* polls only the read-only kinds and never the recipe catalog;
* reuses the shared coordinator and service;
* keeps the dashboard's truthfulness states intact;
* coalesces repeated observations;
* rejects an out-of-order frame;
* never blocks the caller.

No game process, no save, no network. The bridge holds no Qt import, so
these tests run in the system Python without PySide6.
"""

import asyncio
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from observation_coordinator import (  # noqa: E402
    CATALOG,
    MAP,
    STATUS,
    TELEMETRY,
)
from observation_coordinator import (
    Observation as CoordinatorObservation,
)
from qt_observation import (  # noqa: E402
    OBSERVED,
    STALE,
    UNAVAILABLE,
)
from qt_observation_bridge import (  # noqa: E402
    POLLED_KINDS,
    FrameCoalescer,
    ObservationBridge,
    UiFrame,
    frame_tick,
    translate,
)


class FakeService:
    """A stand-in for the shared observation service.

    It records every request so a test can prove that the bridge asks for
    nothing it may not ask for.
    """

    def __init__(self, results=None):
        self.results = dict(results or {})
        self.requests = []
        self.closed = False

    async def observe_tool(self, session, tool, arguments, *, kind,
                           key=None, ttl=None, timeout=None):
        self.requests.append((tool, dict(arguments), kind))
        value = self.results.get(kind)
        if isinstance(value, Exception):
            raise value
        if value is None:
            return CoordinatorObservation(
                kind=kind, reason="never_observed")
        if isinstance(value, CoordinatorObservation):
            return value
        return CoordinatorObservation(kind=kind, value=value,
                                      observed_at=1000.0)

    def close(self):
        self.closed = True


def observed_value(tick, **extra):
    """Return a simple observed payload carrying a game tick."""
    return {"tick": tick, **extra}


class ObservationBridgeTests(unittest.TestCase):
    """The bridge polls, orders, coalesces and refuses to fabricate."""

    def test_observation_interval_backs_off_and_recovers_with_game_ups(self):
        """Observer reuses status frames; no extra game poller or catalog."""
        clock = [0.0]
        service = FakeService({STATUS: observed_value(0),
                               TELEMETRY: observed_value(0)})
        bridge = ObservationBridge(service, clock=lambda: clock[0], interval=2.0)
        self.assertEqual(bridge.recommended_interval, 4.0)
        for sample in range(4):
            clock[0] = sample * 4.0
            service.results[STATUS] = observed_value(sample * 240)
            service.results[TELEMETRY] = observed_value(sample * 240)
            asyncio.run(bridge.poll_once(object()))
        self.assertEqual(bridge.ups_guard.state, "healthy")
        self.assertEqual(bridge.recommended_interval, 2.0)
        clock[0] += 4.0
        service.results[STATUS] = observed_value(720)
        asyncio.run(bridge.poll_once(object()))
        self.assertEqual(bridge.ups_guard.state, "critical")
        self.assertEqual(bridge.recommended_interval, 10.0)
        service.results[STATUS] = CoordinatorObservation(
            kind=STATUS, reason="unavailable: disconnected")
        asyncio.run(bridge.poll_once(object()))
        self.assertEqual(bridge.ups_guard.state, "unknown")
        self.assertEqual(bridge.recommended_interval, 4.0)
        self.assertEqual({kind for _, _, kind in service.requests},
                         {STATUS, TELEMETRY, "inventory"})

    def test_status_transport_failure_restores_conservative_interval(self):
        clock = [0.0]
        service = FakeService({STATUS: observed_value(0), TELEMETRY: observed_value(0)})
        # The interval is pinned so the test checks the behaviour on a
        # transport failure, not the configured default.
        bridge = ObservationBridge(service, clock=lambda: clock[0], interval=2.0)
        for i in range(4):
            clock[0] = 4.0 * i
            service.results[STATUS] = observed_value(240 * i)
            service.results[TELEMETRY] = observed_value(240 * i)
            asyncio.run(bridge.poll_once(object()))
        self.assertEqual(bridge.recommended_interval, 2)
        service.results[STATUS] = ConnectionError("Disconnected")
        asyncio.run(bridge.poll_once(object()))
        self.assertEqual(bridge.recommended_interval, 4)
        self.assertEqual(bridge.ups_guard.state, "unknown")

    def test_the_catalog_is_never_polled(self):
        """A telemetry refresh must never walk the recipe catalog."""
        service = FakeService({STATUS: observed_value(1),
                               TELEMETRY: observed_value(1)})
        bridge = ObservationBridge(service)
        frames = asyncio.run(bridge.poll_once(object()))
        self.assertTrue(frames)
        for tool, arguments, kind in service.requests:
            self.assertNotEqual(kind, CATALOG)
            self.assertNotIn("catalogOnly", arguments)
            self.assertNotIn("catalogPage", arguments)

    def test_only_the_read_only_tools_are_requested(self):
        """The bridge names only the two read-only backend tools."""
        service = FakeService({STATUS: observed_value(1),
                               TELEMETRY: observed_value(1)})
        bridge = ObservationBridge(service)
        asyncio.run(bridge.poll_once(object()))
        tools = {tool for tool, _arguments, _kind in service.requests}
        self.assertEqual(tools, {"autoengineer_view", "autoengineer_telemetry"})

    def test_a_catalog_request_is_queued_for_the_worker(self):
        """The user-driven request is queued, not awaited on the UI thread."""
        service = FakeService({CATALOG: observed_value(1)})
        bridge = ObservationBridge(service)
        self.assertTrue(bridge.request_catalog(1))
        frame = asyncio.run(bridge.serve_catalog_request(object()))
        assert frame is not None
        self.assertEqual(frame.kind, CATALOG)
        self.assertEqual(
            [kind for _, _, kind in service.requests], [CATALOG])

    def test_a_second_request_is_coalesced(self):
        """A second press must not start a second backend request."""
        service = FakeService({CATALOG: observed_value(1)})
        bridge = ObservationBridge(service)
        self.assertTrue(bridge.request_catalog(1))
        self.assertFalse(bridge.request_catalog(2))
        self.assertEqual(bridge.stats.coalesced, 1)
        asyncio.run(bridge.serve_catalog_request(object()))
        self.assertEqual(len(service.requests), 1)

    def test_a_refresh_replaces_the_pending_request(self):
        """A refresh always asks for the first page again."""
        service = FakeService({CATALOG: observed_value(1)})
        bridge = ObservationBridge(service)
        self.assertTrue(bridge.request_catalog(5))
        self.assertTrue(bridge.request_catalog(1, refresh=True))
        asyncio.run(bridge.serve_catalog_request(object()))
        arguments = service.requests[0][1]
        self.assertEqual(arguments["catalogPage"], 1)

    def test_serving_without_a_request_returns_nothing(self):
        service = FakeService({CATALOG: observed_value(1)})
        bridge = ObservationBridge(service)
        self.assertIsNone(asyncio.run(bridge.serve_catalog_request(object())))
        self.assertEqual(service.requests, [])

    def test_the_requested_page_is_bounded(self):
        service = FakeService({CATALOG: observed_value(1)})
        bridge = ObservationBridge(service)
        with self.assertRaises(ValueError):
            bridge.request_catalog(0)
        with self.assertRaises(ValueError):
            bridge.request_catalog(1, page_size=999)

    def test_a_failed_catalog_request_is_reported_as_unavailable(self):
        service = FakeService({CATALOG: ConnectionError("Disconnected")})
        bridge = ObservationBridge(service)
        bridge.request_catalog(1)
        frame = asyncio.run(bridge.serve_catalog_request(object()))
        assert frame is not None
        self.assertFalse(frame.known)

    def test_the_catalog_is_requested_only_on_demand(self):
        """The Recipes workspace can request one bounded catalog page."""
        service = FakeService({
            CATALOG: {"tick": 9, "capabilities": {"recipes": []}},
        })
        bridge = ObservationBridge(service)
        frame = asyncio.run(bridge.poll_catalog(object(), page=2, page_size=32))
        self.assertTrue(frame.observed)
        self.assertEqual(len(service.requests), 1)
        tool, arguments, kind = service.requests[0]
        self.assertEqual(tool, "autoengineer_view")
        self.assertEqual(kind, CATALOG)
        self.assertEqual(arguments["catalogPage"], 2)
        self.assertEqual(arguments["catalogPageSize"], 32)
        self.assertTrue(arguments["catalogOnly"])

    def test_map_is_explicit_bounded_and_paused_without_current_status(self):
        service = FakeService({STATUS: observed_value(1), MAP: observed_value(1)})
        bridge = ObservationBridge(service)
        bridge.request_map([(x, 0) for x in range(30)])
        self.assertEqual(len(bridge._map_requests), 16)
        self.assertIsNone(asyncio.run(bridge.serve_map_request(object())))
        asyncio.run(bridge.poll_once(object()))
        frame = asyncio.run(bridge.serve_map_request(object()))
        self.assertIsNotNone(frame)
        request = service.requests[-1]
        self.assertEqual(request[2], MAP)
        self.assertEqual(request[1], {"mapChunkX": 0, "mapChunkY": 0})
        self.assertIsNone(asyncio.run(bridge.serve_map_request(object())))
        with self.assertRaises(ValueError):
            bridge.request_map([(100001, 0)])

    def test_an_invalid_catalog_request_is_refused(self):
        service = FakeService()
        bridge = ObservationBridge(service)
        frame = asyncio.run(bridge.poll_catalog(object(), page=0))
        self.assertFalse(frame.known)
        self.assertEqual(service.requests, [])

    def test_the_cheap_status_request_skips_the_catalog(self):
        """The frequent read must not ask for the catalog."""
        service = FakeService({STATUS: observed_value(1),
                               TELEMETRY: observed_value(1)})
        bridge = ObservationBridge(service)
        asyncio.run(bridge.poll_once(object()))
        for tool, arguments, kind in service.requests:
            if kind == STATUS:
                self.assertTrue(arguments.get("noCatalog"))

    def test_the_polled_kinds_are_the_read_only_ones(self):
        """The polled kinds never include the catalog or the map."""
        self.assertNotIn(CATALOG, POLLED_KINDS)
        self.assertNotIn(MAP, POLLED_KINDS)
        self.assertIn(STATUS, POLLED_KINDS)
        self.assertIn(TELEMETRY, POLLED_KINDS)

    def test_an_observed_frame_is_observed(self):
        """A fresh observation is shown as observed."""
        service = FakeService({STATUS: observed_value(7, ups=60.0),
                               TELEMETRY: observed_value(7)})
        bridge = ObservationBridge(service)
        frames = asyncio.run(bridge.poll_once(object()))
        self.assertTrue(any(frame.observed for frame in frames))
        for frame in frames:
            self.assertEqual(frame.state, OBSERVED)
            self.assertEqual(frame.tick, 7)

    def test_a_stale_observation_is_stale_and_keeps_its_value(self):
        """A value that aged out is stale, never current."""
        service = FakeService({
            STATUS: CoordinatorObservation(
                kind=STATUS, value=observed_value(3), observed_at=1.0,
                stale=True, reason="backoff"),
            TELEMETRY: observed_value(3),
        })
        bridge = ObservationBridge(service)
        frames = asyncio.run(bridge.poll_once(object()))
        stale = [frame for frame in frames if frame.stale]
        self.assertTrue(stale)
        self.assertEqual(stale[0].state, STALE)
        self.assertIsNotNone(stale[0].value)

    def test_failed_status_does_not_reseed_old_ticks_or_poll_telemetry(self):
        service = FakeService({STATUS: observed_value(100), TELEMETRY: observed_value(100)})
        bridge = ObservationBridge(service)
        asyncio.run(bridge.poll_once(object()))
        service.results[STATUS] = CoordinatorObservation(
            kind=STATUS, value=observed_value(100), observed_at=1,
            stale=True, reason="unavailable")
        before = len(service.requests)
        failed = asyncio.run(bridge.poll_once(object()))
        self.assertEqual(len(service.requests) - before, 1)
        self.assertFalse(any(frame.observed for frame in failed))
        self.assertIsNone(bridge._last_tick)
        service.results[STATUS] = observed_value(2)
        service.results[TELEMETRY] = observed_value(2)
        fresh = asyncio.run(bridge.poll_once(object()))
        self.assertEqual([frame.tick for frame in fresh], [2, 2])
        self.assertEqual(bridge._status_epoch, 1)

    def test_an_unknown_observation_is_unavailable(self):
        """A value that was never observed stays unknown."""
        service = FakeService({STATUS: None, TELEMETRY: None})
        bridge = ObservationBridge(service)
        frames = asyncio.run(bridge.poll_once(object()))
        self.assertTrue(frames)
        for frame in frames:
            self.assertEqual(frame.state, UNAVAILABLE)
            self.assertIsNone(frame.value)
            self.assertEqual(frame.display(), "—")

    def test_a_disconnect_is_reported_as_disconnected(self):
        """A confirmed disconnect is distinguishable from plain unknown."""
        service = FakeService({
            STATUS: CoordinatorObservation(
                kind=STATUS, reason="unavailable: disconnected"),
            TELEMETRY: observed_value(1),
        })
        bridge = ObservationBridge(service)
        frames = asyncio.run(bridge.poll_once(object()))
        self.assertTrue(any(frame.disconnected for frame in frames))

    def test_a_partial_observation_says_so(self):
        """A bounded observation is marked as partial coverage."""
        # The coordinator is what recognises a bounded payload, so the
        # observation it hands over carries the partial flag.
        service = FakeService({
            STATUS: CoordinatorObservation(
                kind=STATUS, value=observed_value(1), observed_at=1000.0,
                partial=True),
            TELEMETRY: observed_value(1),
        })
        bridge = ObservationBridge(service)
        frames = asyncio.run(bridge.poll_once(object()))
        partial = [frame for frame in frames if frame.partial]
        self.assertTrue(partial)
        self.assertIn("partial", partial[0].detail)

    def test_a_repeated_observation_is_coalesced(self):
        """The same value twice does not produce two frames."""
        service = FakeService({STATUS: observed_value(5),
                               TELEMETRY: observed_value(5)})
        bridge = ObservationBridge(service)
        first = asyncio.run(bridge.poll_once(object()))
        second = asyncio.run(bridge.poll_once(object()))
        self.assertTrue(first)
        self.assertEqual(second, [])
        self.assertEqual(bridge.stats.coalesced, 2)

    def test_an_out_of_order_frame_is_rejected(self):
        """A frame older than the newest one already shown is refused."""
        bridge = ObservationBridge(FakeService())
        self.assertTrue(bridge.accept_tick(100))
        self.assertFalse(bridge.accept_tick(50))
        self.assertEqual(bridge.stats.rejected_out_of_order, 1)
        self.assertTrue(bridge.accept_tick(150))

    def test_an_out_of_order_frame_never_reaches_the_ui(self):
        """A late frame is dropped before it is emitted."""
        service = FakeService({STATUS: observed_value(100),
                               TELEMETRY: observed_value(100)})
        bridge = ObservationBridge(service)
        first = asyncio.run(bridge.poll_once(object()))
        self.assertTrue(first)
        service.results[STATUS] = observed_value(50)
        service.results[TELEMETRY] = observed_value(50)
        second = asyncio.run(bridge.poll_once(object()))
        self.assertEqual(second, [])
        self.assertGreater(bridge.stats.rejected_out_of_order, 0)

    def test_a_reset_allows_a_new_observation_after_a_reconnect(self):
        """A reconnect starts the ordering over."""
        bridge = ObservationBridge(FakeService())
        bridge.accept_tick(100)
        self.assertFalse(bridge.accept_tick(50))
        bridge.reset_ordering()
        self.assertTrue(bridge.accept_tick(50))

    def test_a_frame_without_a_tick_cannot_be_ordered(self):
        """A payload without a tick is accepted, not rejected."""
        bridge = ObservationBridge(FakeService())
        self.assertIsNone(frame_tick({"ups": 60.0}))
        self.assertTrue(bridge.accept_tick(None))

    def test_the_tick_is_read_from_the_payload(self):
        """The game tick of a payload is found."""
        self.assertEqual(frame_tick({"tick": 12}), 12)
        self.assertEqual(frame_tick({"game_tick": 13}), 13)
        self.assertEqual(frame_tick({"tick": 14.0}), 14)
        self.assertIsNone(frame_tick({"tick": True}))
        self.assertIsNone(frame_tick("not a mapping"))

    def test_the_bridge_never_raises_on_a_service_failure(self):
        """A failing request becomes an unknown frame, not a crash."""
        service = FakeService({STATUS: RuntimeError("boom"),
                               TELEMETRY: observed_value(1)})
        bridge = ObservationBridge(service)
        frames = asyncio.run(bridge.poll_once(object()))
        self.assertTrue(any(not frame.known for frame in frames))

    def test_the_bridge_requests_the_session_it_was_given(self):
        """The bridge polls the caller's session, not one of its own."""
        service = FakeService({STATUS: observed_value(1),
                               TELEMETRY: observed_value(1)})
        bridge = ObservationBridge(service)
        session = object()
        asyncio.run(bridge.poll_once(session))
        self.assertEqual(len(service.requests), len(POLLED_KINDS))

    def test_a_bridge_without_a_service_is_refused(self):
        """A bridge with no service is a misconfiguration and is refused."""
        with self.assertRaises(ValueError):
            ObservationBridge(None)

    def test_the_interval_must_be_positive(self):
        with self.assertRaises(ValueError):
            ObservationBridge(FakeService(), interval=0)

    def test_stopping_releases_the_service(self):
        """Stopping the bridge closes the service it borrowed."""
        service = FakeService()
        bridge = ObservationBridge(service, interval=0.05)
        bridge.stop()
        self.assertTrue(service.closed)

    def test_the_worker_thread_polls_without_blocking_the_caller(self):
        """The caller returns immediately; the work happens elsewhere."""
        service = FakeService({STATUS: observed_value(1),
                               TELEMETRY: observed_value(1)})
        bridge = ObservationBridge(service, interval=0.05)
        seen = []
        arrived = threading.Event()

        def record(frame):
            seen.append(frame)
            arrived.set()

        thread = bridge.start(object(), record)
        try:
            self.assertTrue(thread.is_alive())
            self.assertNotEqual(thread.ident, threading.get_ident())
            # The worker reaches the game on its own thread; the caller
            # never waited for it.
            self.assertTrue(arrived.wait(5.0), "no frame arrived")
        finally:
            bridge.stop()
        self.assertTrue(seen)
        self.assertTrue(all(frame.observed for frame in seen))


class FrameCoalescerTests(unittest.TestCase):
    """The coalescer suppresses frames that say nothing new."""

    def test_a_new_value_is_accepted(self):
        coalescer = FrameCoalescer()
        self.assertTrue(coalescer.accept(STATUS, {"tick": 1}, 1))

    def test_the_same_value_is_refused(self):
        coalescer = FrameCoalescer()
        self.assertTrue(coalescer.accept(STATUS, {"tick": 1}, 1))
        self.assertFalse(coalescer.accept(STATUS, {"tick": 1}, 1))

    def test_a_different_value_is_accepted(self):
        coalescer = FrameCoalescer()
        self.assertTrue(coalescer.accept(STATUS, {"tick": 1}, 1))
        self.assertTrue(coalescer.accept(STATUS, {"tick": 2}, 2))

    def test_the_window_is_bounded(self):
        coalescer = FrameCoalescer(window=3)
        for tick in range(10):
            coalescer.accept(STATUS, {"tick": tick}, tick)
        self.assertEqual(len(coalescer._seen), 3)

    def test_the_window_must_be_positive(self):
        with self.assertRaises(ValueError):
            FrameCoalescer(window=0)

    def test_a_reset_forgets_everything(self):
        coalescer = FrameCoalescer()
        coalescer.accept(STATUS, {"tick": 1}, 1)
        coalescer.reset()
        self.assertTrue(coalescer.accept(STATUS, {"tick": 1}, 1))

    def test_a_value_that_cannot_be_serialised_is_still_coalesced(self):
        """An unserialisable value does not crash the coalescer."""
        coalescer = FrameCoalescer()
        self.assertTrue(coalescer.accept(STATUS, {"x": object()}, 1))
        self.assertFalse(coalescer.accept(STATUS, {"x": object()}, 1))


class TranslateTests(unittest.TestCase):
    """The translation keeps the truthfulness of the observation."""

    def test_an_unknown_observation_renders_as_an_em_dash(self):
        frame = translate(CoordinatorObservation(kind=STATUS,
                                                 reason="never_observed"))
        self.assertEqual(frame.state, UNAVAILABLE)
        self.assertEqual(frame.display(), "—")
        self.assertNotEqual(frame.display(), "0")

    def test_an_observed_value_is_shown(self):
        frame = translate(CoordinatorObservation(
            kind=TELEMETRY, value={"tick": 4, "ups": 60.0},
            observed_at=1000.0))
        self.assertEqual(frame.state, OBSERVED)
        self.assertTrue(frame.observed)
        self.assertEqual(frame.badge(), "observed")
        self.assertEqual(frame.tick, 4)

    def test_a_stale_value_keeps_its_number(self):
        frame = translate(CoordinatorObservation(
            kind=TELEMETRY, value={"tick": 4}, observed_at=1.0,
            stale=True, reason="backoff"))
        self.assertEqual(frame.state, STALE)
        self.assertIsNotNone(frame.value)
        self.assertEqual(frame.badge(), "stale")

    def test_the_bridge_frame_carries_the_source(self):
        frame = translate(CoordinatorObservation(
            kind=TELEMETRY, value={"tick": 1}), source="autoengineer_telemetry")
        self.assertEqual(frame.source, "autoengineer_telemetry")


class UiFrameTests(unittest.TestCase):
    """The frame's own predicates."""

    def test_an_unknown_frame_is_not_known(self):
        frame = UiFrame(kind=STATUS)
        self.assertFalse(frame.known)
        self.assertFalse(frame.observed)
        self.assertFalse(frame.stale)

    def test_a_disconnected_frame_is_recognised(self):
        frame = UiFrame(kind=STATUS, detail="Disconnected")
        self.assertTrue(frame.disconnected)



class SlowInventoryPollTests(unittest.TestCase):
    def test_inventory_is_bounded_and_slower_than_telemetry(self):
        clock = [0.0]
        service = FakeService({STATUS: observed_value(0), TELEMETRY: observed_value(0)})
        # The interval is pinned so the test checks the inventory pacing
        # relative to the telemetry poll, not the configured default.
        bridge = ObservationBridge(service, clock=lambda: clock[0], interval=2.0)
        asyncio.run(bridge.poll_once(object()))
        self.assertFalse(any(kind == "inventory" for _, _, kind in service.requests))
        clock[0] = 15
        service.results[STATUS] = observed_value(900)
        service.results[TELEMETRY] = observed_value(900)
        asyncio.run(bridge.poll_once(object()))
        requests = [args for _, args, kind in service.requests if kind == "inventory"]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["machinePageSize"], 8)
        clock[0] = 16
        asyncio.run(bridge.poll_once(object()))
        self.assertEqual(sum(kind == "inventory" for _, _, kind in service.requests), 1)


class DerivedUPSFrameTests(unittest.TestCase):
    def test_existing_tick_guard_supplies_an_explicit_estimate(self):
        clock = [0.0]
        service = FakeService({STATUS: observed_value(0), TELEMETRY: observed_value(0)})
        bridge = ObservationBridge(service, clock=lambda: clock[0])
        first = asyncio.run(bridge.poll_once(object()))
        self.assertIsNone(next(f for f in first if f.kind == STATUS).derived_ups)
        clock[0] = 4
        service.results[STATUS] = observed_value(240)
        frames = asyncio.run(bridge.poll_once(object()))
        self.assertEqual(next(f for f in frames if f.kind == STATUS).derived_ups, 60)


class SessionLoopOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_keeps_real_tool_calls_on_owner_loop(self):
        import json
        from types import SimpleNamespace

        from observation_service import ObservationService

        owner = asyncio.get_running_loop()
        calls, frames = [], []
        class Session:
            async def call_tool(self, *args, **kwargs):
                calls.append(asyncio.get_running_loop() is owner)
                return SimpleNamespace(is_error=False, content=[SimpleNamespace(type="text",
                    text=json.dumps({"tick": 60, "status": "ok"}))])
        bridge = ObservationBridge(ObservationService(timeout=1), interval=.01)
        thread = bridge.start(Session(), frames.append)
        try:
            for _ in range(100):
                if frames:
                    break
                await asyncio.sleep(.01)
            self.assertTrue(frames)
            self.assertTrue(calls)
            self.assertTrue(all(calls))
        finally:
            bridge.stop(timeout=1)
        self.assertFalse(thread.is_alive())


class IndependentTickOrderingTests(unittest.TestCase):
    def test_new_telemetry_does_not_reject_a_valid_cached_status(self):
        bridge = ObservationBridge(FakeService())
        self.assertTrue(bridge.accept_tick(100, STATUS))
        self.assertTrue(bridge.accept_tick(120, TELEMETRY))
        self.assertTrue(bridge.accept_tick(110, STATUS))
        self.assertFalse(bridge.accept_tick(90, STATUS))
        self.assertFalse(bridge.accept_tick(119, TELEMETRY))
        bridge.reset_ordering()
        self.assertTrue(bridge.accept_tick(1, STATUS))

if __name__ == "__main__":
    unittest.main()


class FullCatalogRefreshTests(unittest.TestCase):
    def test_concurrency_pause_keeps_the_same_catalog_page_pending(self):
        service = FakeService({CATALOG: CoordinatorObservation(
            kind=CATALOG, reason="concurrency_limited")})
        bridge = ObservationBridge(service)
        bridge.request_catalog(1, page_size=128, refresh=True)
        self.assertIsNone(asyncio.run(bridge.serve_catalog_request(object())))
        self.assertEqual(bridge._catalog_request, (1, 128))

    def test_budget_pause_keeps_the_same_catalog_page_pending(self):
        service = FakeService({CATALOG: CoordinatorObservation(
            kind=CATALOG, reason="budget_exhausted")})
        bridge = ObservationBridge(service)
        bridge.request_catalog(1, page_size=128, refresh=True)
        self.assertIsNone(asyncio.run(bridge.serve_catalog_request(object())))
        self.assertEqual(bridge._catalog_request, (1, 128))
        service.results[CATALOG] = observed_value(10, catalog_status={"total_pages": 1})
        frame = asyncio.run(bridge.serve_catalog_request(object()))
        self.assertIsNotNone(frame)
        self.assertIsNone(bridge._catalog_request)


    def test_refresh_loads_remaining_pages_between_regular_polls(self):
        payload=observed_value(10,catalog_status={"page":1,"total_pages":2})
        service=FakeService({CATALOG:payload, STATUS:observed_value(10)})
        bridge=ObservationBridge(service)
        self.assertTrue(bridge.request_catalog(1,page_size=128,refresh=True))
        asyncio.run(bridge.serve_catalog_request(object()))
        payload["catalog_status"]["page"]=2
        asyncio.run(bridge.poll_once(object()))
        asyncio.run(bridge.serve_catalog_request(object()))
        self.assertIsNone(asyncio.run(bridge.serve_catalog_request(object())))
        catalog_calls=[args for _,args,kind in service.requests if kind==CATALOG]
        self.assertEqual([args["catalogPage"] for args in catalog_calls],[1,2])
        self.assertEqual(catalog_calls[0]["catalogPageSize"],128)
        self.assertTrue(any(kind==STATUS for _,_,kind in service.requests))
        self.assertTrue(any(kind==TELEMETRY for _,_,kind in service.requests))
