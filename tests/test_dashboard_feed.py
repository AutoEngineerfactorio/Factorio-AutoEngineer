import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_feed import PREFIX, DashboardFeed, parse_frame, snapshot
from dashboard_view import LiveView, project
from dispatch_boundary import DispatchBoundary
from offline_loop import OfflineLoop
from session_safety import ConsoleControl


def raw():
    return dict(
        status="ok",
        x=0,
        y=0,
        tick=123,
        surface="nauvis",
        inventory=[dict(name="iron-plate", quality="normal", count=8)],
        inventory_available=True,
        truncated=False,
    )


class FrameTests(unittest.TestCase):
    def test_control_observation_rejects_coerced_types_and_unbounded_epoch(self):
        control = dict(
            input_adapter=True,
            character_control=True,
            lease_active=False,
            walking=False,
            generation=1,
        )
        self.assertEqual(snapshot(dict(raw(), control=control))["control"], control)
        for field in ("input_adapter", "character_control", "lease_active", "walking"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                snapshot(dict(raw(), control=dict(control, **{field: 1})))
        for value in (True, -1, 2**53 + 1, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                snapshot(dict(raw(), control=dict(control, generation=value)))

    def test_final_operation_snapshot_can_be_published_before_poll_interval(self):
        with patch("builtins.print") as output:
            DashboardFeed().publish(
                dict(raw(), inventory=[dict(name="iron-gear-wheel", quality="normal", count=3)])
            )
        frame = parse_frame(output.call_args.args[0])
        assert frame is not None
        self.assertEqual(frame["inventory"][0]["count"], 3)

    def test_roundtrip_and_main_inventory_quality(self):
        data = snapshot(raw())
        data.update(DashboardFeed().features)
        frame = parse_frame(PREFIX + json.dumps(dict(schema=1, status="ok", **data)))
        assert frame is not None
        self.assertEqual(frame["inventory"][0]["count"], 8)
        self.assertEqual(frame["inventory"][0]["quality"], "normal")

    def test_invalid_and_oversized_data_rejected(self):
        for data in [
            dict(raw(), x=float("nan")),
            dict(raw(), inventory=[dict(name="ore", quality="normal", count=-1)]),
            dict(raw(), inventory=raw()["inventory"] * 65),
            dict(raw(), inventory_available="yes"),
        ]:
            with self.assertRaises(ValueError):
                snapshot(data)
        with self.assertRaises(ValueError):
            parse_frame(PREFIX + "x" * 65536)
        with self.assertRaises(ValueError):
            parse_frame(PREFIX + '{"schema":1,"status":"ok","position":[]}')

    def test_empty_inventory_is_not_unknown_inventory(self):
        self.assertEqual(snapshot(dict(raw(), inventory={}))["inventory"], [])
        self.assertFalse(snapshot(dict(raw(), inventory_available=False))["inventory_available"])

    def test_catalog_page_status_is_bounded_and_preserved(self):
        status = dict(
            page=2, page_size=16, total_count=300, total_pages=19, status="ok"
        )
        capabilities = dict(
            schema=1, tick=123, surface="nauvis", game_version="2.0.77",
            force="player", research=[], enabled_content=["base"],
            truncated=True, recipes=[],
        )
        self.assertEqual(
            snapshot(dict(raw(), catalog_status=status, capabilities=capabilities))["catalog_status"],
            status,
        )
        for invalid in (
            dict(status, page=True),
            dict(status, page_size=33),
            dict(status, total_count=10001),
            dict(page=1, page_size=16, status="ok"),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                snapshot(dict(raw(), catalog_status=invalid))
        complete_empty = dict(
            page=1, page_size=16, total_count=0, total_pages=0, status="ok"
        )
        complete_capabilities = dict(capabilities, truncated=False)
        self.assertFalse(snapshot(dict(
            raw(), catalog_status=complete_empty, capabilities=complete_capabilities
        ))["capabilities"]["truncated"])
        out_of_range = dict(
            page=20, page_size=16, total_count=300, total_pages=19,
            status="page_out_of_range",
        )
        self.assertEqual(
            snapshot(dict(raw(), catalog_status=out_of_range))["catalog_status"]["status"],
            "page_out_of_range",
        )
        with self.assertRaises(ValueError):
            snapshot(dict(raw(), catalog_status=out_of_range, capabilities=capabilities))
        incomplete_capabilities = dict(capabilities, truncated=False)
        partial_frame = snapshot(dict(
            raw(), catalog_status=status, capabilities=incomplete_capabilities
        ))
        from read_only_planning import view_intelligence

        planning = view_intelligence(dict(status="ok", **partial_frame), received_at=100)
        self.assertFalse(planning["planner_ready"])

    def test_projection_has_correct_axes_and_scale(self):
        self.assertEqual(project({"x": 10, "y": -10}, {"x": 0, "y": 0}, 400, 200, 50), (220, 80))

    def test_display_failure_retains_snapshot_but_marks_stale(self):
        view = LiveView.__new__(LiveView)
        view.last = raw()
        view.available = True
        view.update_frame({"status": "unavailable"})
        self.assertFalse(view.available)
        view.received = 0
        view.status = Mock()
        with patch("dashboard_view.time.monotonic", return_value=4):
            view.freshness(True)
        self.assertTrue(view.status.set.call_args.args[0].startswith("Stale"))
        view.freshness(False)
        self.assertTrue(view.status.set.call_args.args[0].startswith("Session ended"))


class FeedSafetyTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=OfflineLoop)

    async def test_telemetry_reads_cannot_dispatch_gameplay(self):
        control = ConsoleControl()
        calls = []

        async def call(name, arguments=None):
            calls.append(name)
            control.stop.set()
            return NS(is_error=False, content=[NS(type="text", text=json.dumps(raw()))])

        with patch("builtins.print"):
            await DashboardFeed().poll(
                DispatchBoundary(NS(call_tool=call), control), control, interval=0.001
            )
        self.assertEqual(calls, ["autoengineer_view"])

    async def test_surface_change_stops_session(self):
        control = ConsoleControl()
        responses = [raw(), dict(raw(), surface="vulcanus")]

        async def call(*args, **kwargs):
            return NS(is_error=False, content=[NS(type="text", text=json.dumps(responses.pop(0)))])

        with patch("builtins.print"):
            await DashboardFeed().poll(NS(call_tool=call), control, interval=0.001)
        self.assertTrue(control.stop.is_set())

    async def test_read_error_is_unavailable_and_does_not_change_approval(self):
        control = ConsoleControl()

        async def call(*args, **kwargs):
            control.stop.set()
            raise RuntimeError("private error detail")

        with patch("builtins.print") as output:
            await DashboardFeed().poll(NS(call_tool=call), control, interval=0.001)
        self.assertEqual(output.call_args.args[0], PREFIX + '{"schema":1,"status":"unavailable"}')

    async def test_view_rejects_extra_arguments(self):
        raw_session = NS(call_tool=AsyncMock())
        with self.assertRaises(PermissionError):
            await DispatchBoundary(raw_session).call_tool("autoengineer_view", {"lua": "x"})
        raw_session.call_tool.assert_not_called()

    async def test_view_catalog_pages_are_bounded(self):
        raw_session = NS(call_tool=AsyncMock())
        boundary = DispatchBoundary(raw_session)
        await boundary.call_tool(
            "autoengineer_view", {"catalogPage": 2, "catalogPageSize": 32}
        )
        raw_session.call_tool.assert_awaited_once_with(
            "autoengineer_view",
            arguments={"catalogPage": 2, "catalogPageSize": 32},
        )
        for args in (
            {"catalogPage": True},
            {"catalogPage": 10001},
            {"catalogPageSize": 33},
            {"catalogPageSize": 1.5},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                await boundary.call_tool("autoengineer_view", args)
        raw_session.call_tool.assert_awaited_once()
