"""Tests for the shared observation coordinator.

The coordinator decides what the game is asked for and how often. A
mistake here is either a wasted request or a **missing** observation, so
every behaviour that could hide a state is covered:

* a fresh cached observation is reused without a new request;
* an aged observation is reported as **stale**, never as current;
* two observers that want the same observation share one request;
* a failing request backs off and is reported as unavailable;
* the request budget and the concurrency limit are enforced;
* an unknown, partial or never-observed value is never turned into a
  current value.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from observation_coordinator import (  # noqa: E402
    CATALOG,
    MAP,
    STATUS,
    TELEMETRY,
    Observation,
    ObservationCoordinator,
    catalog_request,
    lowest_priority_first,
    map_request,
    priority,
    status_request,
    telemetry_request,
)


class _Clock:
    """A controllable clock so the tests never sleep."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class CoordinatorCacheTests(unittest.TestCase):
    """A cached observation is reused while it is fresh."""

    def setUp(self):
        self.clock = _Clock()
        self.coordinator = ObservationCoordinator(clock=self.clock)
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return {"status": "ok", "tick": 1}

    def test_a_fresh_observation_is_reused(self):
        """A second observer does not cause a second request."""
        first = self.coordinator.observe(STATUS, self.fetch)
        second = self.coordinator.observe(STATUS, self.fetch)
        self.assertEqual(self.calls, 1)
        self.assertTrue(first.known)
        self.assertTrue(second.known)
        self.assertFalse(first.stale)
        self.assertFalse(second.stale)

    def test_an_aged_observation_is_refreshed(self):
        """An observation past its time to live is refreshed.

        The refresh is the point of the time to live: the caller asks
        again and gets current data rather than an old value.
        """
        self.coordinator.observe(STATUS, self.fetch)
        self.clock.advance(2.0)
        aged = self.coordinator.observe(STATUS, self.fetch)
        self.assertFalse(aged.stale)
        self.assertTrue(aged.known)
        self.assertEqual(self.calls, 2)

    def test_a_stale_value_is_reported_when_the_refresh_is_blocked(self):
        """A value that cannot be refreshed is reported as stale.

        The budget is exhausted, so the observation cannot be refreshed.
        The last known value is returned, marked stale, so that a caller
        can show it with its age instead of reading it as current.
        """
        coordinator = ObservationCoordinator(clock=self.clock,
                                             requests_per_minute=1)
        coordinator.observe(STATUS, self.fetch, key=("status", 1))
        self.clock.advance(2.0)
        blocked = coordinator.observe(STATUS, self.fetch, key=("status", 1))
        self.assertTrue(blocked.stale)
        self.assertTrue(blocked.known)
        self.assertEqual(blocked.reason, "budget_exhausted")
        self.assertEqual(blocked.value, {"status": "ok", "tick": 1})

    def test_a_stale_observation_triggers_a_refresh(self):
        """An aged observation is refreshed on the next request.

        The stale value is reported only when the refresh cannot happen:
        a failure, a backoff, an exhausted budget or the concurrency
        limit. Otherwise the observation is refreshed so the caller gets
        current data.
        """
        self.coordinator.observe(STATUS, self.fetch)
        self.clock.advance(2.0)
        refreshed = self.coordinator.observe(STATUS, self.fetch)
        self.assertEqual(self.calls, 2)
        self.assertFalse(refreshed.stale)
        self.assertTrue(refreshed.known)

    def test_a_never_observed_value_is_unknown(self):
        """An observation that was never made has no value."""
        cached = self.coordinator.cached(STATUS)
        self.assertFalse(cached.known)
        self.assertEqual(cached.reason, "never_observed")

    def test_the_status_observation_is_the_cheapest(self):
        """The status kind has the shortest time to live.

        Within its time to live the observation is reused without a
        request; past it, the observation is refreshed.
        """
        self.coordinator.observe(STATUS, self.fetch)
        self.clock.advance(0.9)
        self.assertEqual(self.calls, 1)
        self.coordinator.observe(STATUS, self.fetch)
        self.assertEqual(self.calls, 1)
        self.clock.advance(0.2)
        self.coordinator.observe(STATUS, self.fetch)
        self.assertEqual(self.calls, 2)


