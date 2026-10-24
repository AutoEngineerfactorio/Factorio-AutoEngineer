import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_feed import (
    PREFIX,
    DashboardFeed,
    command_help,
    observed_entity_footprint,
    parse_frame,
    snapshot,
)
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
    def test_command_help_separates_guard_backend_mode_and_telemetry(self):
        help_text = command_help()
        self.assertIn("/autoengineer-status", help_text)
        self.assertIn("/autoengineer-takeover", help_text)
        self.assertIn("not backend connection proof", help_text)
        self.assertIn("explicit human takeover only", help_text)
        self.assertIn("reported separately", help_text)

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
            schema=1, tick=123, surface="nauvis", game_version="2.1.23",
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


class ObservedEntityFrameTests(unittest.TestCase):
    """The feed must accept the observed natural-object fields and nothing else."""

    def footprint(self, value):
        return observed_entity_footprint(value)

    def test_an_observed_chart_color_is_preserved(self):
        result = self.footprint({"map_color": {"r": 129, "g": 105, "b": 78}})
        self.assertEqual(result["map_color"], {"r": 129, "g": 105, "b": 78})

    def test_an_absent_chart_color_stays_absent(self):
        # A prototype with no chart colour must not gain an invented one.
        self.assertNotIn("map_color", self.footprint({}))

    def test_an_invalid_chart_color_is_rejected(self):
        for bad in ({"r": 1, "g": 2}, {"r": 1, "g": 2, "b": 3, "a": 4},
                    {"r": -1, "g": 0, "b": 0}, {"r": 256, "g": 0, "b": 0},
                    {"r": 1.5, "g": 0, "b": 0}, {"r": "1", "g": 0, "b": 0},
                    {"r": True, "g": 0, "b": 0}, "red"):
            with self.assertRaises(ValueError):
                self.footprint({"map_color": bad})

    def test_observed_entity_and_prototype_types_are_preserved(self):
        result = self.footprint({"entity_type": "tree", "prototype_type": "tree"})
        self.assertEqual(result["entity_type"], "tree")
        self.assertEqual(result["prototype_type"], "tree")

    def test_the_observed_graphics_variation_is_preserved(self):
        result = self.footprint({"graphics_variation": 6})
        self.assertEqual(result["graphics_variation"], 6)

    def test_an_invalid_graphics_variation_is_rejected(self):
        for bad in (-1, 256, 1.5, "3", True, None):
            with self.assertRaises(ValueError):
                self.footprint({"graphics_variation": bad})

    def test_an_invalid_prototype_identity_is_rejected(self):
        for bad in ("", 5, None, "x" * 65):
            with self.assertRaises(ValueError):
                self.footprint({"entity_type": bad})

    def test_geometry_and_colour_combine(self):
        result = self.footprint({
            "map_color": {"r": 144, "g": 119, "b": 87},
            "entity_type": "cliff",
            "prototype_type": "cliff",
            "width": 2.0,
            "height": 1.0,
            "direction": 4,
        })
        self.assertEqual(result["map_color"], {"r": 144, "g": 119, "b": 87})
        self.assertEqual(result["entity_type"], "cliff")
        self.assertEqual(result["width"], 2.0)
        self.assertEqual(result["direction"], 4)

    def test_a_nature_entity_outside_the_observed_window_is_rejected(self):
        frame = dict(
            raw(),
            capacity=40,
            slots=[],
            slots_truncated=False,
            terrain=dict(
                step=4,
                partial=False,
                origin={"x": 0, "y": 0},
                rows=["00"] * 256,
                palette=["#000000"],
                entities=[dict(x=999, y=999, name="tree-01", kind="nature")],
            ),
        )
        with self.assertRaises(ValueError):
            snapshot(frame)

    def test_map_chunk_metadata_is_preserved_and_bounded(self):
        frame = dict(
            raw(),
            capacity=40,
            slots=[],
            slots_truncated=False,
            terrain=dict(
                step=1,
                partial=True,
                origin={"x": -128, "y": 192},
                rows=["00" * 64] * 64,
                palette=["#000000"],
                entities=[],
                map_chunk={"x": -2, "y": 3, "size": 64},
                chunk_complete=False,
            ),
        )
        terrain = snapshot(frame)["terrain"]
        self.assertEqual(terrain["map_chunk"], {"x": -2, "y": 3, "size": 64})
        self.assertTrue(terrain["partial"])
        self.assertFalse(terrain["chunk_complete"])

    def test_map_chunk_origin_must_be_aligned_to_its_chunk(self):
        frame = dict(
            raw(),
            capacity=40,
            slots=[],
            slots_truncated=False,
            terrain=dict(
                step=1,
                partial=False,
                origin={"x": 0, "y": 0},
                rows=["00" * 64] * 64,
                palette=["#000000"],
                entities=[],
                map_chunk={"x": -2, "y": 3, "size": 64},
            ),
        )
        with self.assertRaises(ValueError):
            snapshot(frame)

    def test_invalid_map_chunk_metadata_is_rejected(self):
        for chunk in (
            {"x": 0, "y": 0, "size": 0},
            {"x": 0, "y": 0, "size": 65},
            {"x": True, "y": 0, "size": 64},
            {"x": 0, "y": 0},
        ):
            frame = dict(
                raw(),
                capacity=40,
                slots=[],
                slots_truncated=False,
                terrain=dict(
                    step=1,
                    partial=True,
                    origin={"x": 0, "y": 0},
                    rows=["00" * 256] * 256,
                    palette=["#000000"],
                    entities=[],
                    map_chunk=chunk,
                ),
            )
            with self.subTest(chunk=chunk), self.assertRaises(ValueError):
                snapshot(frame)

    def test_a_nature_entity_with_a_chart_color_is_accepted(self):
        frame = dict(
            raw(),
            capacity=40,
            slots=[],
            slots_truncated=False,
            terrain=dict(
                step=4,
                partial=False,
                origin={"x": 0, "y": 0},
                rows=["00"] * 256,
                palette=["#000000"],
                entities=[dict(
                    x=10, y=10, name="big-rock", kind="nature",
                    entity_type="simple-entity", prototype_type="simple-entity",
                    map_color={"r": 129, "g": 105, "b": 78},
                )],
            ),
        )
        entities = snapshot(frame)["terrain"]["entities"]
        self.assertEqual(entities[0]["map_color"], {"r": 129, "g": 105, "b": 78})
        self.assertEqual(entities[0]["prototype_type"], "simple-entity")


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
