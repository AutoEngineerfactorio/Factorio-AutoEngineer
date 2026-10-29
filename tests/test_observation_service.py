"""The observation service must deduplicate, cache and back off correctly.

The service is the async face of the shared observation coordinator. It must
never widen a read, never present a stale value as a current one and never
issue a gameplay command.
"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from observation_coordinator import (  # noqa: E402
    CATALOG,
    MAP,
    STATUS,
    ObservationCoordinator,
)
from observation_service import ObservationService  # noqa: E402


class _Session:
    """A minimal stand-in for the MCP session."""

    def __init__(self, payload=None, *, is_error=False):
        self.payload = payload if payload is not None else {"status": "ok"}
        self.is_error = is_error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name, arguments=None):
        self.calls.append((name, dict(arguments or {})))
        return NS(
            is_error=self.is_error,
            content=[NS(type="text", text=json.dumps(self.payload))],
        )


class ObservationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_building_catalog_is_not_cached_as_a_fresh_value(self):
        clock = [10.0]
        service = ObservationService(ObservationCoordinator(clock=lambda: clock[0]))
        session = _Session({"status": "pending", "reason": "catalog_building"})
        try:
            answer = await service.observe_tool(session, "autoengineer_view", {}, kind=CATALOG)
            self.assertFalse(answer.known)
            self.assertEqual(answer.reason, "catalog_building")
            self.assertEqual(service.stats()["consecutive_failures"], 0)
            clock[0] += 1
            session.payload = {"status": "ok", "tick": 12}
            ready = await service.observe_tool(session, "autoengineer_view", {}, kind=CATALOG)
            self.assertTrue(ready.known)
            self.assertEqual(len(session.calls), 2)
        finally:
            service.close()

    async def test_a_second_request_within_the_freshness_costs_no_request(self):
        service = ObservationService(timeout=5)
        session = _Session()
        try:
            first = await service.observe_tool(
                session, "autoengineer_view", {"noCatalog": True}, kind=STATUS)
            second = await service.observe_tool(
                session, "autoengineer_view", {"noCatalog": True}, kind=STATUS)
            self.assertTrue(first.known)
            self.assertTrue(second.known)
            self.assertEqual(len(session.calls), 1)
        finally:
            service.close()

    async def test_two_different_map_chunks_are_two_observations(self):
        service = ObservationService(timeout=5)
        session = _Session()
        try:
            await service.observe_tool(
                session, "autoengineer_view", {"mapChunkX": 1, "mapChunkY": 2},
                kind=MAP, key=service.coordinator.key(MAP, chunk_x=1, chunk_y=2))
            await service.observe_tool(
                session, "autoengineer_view", {"mapChunkX": 3, "mapChunkY": 4},
                kind=MAP, key=service.coordinator.key(MAP, chunk_x=3, chunk_y=4))
            self.assertEqual(len(session.calls), 2)
        finally:
            service.close()

    async def test_a_failed_request_is_never_reported_as_current(self):
        service = ObservationService(timeout=5)
        session = _Session(is_error=True)
        try:
            answer = await service.observe_tool(
                session, "autoengineer_view", {"noCatalog": True}, kind=STATUS)
            self.assertFalse(answer.known)
            self.assertIn("unavailable", str(answer.reason))
        finally:
            service.close()

    async def test_a_failure_backs_off_instead_of_retrying_tightly(self):
        coordinator = ObservationCoordinator(base_backoff=5.0)
        service = ObservationService(coordinator, timeout=5)
        session = _Session(is_error=True)
        try:
            await service.observe_tool(
                session, "autoengineer_view", {"noCatalog": True}, kind=STATUS)
            await service.observe_tool(
                session, "autoengineer_view", {"noCatalog": True}, kind=STATUS)
            # The second call is inside the backoff window, so it costs no
            # request at all.
            self.assertEqual(len(session.calls), 1)
        finally:
            service.close()

    async def test_the_service_never_requests_a_gameplay_tool(self):
        """Only the read-only view tool may be requested through the service."""
        source = (ROOT / "agent" / "observation_service.py").read_text(
            encoding="utf-8")
        for forbidden in ("autoengineer_operation", "walk_to_position",
                          "autoengineer_arm", "autoengineer_renew"):
            self.assertNotIn(forbidden, source)

    async def test_the_service_keeps_the_coordinator_usable(self):
        service = ObservationService(timeout=5)
        try:
            stats = cast(dict, service.stats())
            self.assertIn("entries", stats)
            self.assertIn("in_flight", stats)
            self.assertEqual(stats["in_flight"], 0)
        finally:
            service.close()



class BackendPayloadFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_declared_backend_errors_are_not_fresh_observations(self):
        for status in ("unavailable", "error"):
            service = ObservationService(timeout=1)
            try:
                answer = await service.observe_tool(_Session({"status": status}),
                    "autoengineer_view", {"noCatalog": True}, kind=STATUS)
                self.assertFalse(answer.known)
                assert answer.reason is not None
                self.assertIn("unavailable", answer.reason)
            finally:
                service.close()

    async def test_failed_response_keeps_previous_value_stale_and_backs_off(self):
        clock = [0.0]
        coordinator = ObservationCoordinator(clock=lambda: clock[0])
        service = ObservationService(coordinator, timeout=1)
        session = _Session({"status": "ok", "tick": 1})
        try:
            await service.observe_tool(session, "autoengineer_view", {}, kind=STATUS)
            clock[0] = 10
            session.payload = {"status": "unavailable"}
            failed = await service.observe_tool(session, "autoengineer_view", {}, kind=STATUS)
            self.assertTrue(failed.stale)
            self.assertEqual(failed.value["tick"], 1)
            await service.observe_tool(session, "autoengineer_view", {}, kind=STATUS)
            self.assertEqual(len(session.calls), 2)
        finally:
            service.close()

if __name__ == "__main__":
    unittest.main()


class ToolArgumentCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_catalog_pages_are_not_the_same_cache_entry(self):
        from observation_coordinator import CATALOG
        service=ObservationService(timeout=5)
        session=_Session()
        try:
            await service.observe_tool(session,"autoengineer_view",{"catalogPage":1},kind=CATALOG)
            await service.observe_tool(session,"autoengineer_view",{"catalogPage":2},kind=CATALOG)
            await service.observe_tool(session,"autoengineer_view",{"catalogPage":2},kind=CATALOG)
            self.assertEqual(len(session.calls),2)
        finally:
            service.close()


class SessionEventLoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_calls_run_on_the_callers_session_loop(self):
        import asyncio
        owner=asyncio.get_running_loop()
        class LoopBoundSession(_Session):
            async def call_tool(self,name,arguments=None):
                if asyncio.get_running_loop() is not owner:
                    raise RuntimeError("MCP session used from a foreign event loop")
                return await super().call_tool(name,arguments)
        service=ObservationService(timeout=5)
        try:
            result=await service.observe_tool(LoopBoundSession(),"autoengineer_view",{},kind=STATUS)
            self.assertTrue(result.known,result.reason)
        finally:
            service.close()