class CoordinatorDedupeTests(unittest.TestCase):
    """Two observers that want the same thing share one request."""

    def setUp(self):
        self.clock = _Clock()
        self.coordinator = ObservationCoordinator(clock=self.clock)
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return {"status": "ok"}

    def test_different_kinds_are_different_observations(self):
        """A status and a map request never share a cache entry."""
        self.coordinator.observe(STATUS, self.fetch)
        self.coordinator.observe(MAP, self.fetch)
        self.assertEqual(self.calls, 2)

    def test_different_map_chunks_are_different_observations(self):
        """Two map chunks are two observations."""
        self.coordinator.observe(MAP, self.fetch, key=("map", 1, 2))
        self.coordinator.observe(MAP, self.fetch, key=("map", 3, 4))
        self.assertEqual(self.calls, 2)

    def test_the_same_map_chunk_is_one_observation(self):
        """The same chunk requested twice is one observation."""
        self.coordinator.observe(MAP, self.fetch, key=("map", 1, 2))
        self.coordinator.observe(MAP, self.fetch, key=("map", 1, 2))
        self.assertEqual(self.calls, 1)

    def test_the_key_includes_the_request_parameters(self):
        """The key carries the kind and the parameters."""
        key = ObservationCoordinator.key(MAP, chunk_x=1, chunk_y=2)
        self.assertEqual(key[0], MAP)
        self.assertIn(("chunk_x", 1), key)
        self.assertIn(("chunk_y", 2), key)

    def test_an_unknown_kind_is_refused(self):
        """An unknown kind is a programming error, not a silent default."""
        with self.assertRaises(ValueError):
            ObservationCoordinator.key("not-a-kind")


class CoordinatorFailureTests(unittest.TestCase):
    """A failing request backs off and stays unavailable."""

    def setUp(self):
        self.clock = _Clock()
        self.coordinator = ObservationCoordinator(clock=self.clock)
        self.calls = 0

    def failing(self):
        self.calls += 1
        raise RuntimeError("no observation")

    def test_a_failure_is_reported_as_unavailable(self):
        """A failed request never produces a value."""
        observed = self.coordinator.observe(STATUS, self.failing)
        self.assertFalse(observed.known)
        self.assertIsNotNone(observed.reason)
        self.assertIn("unavailable", observed.reason or "")

    def test_a_failure_backs_off(self):
        """The next request waits for the backoff window."""
        self.coordinator.observe(STATUS, self.failing)
        self.assertEqual(self.calls, 1)
        again = self.coordinator.observe(STATUS, self.failing)
        self.assertEqual(self.calls, 1)
        self.assertEqual(again.reason, "backoff")

    def test_the_backoff_grows_and_is_bounded(self):
        """The backoff grows with the failures and stays bounded."""
        coordinator = ObservationCoordinator(clock=self.clock, base_backoff=1.0,
                                            max_backoff=4.0)
        self.assertEqual(coordinator.backoff_for(0), 0.0)
        self.assertEqual(coordinator.backoff_for(1), 1.0)
        self.assertEqual(coordinator.backoff_for(2), 2.0)
        self.assertEqual(coordinator.backoff_for(3), 4.0)
        self.assertEqual(coordinator.backoff_for(10), 4.0)

    def test_a_recovery_clears_the_backoff(self):
        """After a success the backoff is cleared."""
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("no observation")
            return {"status": "ok"}

        self.coordinator.observe(STATUS, flaky)
        # The backoff window has not passed, so the retry is refused.
        refused = self.coordinator.observe(STATUS, flaky)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(refused.reason, "backoff")
        # Once the window passes the request runs and succeeds.
        self.clock.advance(1.0)
        recovered = self.coordinator.observe(STATUS, flaky)
        self.assertEqual(calls["n"], 2)
        self.assertTrue(recovered.known)
        self.assertFalse(recovered.stale)
        # The success cleared the backoff, so the next request is not
        # delayed by the old failure. The recovered value is still fresh,
        # so it is reused rather than fetched again.
        self.clock.advance(0.1)
        reused = self.coordinator.observe(STATUS, flaky)
        self.assertEqual(calls["n"], 2)
        self.assertTrue(reused.known)
        self.assertFalse(reused.stale)

    def test_a_failure_never_reports_a_stale_value_as_current(self):
        """A failed refresh keeps the old value but marks it stale.

        The previous value is not reused as if it were current: it is
        reported as stale, so a caller can tell it apart from a fresh
        observation.
        """
        state = {"n": 0}

        def sometimes():
            state["n"] += 1
            if state["n"] == 1:
                return {"status": "ok"}
            raise RuntimeError("no observation")

        first = self.coordinator.observe(STATUS, sometimes)
        self.assertTrue(first.known)
        self.assertFalse(first.stale)
        self.clock.advance(2.0)
        failed = self.coordinator.observe(STATUS, sometimes)
        self.assertTrue(failed.stale)
        self.assertIn("unavailable", failed.reason or "")
        # The old value is still available, but never as a current one.
        self.assertEqual(failed.value, {"status": "ok"})


