"""R04 recipe page assembly must fail closed on mixed or incomplete snapshots."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from catalog_assembly import CatalogAssemblyError, assemble_catalog
from dashboard_feed import snapshot
from read_only_planning import view_intelligence

FINGERPRINT = "poly31x131-v1:0123456789-9876543210"


def recipe(name):
    return {
        "name": name, "enabled": True, "hidden": False, "simple": True,
        "category": "crafting", "crafting_time": 1,
        "ingredients": [{"name": "iron-plate", "type": "item", "amount": 1}],
        "products": [{"name": name, "type": "item", "amount": 1}],
    }


def page(number, names, *, tick=120, fingerprint: str | None = FINGERPRINT, truncated=False,
         total_count=17, total_pages=2):
    return {
        "status": "ok", "x": 0, "y": 0, "tick": tick, "surface": "nauvis",
        "inventory": [], "inventory_available": True, "truncated": False,
        "catalog_status": {
            "page": number, "page_size": 16, "total_count": total_count,
            "total_pages": total_pages, "status": "ok",
        },
        "capabilities": {
            "schema": 1, "tick": tick, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player", "research": ["automation"],
            "enabled_content": ["base"], "truncated": truncated,
            "recipes": [recipe(name) for name in names],
            "source_fingerprint": fingerprint,
        },
    }


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        value = self.responses.pop(0)
        return NS(
            is_error=False,
            content=[NS(type="text", text=json.dumps(value))],
        )


class CatalogAssemblyTests(unittest.IsolatedAsyncioTestCase):
    async def test_assembles_pages_from_one_exact_snapshot(self):
        names = [f"recipe-{number:02d}" for number in range(17)]
        first = page(1, names[:16])
        second = page(2, names[16:])
        session = FakeSession([second])

        assembled = await assemble_catalog(session, first)

        self.assertEqual(
            session.calls,
            [("autoengineer_view", {"catalogPage": 2, "catalogPageSize": 16})],
        )
        parsed = snapshot(assembled)
        self.assertEqual(assembled["catalog_status"]["status"], "assembled")
        self.assertEqual(assembled["catalog_status"]["pages_collected"], 2)
        self.assertEqual([r["name"] for r in parsed["capabilities"]["recipes"]], names)
        self.assertFalse(parsed["capabilities"]["truncated"])

    async def test_rejects_tick_or_fingerprint_change(self):
        for second in (
            page(2, ["recipe-16"], tick=121),
            page(2, ["recipe-16"], fingerprint="poly31x131-v1:0000000001-0000000002"),
        ):
            with self.subTest(second_tick=second["tick"],
                              fingerprint=second["capabilities"]["source_fingerprint"]):
                with self.assertRaises(CatalogAssemblyError):
                    await assemble_catalog(FakeSession([second]), page(
                        1, [f"recipe-{n:02d}" for n in range(16)]
                    ))

    async def test_rejects_research_or_content_change_even_with_matching_fingerprint(self):
        first = page(1, [f"recipe-{n:02d}" for n in range(16)])
        for field, value in (("research", ["automation", "logistics"]),
                             ("enabled_content", ["base", "space-age"])):
            second = page(2, ["recipe-16"])
            second["capabilities"][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(CatalogAssemblyError, "changed during page assembly"):
                    await assemble_catalog(FakeSession([second]), first)

    async def test_marks_omitted_recipes_truncated_but_keeps_observation(self):
        first = page(1, [f"recipe-{n:02d}" for n in range(16)], truncated=True)
        assembled = await assemble_catalog(
            FakeSession([page(2, ["recipe-16"], truncated=True)]), first
        )
        data = snapshot(assembled)
        self.assertTrue(data["capabilities"]["truncated"])
        self.assertFalse(view_intelligence(
            dict(status="ok", **data), received_at=100
        )["planner_ready"])

    async def test_unassembled_page_cannot_enable_planning(self):
        raw = page(1, [f"recipe-{n:02d}" for n in range(16)])
        data = snapshot(raw)
        result = view_intelligence(dict(status="ok", **data), received_at=100)
        self.assertFalse(result["planner_ready"])
        self.assertEqual(result["reason"], "Recipe catalog pages are not fully assembled")

    async def test_rejects_overlapping_pages_and_missing_or_mismatched_counts(self):
        first = page(1, [f"recipe-{n:02d}" for n in range(16)])
        bad_pages = (
            page(2, ["recipe-15"]),
            page(2, ["recipe-16"], total_count=34),
            page(2, ["recipe-16"], total_pages=3),
        )
        for bad in bad_pages:
            with self.subTest(status=bad["catalog_status"]):
                with self.assertRaises(CatalogAssemblyError):
                    await assemble_catalog(FakeSession([bad]), first)

    async def test_empty_catalog_has_a_complete_but_not_planner_ready_assembly(self):
        empty = page(1, [], total_count=0, total_pages=0)
        result = await assemble_catalog(FakeSession([]), empty)
        parsed = snapshot(result)
        self.assertEqual(result["catalog_status"]["pages_collected"], 1)
        self.assertEqual(parsed["capabilities"]["recipes"], [])
        self.assertFalse(view_intelligence(
            dict(status="ok", **parsed), received_at=100
        )["planner_ready"])

    async def test_request_timeout_is_explicit(self):
        class HangingSession:
            async def call_tool(self, name, arguments):
                await asyncio.sleep(1)

        first = page(1, [f"recipe-{n:02d}" for n in range(16)])
        from unittest.mock import patch

        with patch("catalog_assembly.PAGE_TIMEOUT_SECONDS", 0.001):
            with self.assertRaisesRegex(CatalogAssemblyError, "timed out"):
                await assemble_catalog(HangingSession(), first)

    async def test_total_budget_is_checked_after_last_page(self):
        first = page(1, [f"recipe-{n:02d}" for n in range(16)])
        second = page(2, ["recipe-16"])
        times = iter((0, 0.25, 0.6))

        from unittest.mock import patch

        with patch("catalog_assembly.ASSEMBLY_TIMEOUT_SECONDS", 0.5):
            with self.assertRaisesRegex(CatalogAssemblyError, "time budget"):
                await assemble_catalog(
                    FakeSession([second]), first, monotonic=lambda: next(times)
                )

    async def test_multitick_missing_fingerprint_is_browsable_but_not_planner_ready(self):
        names = [f"modded-{n:02d}" for n in range(34)]
        first = page(1, names[:32], tick=100, fingerprint=None,
                     truncated=True, total_count=34, total_pages=2)
        second = page(2, names[32:], tick=220, fingerprint=None,
                      truncated=True, total_count=34, total_pages=2)
        for raw in (first, second):
            raw["catalog_status"]["page_size"] = 32
        session = FakeSession([second])
        result = await assemble_catalog(session, first, allow_multi_tick=True)
        recipes = result["capabilities"]["recipes"]
        if not isinstance(recipes, list):
            self.fail("assembled recipes must be a list")
        self.assertEqual(len(recipes), 34)
        self.assertTrue(result["capabilities"]["truncated"])
        self.assertIsNone(result["capabilities"]["source_fingerprint"])
        self.assertEqual(result["catalog_status"]["status"], "assembled")
        self.assertEqual(session.calls[0][1]["catalogPageSize"], 32)

    def test_large_modpack_bound_remains_consistent_with_planner(self):
        from catalog_assembly import MAX_CATALOG_ENTRIES, MAX_CATALOG_PAGES
        from read_only_planning import MAX_RECIPE_CATALOG_ROWS
        self.assertEqual(MAX_CATALOG_ENTRIES, MAX_CATALOG_PAGES * 16)
        self.assertEqual(MAX_CATALOG_ENTRIES, MAX_RECIPE_CATALOG_ROWS)

    async def test_multitick_rejects_changed_force(self):
        first = page(1, [f"a-{n:02d}" for n in range(16)],
                     fingerprint=None, truncated=True)
        second = page(2, ["z-last"], tick=200,
                      fingerprint=None, truncated=True)
        second["capabilities"]["force"] = "enemy"
        with self.assertRaises(CatalogAssemblyError):
            await assemble_catalog(FakeSession([second]), first,
                                   allow_multi_tick=True)

    async def test_immutable_catalog_preserves_all_explicit_exclusions(self):
        names=[f"recipe-{number:02d}" for number in range(17)]
        first=page(1,names[1:16])
        first["catalog_status"].update(snapshot=True,snapshot_tick=120,observation_tick=120)
        first["capabilities"]["excluded"]=[{"name":names[0],"reason":"unsupported_shape"}]
        second=page(2,names[16:])
        second["capabilities"]["excluded"]={}
        result=await assemble_catalog(FakeSession([second]),first)
        self.assertEqual(len(result["capabilities"]["recipes"]),16)
        self.assertEqual(result["capabilities"]["excluded"][0]["name"],names[0])
        self.assertFalse(result["capabilities"]["truncated"])
        snapshot(result)

    async def test_large_immutable_batches_keep_strict_assembly(self):
        names=[f"recipe-{number:03d}" for number in range(129)]
        first=page(1,names[:128],total_count=129,total_pages=2)
        second=page(2,names[128:],total_count=129,total_pages=2)
        for raw in (first,second):
            raw["catalog_status"].update(page_size=128,snapshot=True,snapshot_tick=120,observation_tick=120)
        result=await assemble_catalog(FakeSession([second]),first)
        self.assertEqual(len(result["capabilities"]["recipes"]),129)
        self.assertFalse(result["capabilities"]["truncated"])
