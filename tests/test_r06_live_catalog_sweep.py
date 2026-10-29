"""Exercise pagination accounting without running a game or backend."""
import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import r06_live_catalog_sweep as catalog


def page(index, recipes, excluded):
    return {"status": "ok", "catalog_status": {"status": "ok", "total_pages": 2,
            "total_count": 4, "page_size": 2}, "capabilities": {
                "tick": index, "game_version": "2.1.23", "surface": "nauvis",
                "force": "player", "source_fingerprint": "same",
                "recipes": [{"name": name} for name in recipes], "excluded": excluded}}


class CatalogSweepAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_exclusions_from_every_page(self):
        first = page(1, ["a"], [{"name": "b", "reason": "recipe_shape"}])
        second = page(2, ["c"], [{"name": "d", "reason": "no_products"}])
        report = {}
        with patch.object(catalog, "call_view", AsyncMock(side_effect=[(first, .1), (second, .1)])), patch.object(catalog, "log"):
            await catalog.sweep(cast(Any, None), report)
        self.assertEqual([r["name"] for r in report["exclusions"]["rows"]], ["b", "d"])
        self.assertTrue(report["accounting"]["balanced"])
        self.assertFalse(report["pagination"]["single_tick"])

    async def test_failed_page_cannot_claim_balanced_catalog(self):
        first = page(1, ["a"], [{"name": "b", "reason": "recipe_shape"}])
        report = {}
        with patch.object(catalog, "call_view", AsyncMock(side_effect=[(first, .1), RuntimeError("offline")])), patch.object(catalog, "log"):
            await catalog.sweep(cast(Any, None), report)
        self.assertFalse(report["accounting"]["balanced"])
        self.assertEqual(report["pagination"]["errors"][0]["page"], 2)

    async def test_empty_lua_table_is_an_explicit_empty_exclusion_list(self):
        first = page(1, ["a", "b"], {})
        second = page(2, ["c", "d"], [])
        report = {}
        with patch.object(catalog, "call_view", AsyncMock(side_effect=[(first, .1), (second, .1)])), patch.object(catalog, "log"):
            await catalog.sweep(cast(Any, None), report)
        self.assertTrue(report["accounting"]["balanced"])
        self.assertEqual(report["exclusions"]["rows"], [])