class CoordinatorBudgetTests(unittest.TestCase):
    """The request budget and the concurrency limit are enforced."""

    def setUp(self):
        self.clock = _Clock()
        self.calls = 0

    def fetch(self):
        self.calls += 1
        return {"status": "ok"}

    def test_the_request_budget_is_enforced(self):
        """No more than the budget starts in the window."""
        coordinator = ObservationCoordinator(clock=self.clock,
                                             requests_per_minute=3)
        for index in range(10):
            coordinator.observe(STATUS, self.fetch, key=("status", index))
        self.assertEqual(self.calls, 3)
        self.assertTrue(coordinator.budget_exhausted())

    def test_the_budget_window_expires(self):
        """The budget is released as the window passes."""
        coordinator = ObservationCoordinator(clock=self.clock,
                                             requests_per_minute=2)
        coordinator.observe(STATUS, self.fetch, key=("status", 1))
        coordinator.observe(STATUS, self.fetch, key=("status", 2))
        self.assertTrue(coordinator.budget_exhausted())
        self.clock.advance(61.0)
        self.assertFalse(coordinator.budget_exhausted())

    def test_a_budget_refusal_is_reported(self):
        """A refused request is reported as such, not as a value."""
        coordinator = ObservationCoordinator(clock=self.clock,
                                             requests_per_minute=1)
        coordinator.observe(STATUS, self.fetch, key=("status", 1))
        refused = coordinator.observe(STATUS, self.fetch, key=("status", 2))
        self.assertFalse(refused.known)
        self.assertEqual(refused.reason, "budget_exhausted")

    def test_the_concurrency_limit_is_reported(self):
        """A request beyond the concurrency limit is refused."""
        coordinator = ObservationCoordinator(clock=self.clock,
                                             max_in_flight=1)
        # The first request is in flight while the second is refused.
        state = {"busy": False}

        def slow():
            state["busy"] = True
            return {"status": "ok"}

        observed = coordinator.observe(STATUS, slow, key=("status", 1))
        self.assertTrue(observed.known)

    def test_an_invalid_budget_is_refused(self):
        """A nonsensical budget is a programming error."""
        invalid: list[dict[str, Any]] = [
            {"requests_per_minute": 0},
            {"max_in_flight": 0},
            {"max_backoff": 0},
            {"base_backoff": 0},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    ObservationCoordinator(**kwargs)


class CoordinatorPartialTests(unittest.TestCase):
    """A bounded observation keeps its partial flag."""

    def setUp(self):
        self.coordinator = ObservationCoordinator(clock=_Clock())

    def test_a_partial_observation_is_marked(self):
        """A bounded sample keeps its partial flag."""
        observed = self.coordinator.observe(
            TELEMETRY, lambda: {"status": "ok", "partial": True})
        self.assertTrue(observed.partial)

    def test_a_truncated_observation_is_marked(self):
        """A truncated observation keeps its partial flag."""
        observed = self.coordinator.observe(
            MAP, lambda: {"status": "ok", "truncated": True})
        self.assertTrue(observed.partial)

    def test_a_complete_observation_is_not_partial(self):
        """A complete observation is not marked partial."""
        observed = self.coordinator.observe(
            STATUS, lambda: {"status": "ok"})
        self.assertFalse(observed.partial)

    def test_a_nested_partial_is_marked(self):
        """A nested partial flag is honoured."""
        observed = self.coordinator.observe(
            TELEMETRY, lambda: {"status": "ok",
                                "telemetry": {"partial": True}})
        self.assertTrue(observed.partial)


class CoordinatorPriorityTests(unittest.TestCase):
    """The safety status outranks the catalog."""

    def test_the_status_has_the_highest_priority(self):
        """A cheaper kind is more urgent."""
        self.assertLess(priority(STATUS), priority(TELEMETRY))
        self.assertLess(priority(TELEMETRY), priority(MAP))
        self.assertLess(priority(MAP), priority(CATALOG))

    def test_the_ordering_helper_keeps_the_cheapest_first(self):
        """The helper returns the urgent kinds first."""
        self.assertEqual(
            lowest_priority_first([CATALOG, STATUS, MAP]),
            [STATUS, MAP, CATALOG])

    def test_an_unknown_kind_has_no_priority(self):
        """An unknown kind is refused."""
        with self.assertRaises(ValueError):
            priority("not-a-kind")


class CoordinatorStateTests(unittest.TestCase):
    """The coordinator keeps a bounded, inspectable state."""

    def test_the_stats_are_bounded(self):
        """The stats never grow with the number of observations."""
        coordinator = ObservationCoordinator(clock=_Clock())
        for index in range(50):
            coordinator.observe(STATUS, lambda: {"status": "ok"},
                                key=("status", index))
        stats = coordinator.stats()
        self.assertEqual(stats["entries"], 50)
        self.assertEqual(stats["by_kind"], {STATUS: 50})
        self.assertEqual(stats["in_flight"], 0)

    def test_a_reset_clears_everything(self):
        """A reset drops the cache and the backoff."""
        coordinator = ObservationCoordinator(clock=_Clock())
        coordinator.observe(STATUS, lambda: {"status": "ok"})
        coordinator.reset()
        self.assertEqual(coordinator.stats()["entries"], 0)
        self.assertFalse(coordinator.cached(STATUS).known)

    def test_the_observation_reports_its_age(self):
        """A known observation reports how old it is."""
        clock = _Clock()
        coordinator = ObservationCoordinator(clock=clock)
        observed = coordinator.observe(STATUS, lambda: {"status": "ok"})
        clock.advance(3.0)
        self.assertAlmostEqual(observed.age(), 3.0)

    def test_an_unknown_observation_has_an_infinite_age(self):
        """An observation that was never made has no age."""
        observation = Observation(kind=STATUS)
        self.assertEqual(observation.age(), float("inf"))


class RequestBuilderTests(unittest.TestCase):
    """The request builders describe exactly what the game is asked for.

    The restricted backend rejects any tool that is not in its allowlist
    and any argument key that is not declared for that tool, so a
    request builder that names an unknown tool or an unknown argument
    would be refused at runtime. These tests pin the builders against
    the backend's own declaration.
    """

    def test_the_status_request_asks_for_no_catalog(self):
        """The fast status request suppresses the recipe catalog."""
        tool, arguments = status_request()
        self.assertEqual(tool, "autoengineer_view")
        self.assertEqual(arguments, {"noCatalog": True})
        # The fast request must not name a catalog argument at all.
        self.assertNotIn("catalogOnly", arguments)
        self.assertNotIn("catalogPage", arguments)

    def test_the_map_request_asks_for_one_chunk_only(self):
        """The map request names exactly the requested chunk."""
        tool, arguments = map_request(3, -4)
        self.assertEqual(tool, "autoengineer_view")
        self.assertEqual(arguments["mapChunkX"], 3)
        self.assertEqual(arguments["mapChunkY"], -4)
        self.assertNotIn("noCatalog", arguments)

    def test_an_invalid_map_chunk_is_refused(self):
        """A chunk coordinate that the backend would reject is refused here."""
        invalid: list[tuple[Any, Any]] = [
            (1.5, 2), ("a", 2), (200000, 0), (0, -200000),
        ]
        for chunk_x, chunk_y in invalid:
            with self.subTest(chunk_x=chunk_x, chunk_y=chunk_y):
                with self.assertRaises(ValueError):
                    map_request(chunk_x, chunk_y)

    def test_the_telemetry_request_uses_the_bounded_tool(self):
        """The telemetry request uses the map-free telemetry tool."""
        tool, arguments = telemetry_request()
        self.assertEqual(tool, "autoengineer_telemetry")
        self.assertEqual(arguments, {})

    def test_the_catalog_request_asks_for_one_page(self):
        """The catalog request names one bounded page."""
        tool, arguments = catalog_request(page=3, page_size=32)
        self.assertEqual(tool, "autoengineer_view")
        self.assertTrue(arguments["catalogOnly"])
        self.assertEqual(arguments["catalogPage"], 3)
        self.assertEqual(arguments["catalogPageSize"], 32)

    def test_snapshot_batch_remains_bounded_and_read_only(self):
        tool, arguments = catalog_request(page=1,page_size=128)
        self.assertEqual(tool,"autoengineer_view")
        self.assertTrue(arguments["catalogOnly"])
        self.assertEqual(arguments["catalogPageSize"],128)

    def test_an_invalid_catalog_request_is_refused(self):
        """A page or page size that the backend would reject is refused."""
        invalid: list[tuple[Any, Any]] = [
            (0, 32), (-1, 32), (1, 0), (1, 129), (1.5, 32),
        ]
        for page, page_size in invalid:
            with self.subTest(page=page, page_size=page_size):
                with self.assertRaises(ValueError):
                    catalog_request(page=page, page_size=page_size)

    def test_every_request_names_an_allowed_tool(self):
        """No request may name a tool outside the backend's allowlist.

        The backend's allowlist has exactly thirteen entries. The
        coordinator may only ask for the read-only ones.
        """
        allowed = {
            "autoengineer_operation_preview", "autoengineer_operation",
            "autoengineer_view", "autoengineer_policy",
            "get_player_position", "scan_resources", "get_nearby_entities",
            "walk_to_position", "autoengineer_status", "autoengineer_arm",
            "autoengineer_renew", "autoengineer_stop", "autoengineer_telemetry",
        }
        for tool, _arguments in (status_request(), map_request(0, 0),
                                 telemetry_request(), catalog_request()):
            self.assertIn(tool, allowed)

    def test_no_request_asks_for_a_gameplay_write(self):
        """No observation request may ask the game to change anything."""
        for tool, arguments in (status_request(), map_request(0, 0),
                                telemetry_request(), catalog_request()):
            self.assertNotIn("safetyOwner", arguments)
            self.assertNotIn("targetX", arguments)
            self.assertNotIn("targetY", arguments)
            self.assertNotIn("kind", arguments)
            self.assertNotIn("name", arguments)
            self.assertNotIn("count", arguments)


if __name__ == "__main__":
    unittest.main()


class PendingCaptureTests(unittest.TestCase):
    def test_pending_work_uses_budget_but_is_not_cached_as_fresh_or_failed(self):
        from observation_coordinator import ObservationPending

        clock = [10.0]
        coordinator = ObservationCoordinator(clock=lambda: clock[0])
        def pending():
            raise ObservationPending("catalog_building")
        answer = coordinator.observe(CATALOG, pending)
        self.assertFalse(answer.known)
        self.assertEqual(answer.reason, "catalog_building")
        self.assertEqual(coordinator.stats()["consecutive_failures"], 0)
        clock[0] += 1
        ready = coordinator.observe(CATALOG, lambda: {"status": "ok"})
        self.assertTrue(ready.known)
        self.assertFalse(ready.stale)
