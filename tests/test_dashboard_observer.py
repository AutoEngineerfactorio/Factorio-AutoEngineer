import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_feed import snapshot
from dashboard_observer import ViewOnly, observe
from dashboard_view import raster_pixels
from offline_loop import OfflineLoop
from session_safety import ConsoleControl


class ObserverTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(loop_factory=OfflineLoop)

    async def test_observer_cannot_arm_stop_or_write(self):
        raw = NS(call_tool=AsyncMock())
        for name, args in [
            ("walk_to_position", {}),
            ("autoengineer_arm", {}),
            ("autoengineer_stop", {}),
            ("autoengineer_view", {"x": 1}),
            ("autoengineer_view", {"catalogPage": True}),
            ("autoengineer_view", {"catalogPageSize": 33}),
        ]:
            with self.assertRaises((PermissionError, ValueError)):
                await ViewOnly(raw).call_tool(name, args)
        raw.call_tool.assert_not_called()

    async def test_observer_allows_only_bounded_catalog_pages(self):
        raw = NS(call_tool=AsyncMock())
        await ViewOnly(raw).call_tool(
            "autoengineer_view", {"catalogPage": 2, "catalogPageSize": 32}
        )
        raw.call_tool.assert_awaited_once_with(
            "autoengineer_view", arguments={"catalogPage": 2, "catalogPageSize": 32}
        )

    async def test_idle_observer_reads_without_ai_or_lease(self):
        c = ConsoleControl()
        calls = []

        async def read(name, arguments=None):
            calls.append(name)
            c.stop.set()
            return NS(
                is_error=False,
                content=[
                    NS(
                        type="text",
                        text=json.dumps(
                            dict(
                                status="ok",
                                x=0,
                                y=0,
                                tick=1,
                                surface="nauvis",
                                inventory=[],
                                inventory_available=True,
                                truncated=False,
                            )
                        ),
                    )
                ],
            )

        with patch("builtins.print") as output:
            await observe(ViewOnly(NS(call_tool=read)), c, 0.001)
        self.assertEqual(calls, ["autoengineer_view"])
        self.assertIn('"status":"ok"', output.call_args.args[0])

    async def test_observer_assembles_and_publishes_same_tick_catalog_pages(self):
        control = ConsoleControl()
        calls = []
        fingerprint = "poly31x131-v1:0123456789-9876543210"

        def catalog_page(number, names):
            recipes = [{
                "name": name, "enabled": True, "hidden": False, "simple": True,
                "category": "crafting", "crafting_time": 1,
                "ingredients": [{"name": "plate", "type": "item", "amount": 1}],
                "products": [{"name": name, "type": "item", "amount": 1}],
            } for name in names]
            return dict(
                status="ok", x=0, y=0, tick=120, surface="nauvis",
                inventory=[], inventory_available=True, truncated=False,
                catalog_status=dict(page=number, page_size=16, total_count=17,
                                    total_pages=2, status="ok"),
                capabilities=dict(
                    schema=1, tick=120, surface="nauvis", game_version="2.1.23",
                    force="player", research=[], enabled_content=["base"],
                    truncated=False, recipes=recipes, source_fingerprint=fingerprint,
                ),
            )

        responses = [
            catalog_page(1, [f"recipe-{i:02d}" for i in range(16)]),
            catalog_page(2, ["recipe-16"]),
        ]

        async def read(name, arguments=None):
            calls.append((name, arguments))
            raw = responses.pop(0)
            if not responses:
                control.stop.set()
            return NS(
                is_error=False,
                content=[NS(type="text", text=json.dumps(raw))],
            )

        with patch("builtins.print") as output:
            await observe(ViewOnly(NS(call_tool=read)), control, 0.001)
        self.assertEqual(
            calls,
            [
                ("autoengineer_view", {}),
                ("autoengineer_view", {"catalogPage": 2, "catalogPageSize": 16}),
            ],
        )
        self.assertIn('"status":"assembled"', output.call_args.args[0])


class RasterTests(unittest.TestCase):
    def terrain(self):
        return dict(
            origin=dict(x=0, y=0),
            step=1,
            rows=["01" * 256] * 256,
            palette=["#000000", "#73532f"],
            entities=[],
            partial=False,
        )

    def raw(self):
        return dict(
            status="ok",
            x=0,
            y=0,
            tick=1,
            surface="nauvis",
            inventory=[],
            inventory_available=True,
            truncated=False,
            slots=[],
            capacity=80,
            slots_truncated=False,
            terrain=self.terrain(),
        )

    def test_exact_map_color_survives_zoom_and_unknown_is_black(self):
        t = self.terrain()
        self.assertEqual(
            raster_pixels(t, dict(x=128, y=128), 4, 4, 128), bytes.fromhex("73532f") * 16
        )
        self.assertEqual(raster_pixels(t, dict(x=-500, y=-500), 4, 4, 128), b"\0" * 48)

    def test_rejects_malformed_palette_rows_and_indices(self):
        for mutate in [
            lambda t: t.update(rows=["00"] * 256),
            lambda t: t.update(palette=["red"]),
            lambda t: t.update(rows=["ff" * 256] * 256),
            lambda t: t.update(rows=t["rows"] * 2),
        ]:
            d = self.raw()
            mutate(d["terrain"])
            with self.assertRaises(ValueError):
                snapshot(d)

    def test_valid_raster_is_bounded_and_preserved(self):
        d = snapshot(self.raw())
        self.assertEqual(len(d["terrain"]["rows"]), 256)
        self.assertEqual(d["terrain"]["palette"][1], "#73532f")
