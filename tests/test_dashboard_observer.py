import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "agent"
sys.path.insert(0, str(AGENT_DIR))
from dashboard_feed import snapshot
from dashboard_observer import ViewOnly, ViewportRequests, observe, observe_viewport
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

    def test_full_catalog_is_requested_once_with_multitick_validation(self):
        from inspect import getsource
        source = getsource(observe)
        self.assertIn('allow_multi_tick=catalog_only', source)
        self.assertIn('if catalog_only and full_catalog', source)
        self.assertIn('catalogPageSize', source)
        self.assertIn('if catalog_only:', source)
        self.assertIn('validate_capabilities', source)

    async def test_catalog_observer_requests_no_map_and_is_one_shot(self):
        raw = NS(call_tool=AsyncMock())
        await ViewOnly(raw, catalog_only=True).call_tool(
            "autoengineer_view", {"catalogPage": 3, "catalogPageSize": 16}
        )
        raw.call_tool.assert_awaited_once_with(
            "autoengineer_view", arguments={
                "catalogPage": 3, "catalogPageSize": 16, "catalogOnly": True
            }
        )
        with self.assertRaises(PermissionError):
            await ViewOnly(raw, catalog_only=True).call_tool(
                "autoengineer_view", {"mapChunkX": 0, "mapChunkY": 0}
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
            await observe(ViewOnly(NS(call_tool=read), catalog_only=True), control,
                          0.001, catalog_only=True, full_catalog=True)
        self.assertEqual(
            calls,
            [
                ("autoengineer_view", {"catalogPageSize": 32, "catalogOnly": True}),
                ("autoengineer_view", {"catalogPage": 2, "catalogPageSize": 16,
                                       "catalogOnly": True}),
            ],
        )
        self.assertIn('"status":"assembled"', output.call_args.args[0])


class NoPeriodicCatalogRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_map_refresh_does_not_page_the_recipe_catalog(self):
        """The frequent poll must not ask the backend for the catalog.

        The poll used to send a bare ``autoengineer_view``, which made the
        backend enumerate every recipe, recompute the technology
        fingerprint and enumerate every machine prototype on every poll.
        The poll now asks for the fast path, which skips the recipe
        adapter entirely.
        """
        control = ConsoleControl()
        calls = []

        async def read(name, arguments=None):
            calls.append((name, arguments))
            control.stop.set()
            return NS(is_error=False, content=[NS(type="text", text=json.dumps({
                "status": "ok", "surface": "nauvis", "tick": 10,
                "inventory": [], "inventory_available": True, "truncated": False,
                "x": 0, "y": 0, "catalog_status": {"status": "ok"},
            }))])

        with patch("dashboard_observer.assemble_catalog", new_callable=AsyncMock) as scan, patch(
            "builtins.print"
        ), patch("dashboard_observer.DashboardFeed") as feed:
            await observe(ViewOnly(NS(call_tool=read)), control, 0.001)
        self.assertEqual(calls, [("autoengineer_view", {"noCatalog": True})])
        scan.assert_not_awaited()
        feed.return_value.publish.assert_called_once()

    async def test_the_map_chunk_read_does_not_ask_for_the_catalog(self):
        """A chunk read never needs the recipe catalog."""
        from dashboard_observer import chunk_arguments
        arguments = chunk_arguments(2, -3)
        self.assertEqual(arguments["mapChunkX"], 2)
        self.assertEqual(arguments["mapChunkY"], -3)
        self.assertTrue(arguments["noCatalog"])

    async def test_the_catalog_observer_keeps_the_full_path(self):
        """The on-demand catalog observer still asks for the catalog."""
        control = ConsoleControl()
        calls = []

        async def read(name, arguments=None):
            calls.append((name, arguments))
            control.stop.set()
            return NS(is_error=False, content=[NS(type="text", text=json.dumps({
                "status": "ok", "surface": "nauvis", "tick": 10,
                "inventory": [], "inventory_available": True, "truncated": False,
                "x": 0, "y": 0, "catalog_status": {"status": "ok"},
            }))])

        with patch("dashboard_observer.assemble_catalog", new_callable=AsyncMock), patch(
            "builtins.print"
        ), patch("dashboard_observer.DashboardFeed"):
            await observe(ViewOnly(NS(call_tool=read), catalog_only=True),
                          control, 0.001, catalog_only=True)
        self.assertEqual(calls, [("autoengineer_view", {"catalogPageSize": 32,
                                                       "catalogOnly": True})])
        self.assertNotIn("noCatalog", calls[0][1])


class ViewOnlyNoCatalogArgumentTests(unittest.IsolatedAsyncioTestCase):
    """The read-only boundary validates the fast-path flag."""

    async def test_the_no_catalog_flag_is_accepted(self):
        """The fast flag passes the observer's own argument check."""
        seen = []

        async def read(name, arguments=None):
            seen.append((name, arguments))
            return NS(is_error=False, content=[])

        await ViewOnly(NS(call_tool=read)).call_tool(
            "autoengineer_view", {"noCatalog": True})
        self.assertEqual(seen, [("autoengineer_view", {"noCatalog": True})])

    async def test_a_non_boolean_no_catalog_flag_is_refused(self):
        """The flag must be a real boolean."""
        async def read(name, arguments=None):  # pragma: no cover - never called
            raise AssertionError("the invalid flag must be refused")

        for value in ("yes", 1, None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    await ViewOnly(NS(call_tool=read)).call_tool(
                        "autoengineer_view", {"noCatalog": value})

    async def test_a_catalog_read_cannot_suppress_the_catalog(self):
        """A catalog read that also suppresses the catalog is refused."""
        async def read(name, arguments=None):  # pragma: no cover - never called
            raise AssertionError("the invalid request must be refused")

        with self.assertRaises(ValueError):
            await ViewOnly(NS(call_tool=read)).call_tool(
                "autoengineer_view", {"catalogOnly": True, "noCatalog": True})


class ViewportPacingTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_chunk_reads_are_paced_not_dropped(self):
        control = NS(stop=asyncio.Event())
        requests = ViewportRequests()
        requests.offer({"center": {"x": 0, "y": 0},
                        "radius": {"x": 128, "y": 128}, "limit": 8})
        completed = set()
        feed = NS(cache=NS(needs_refresh=lambda *xy: xy not in completed),
                  publish=lambda raw: None)
        calls = []
        async def fetch(_session, x, y):
            calls.append((x, y))
            completed.add((x, y))
            return {"status": "ok"}
        with patch("dashboard_observer.observe_chunk", side_effect=fetch):
            for _ in range(8):
                await observe_viewport(None, feed, control, requests)
        self.assertEqual(len(calls), 8)
        self.assertEqual(len(set(calls)), 8)
        self.assertIsNone(requests._pending)


class ObserverWorkingDirectoryTests(unittest.TestCase):
    """The observer must publish frames from any working directory.

    The dashboard spawns the observer as a child process whose working
    directory is not the repository root, and the launcher spawns the
    dashboard itself from an unrelated runtime directory. A frame that
    carries 'capabilities' makes the observer import the read-only
    planning bridge, which imports the production solver. That import
    must resolve from the module location alone, so the observer never
    depends on the caller's working directory or on a PYTHONPATH
    override.
    """

    CHILD = """
import json, sys
sys.path.insert(0, sys.argv[1])
import dashboard_feed

raw = {
    "status": "ok", "x": 0.0, "y": 0.0, "tick": 1, "surface": "nauvis",
    "inventory": [], "inventory_available": True, "truncated": False,
    "capabilities": {
        "schema": 1, "tick": 1, "surface": "nauvis",
        "game_version": "2.1.23", "force": "player", "research": [],
        "enabled_content": ["base"], "truncated": False, "recipes": [],
        "source_fingerprint": "poly31x131-v1:0123456789-9876543210",
    },
}
try:
    frame = dashboard_feed.snapshot(raw)
    print(json.dumps({"ok": True, "surface": frame["surface"]}))
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
"""

    def _publish_from(self, cwd):
        env = dict(os.environ)
        # The observer must not need a PYTHONPATH override to import the
        # agent package; remove any inherited value to prove it.
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-c", self.CHILD, str(AGENT_DIR)],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_observer_publishes_a_capability_frame_from_a_foreign_cwd(self):
        for cwd in (AGENT_DIR, tempfile.gettempdir()):
            with self.subTest(cwd=str(cwd)):
                self.assertNotEqual(
                    Path(cwd).resolve(), REPO_ROOT, "cwd must not be the repository root"
                )
                result = self._publish_from(cwd)
                self.assertTrue(
                    result["ok"],
                    f"observer failed to publish from {cwd}: {result.get('error')}",
                )
                self.assertEqual(result["surface"], "nauvis")

    def test_the_agent_package_import_does_not_need_the_cwd_on_sys_path(self):
        """The production solver import must not depend on the working directory."""
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; sys.path.insert(0, sys.argv[1]);"
                " import production_solver;"
                " print(production_solver.base_gears_chain is not None)",
                str(AGENT_DIR),
            ],
            cwd=str(AGENT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("True", proc.stdout)


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
