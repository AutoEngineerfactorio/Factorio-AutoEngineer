"""Regression tests for the bounded multi-page catalog assembly."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from qt_catalog_pages import (  # noqa: E402
    MAX_CACHED_PAGES,
    CatalogPager,
    page_from_frame,
)


def _frame(page: int, *, total: int = 6, page_size: int = 2,
           fingerprint: str = "fp-1", truncated: bool = False,
           status: str = "ok") -> dict:
    """Return one synthetic observed catalog page frame."""
    first = (page - 1) * page_size
    last = min(first + page_size, total)
    recipes = [
        {"name": f"recipe-{index}", "category": "crafting"}
        for index in range(first, last)
    ]
    machines = [
        {"name": f"machine-{index}", "crafting_speed": 1.0}
        for index in range(first, last)
    ]
    return {
        "capabilities": {
            "schema": 1,
            "game_version": "2.1.23",
            "recipes": recipes,
            "machines": machines,
            "research": ["automation"],
            "truncated": truncated,
            "source_fingerprint": fingerprint,
        },
        "catalog_status": {
            "page": page,
            "page_size": page_size,
            "total_count": total,
            "total_pages": (total + page_size - 1) // page_size,
            "status": status,
        },
    }


class PageFromFrameTests(unittest.TestCase):
    """The page reader must reflect only what the frame really carried."""

    def test_reads_rows_and_counts(self):
        page = page_from_frame(_frame(1))
        self.assertEqual(page.page, 1)
        self.assertEqual(len(page.recipes), 2)
        self.assertEqual(len(page.machines), 2)
        self.assertEqual(page.research, ("automation",))
        self.assertEqual(page.total_count, 6)
        self.assertEqual(page.total_pages, 3)
        self.assertFalse(page.truncated)

    def test_missing_capabilities_is_an_empty_page(self):
        page = page_from_frame({})
        self.assertTrue(page.empty)
        self.assertEqual(page.recipes, ())
        self.assertEqual(page.machines, ())
        self.assertEqual(page.research, ())

    def test_none_frame_is_an_empty_page(self):
        page = page_from_frame(None)
        self.assertTrue(page.empty)
        self.assertIsNone(page.total_count)

    def test_truncation_is_preserved(self):
        page = page_from_frame(_frame(1, truncated=True))
        self.assertTrue(page.truncated)


class CatalogPagerTests(unittest.TestCase):
    """The pager must be bounded, cached and honest."""

    def test_assembles_every_page(self):
        calls: list[int] = []

        def fetch(page: int):
            calls.append(page)
            return _frame(page)

        pager = CatalogPager(page_size=2, fetch=fetch)
        assembly = pager.assemble()
        self.assertEqual(assembly.pages_loaded, (1, 2, 3))
        self.assertEqual(len(assembly.snapshot.recipes), 6)
        self.assertEqual(len(assembly.snapshot.machines), 6)
        self.assertTrue(assembly.complete)
        self.assertEqual(calls, [1, 2, 3])

    def test_cached_page_is_not_requested_twice(self):
        calls: list[int] = []

        def fetch(page: int):
            calls.append(page)
            return _frame(page)

        pager = CatalogPager(page_size=2, fetch=fetch)
        pager.load_page(1)
        pager.load_page(1)
        self.assertEqual(calls, [1])
        self.assertTrue(pager.has_page(1))

    def test_assemble_reuses_the_cache(self):
        calls: list[int] = []

        def fetch(page: int):
            calls.append(page)
            return _frame(page)

        pager = CatalogPager(page_size=2, fetch=fetch)
        pager.assemble()
        calls.clear()
        pager.assemble()
        self.assertEqual(calls, [])

    def test_missing_page_stops_and_is_reported(self):
        def fetch(page: int):
            if page == 2:
                return None
            return _frame(page)

        pager = CatalogPager(page_size=2, fetch=fetch)
        assembly = pager.assemble()
        self.assertEqual(assembly.pages_loaded, (1,))
        self.assertEqual(assembly.missing_pages, (2,))
        self.assertFalse(assembly.complete)
        self.assertIn("Partial catalog", assembly.detail)

    def test_no_fetch_function_yields_no_catalog(self):
        pager = CatalogPager(page_size=2)
        assembly = pager.assemble()
        self.assertEqual(assembly.pages_loaded, ())
        self.assertFalse(assembly.complete)
        self.assertEqual(assembly.snapshot.recipes, ())

    def test_page_budget_is_bounded(self):
        calls: list[int] = []

        def fetch(page: int):
            calls.append(page)
            return _frame(page, total=1000, page_size=2)

        pager = CatalogPager(page_size=2, max_pages=3, fetch=fetch)
        assembly = pager.assemble()
        self.assertEqual(len(assembly.pages_loaded), 3)
        self.assertEqual(len(calls), 3)
        self.assertFalse(assembly.complete)

    def test_assemble_respects_the_page_argument(self):
        calls: list[int] = []

        def fetch(page: int):
            calls.append(page)
            return _frame(page)

        pager = CatalogPager(page_size=2, fetch=fetch)
        assembly = pager.assemble(pages=1)
        self.assertEqual(assembly.pages_loaded, (1,))
        self.assertEqual(calls, [1])

    def test_duplicate_rows_are_merged_once(self):
        def fetch(page: int):
            frame = _frame(page, total=6, page_size=2)
            # Every page repeats the same first recipe.
            frame["capabilities"]["recipes"].insert(
                0, {"name": "recipe-0", "category": "crafting"})
            return frame

        pager = CatalogPager(page_size=2, fetch=fetch)
        assembly = pager.assemble()
        names = [row["name"] for row in assembly.snapshot.recipes]
        self.assertEqual(len(names), len(set(names)))

    def test_changed_fingerprint_drops_the_old_pages(self):
        """A fetch that reveals a new fingerprint drops the stale pages."""
        state = {"fingerprint": "fp-1"}
        calls: list[int] = []

        def fetch(page: int):
            calls.append(page)
            return _frame(page, fingerprint=state["fingerprint"])

        pager = CatalogPager(page_size=2, fetch=fetch)
        pager.load_page(1)
        self.assertEqual(pager.cached_pages(), (1,))

        # The catalog content changed. Fetching page 2 reports the new
        # fingerprint, so the stale page 1 is dropped instead of being mixed
        # with the new content.
        state["fingerprint"] = "fp-2"
        pager.load_page(2)
        self.assertEqual(pager.cached_pages(), (2,))
        self.assertEqual(pager._pages[2].fingerprint, "fp-2")
        self.assertEqual(calls, [1, 2])

    def test_cached_page_is_reused_while_the_fingerprint_holds(self):
        calls: list[int] = []

        def fetch(page: int):
            calls.append(page)
            return _frame(page, fingerprint="fp-1")

        pager = CatalogPager(page_size=2, fetch=fetch)
        pager.load_page(1)
        pager.load_page(1)
        self.assertEqual(calls, [1])
        self.assertEqual(pager.cached_pages(), (1,))

    def test_cache_is_bounded(self):
        def fetch(page: int):
            return _frame(page, total=1000, page_size=2)

        pager = CatalogPager(page_size=2, fetch=fetch)
        for page in range(1, MAX_CACHED_PAGES + 5):
            pager.load_page(page)
        self.assertLessEqual(len(pager.cached_pages()), MAX_CACHED_PAGES)

    def test_truncated_catalog_is_not_complete(self):
        def fetch(page: int):
            return _frame(page, truncated=True)

        pager = CatalogPager(page_size=2, fetch=fetch)
        assembly = pager.assemble()
        self.assertFalse(assembly.complete)
        self.assertTrue(assembly.snapshot.truncated)

    def test_page_out_of_range_ends_the_walk(self):
        def fetch(page: int):
            return _frame(page, status="page_out_of_range")

        pager = CatalogPager(page_size=2, fetch=fetch)
        assembly = pager.assemble()
        self.assertEqual(len(assembly.pages_loaded), 1)
        self.assertFalse(assembly.complete)

    def test_counts_report_the_real_totals(self):
        def fetch(page: int):
            return _frame(page)

        pager = CatalogPager(page_size=2, fetch=fetch)
        assembly = pager.assemble()
        counts = assembly.counts()
        self.assertEqual(counts["recipes"], 6)
        self.assertEqual(counts["machines"], 6)
        self.assertEqual(counts["research"], 1)
        self.assertEqual(counts["total_recipes"], 6)
        self.assertEqual(counts["total_pages"], 3)

    def test_invalid_page_is_rejected(self):
        pager = CatalogPager(page_size=2)
        with self.assertRaises(ValueError):
            pager.load_page(0)
        with self.assertRaises(ValueError):
            pager.load_page(-1)

    def test_invalid_page_size_is_rejected(self):
        with self.assertRaises(ValueError):
            CatalogPager(page_size=0)
        with self.assertRaises(ValueError):
            CatalogPager(page_size=999)

    def test_invalid_page_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            CatalogPager(page_size=2, max_pages=0)

    def test_clear_drops_the_cache(self):
        pager = CatalogPager(page_size=2, fetch=lambda page: _frame(page))
        pager.load_page(1)
        pager.clear()
        self.assertEqual(pager.cached_pages(), ())


class ConfigurableCacheBoundTests(unittest.TestCase):
    """The cache bound comes from the settings, not from a constant."""

    def test_an_explicit_bound_is_used(self):
        pager = CatalogPager(max_cached_pages=3)
        self.assertEqual(pager.max_cached_pages, 3)

    def test_the_bound_evicts_the_oldest_page(self):
        pager = CatalogPager(max_cached_pages=2)
        for page in (1, 2, 3):
            pager.remember_page(page_from_frame(_frame(page)))
        self.assertEqual(pager.cached_pages(), (2, 3))

    def test_a_bound_of_one_keeps_only_the_newest_page(self):
        pager = CatalogPager(max_cached_pages=1)
        for page in (1, 2):
            pager.remember_page(page_from_frame(_frame(page)))
        self.assertEqual(pager.cached_pages(), (2,))

    def test_the_default_bound_is_bounded(self):
        pager = CatalogPager()
        self.assertGreaterEqual(pager.max_cached_pages, 1)
        self.assertLessEqual(pager.max_cached_pages, MAX_CACHED_PAGES)

    def test_a_nonsense_bound_falls_back(self):
        pager = CatalogPager(max_cached_pages="many")  # pyright: ignore[reportArgumentType]
        self.assertGreaterEqual(pager.max_cached_pages, 1)
        self.assertLessEqual(pager.max_cached_pages, MAX_CACHED_PAGES)


class ProfileAwareCacheTests(unittest.TestCase):
    """A page is only served for the context it was observed in."""

    def test_the_same_context_keeps_the_pages(self):
        from cache_context import CacheContext

        context = CacheContext("p1", "2.1.23", "fp", "nauvis", "f")
        pager = CatalogPager(context=context)
        pager.remember_page(page_from_frame(_frame(1)))
        self.assertEqual(pager.cached_pages(), (1,))

    def test_a_different_profile_drops_the_pages(self):
        from cache_context import CacheContext

        pager = CatalogPager(context=CacheContext("p1", "2.1.23", "fp", "n", "f"))
        pager.remember_page(page_from_frame(_frame(1)))
        dropped = pager.set_context(CacheContext("p2", "2.1.23", "fp", "n", "f"))
        self.assertTrue(dropped)
        self.assertEqual(pager.cached_pages(), ())

    def test_a_different_mod_fingerprint_drops_the_pages(self):
        from cache_context import CacheContext

        pager = CatalogPager(context=CacheContext("p1", "2.1.23", "fp1", "n", "f"))
        pager.remember_page(page_from_frame(_frame(1)))
        dropped = pager.set_context(CacheContext("p1", "2.1.23", "fp2", "n", "f"))
        self.assertTrue(dropped)
        self.assertEqual(pager.cached_pages(), ())

    def test_the_same_context_drops_nothing(self):
        from cache_context import CacheContext

        context = CacheContext("p1", "2.1.23", "fp", "n", "f")
        pager = CatalogPager(context=context)
        pager.remember_page(page_from_frame(_frame(1)))
        dropped = pager.set_context(context)
        self.assertFalse(dropped)
        self.assertEqual(pager.cached_pages(), (1,))

    def test_the_context_is_reported(self):
        from cache_context import CacheContext

        context = CacheContext("p1", "2.1.23", "fp", "n", "f")
        pager = CatalogPager(context=context)
        self.assertIs(pager.context, context)


if __name__ == "__main__":
    unittest.main()


class SnapshotCoveragePagerTests(unittest.TestCase):
    def test_explicit_exclusions_and_identity_survive_assembly(self):
        def fetch(number):
            raw=_frame(number,total=4,page_size=2)
            raw["capabilities"].update(tick=42,game_version="2.1.23",force="player",surface="nauvis")
            if number==1:
                raw["capabilities"]["recipes"].pop(0)
                raw["capabilities"]["excluded"]=[{"name":"recipe-0","reason":"shape"}]
            return raw
        result=CatalogPager(page_size=2,fetch=fetch).assemble()
        self.assertTrue(result.complete)
        self.assertTrue(result.snapshot.complete)
        self.assertEqual(result.snapshot.tick,42)
        self.assertEqual(len(result.snapshot.excluded),1)

    def test_changed_snapshot_cannot_be_mixed(self):
        def fetch(number):
            raw=_frame(number,total=4,page_size=2)
            raw["capabilities"]["tick"]=number
            return raw
        with self.assertRaisesRegex(ValueError,"snapshot changed"):
            CatalogPager(page_size=2,fetch=fetch).assemble()

    def test_pyanodons_sized_catalog_fits_bounded_pager(self):
        result=CatalogPager(page_size=32,fetch=lambda n:_frame(n,total=10146,page_size=32)).assemble()
        self.assertTrue(result.complete)
        self.assertEqual(len(result.snapshot.recipes),10146)


class SnapshotBatchPagerTests(unittest.TestCase):
    def test_full_pyanodons_catalog_uses_eighty_bounded_batches(self):
        result=CatalogPager(page_size=128,fetch=lambda n:_frame(n,total=10146,page_size=128)).assemble()
        self.assertTrue(result.complete)
        self.assertEqual(len(result.pages_loaded),80)
        with self.assertRaises(ValueError):
            CatalogPager(page_size=129)


class SharedSnapshotMetadataTests(unittest.TestCase):
    def test_equal_machine_metadata_is_shared_across_cached_pages(self):
        def fetch(number):
            raw=_frame(number,total=4,page_size=2)
            raw["capabilities"]["machines"]=[{"name":"same-machine","crafting_speed":1}]
            return raw
        pager=CatalogPager(page_size=2,fetch=fetch)
        first=pager.load_page(1)
        second=pager.load_page(2)
        assert first is not None and second is not None
        self.assertIs(first.machines,second.machines)
