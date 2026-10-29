"""Regression tests for the shared Qt recipe/research catalog snapshot."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from qt_catalog import (  # noqa: E402
    catalog_snapshot,
    catalog_status_text,
)
from qt_observation import OBSERVED, STALE, UNAVAILABLE  # noqa: E402


def frame(*, truncated=False, status="assembled", recipes=None):
    return {
        "catalog_status": {
            "status": status,
            "page": 1,
            "page_size": 32,
            "total_count": 1,
            "total_pages": 1,
        },
        "capabilities": {
            "game_version": "2.1.23",
            "force": "player",
            "surface": "nauvis",
            "tick": 42,
            "truncated": truncated,
            "source_fingerprint": "catalog-v1:abc",
            "research": ["automation"],
            "recipes": recipes if recipes is not None else [{
                "name": "iron-gear-wheel",
                "enabled": True,
                "hidden": False,
                "category": "crafting",
                "categories": ["crafting"],
                "crafting_time": 0.5,
                "ingredients": [],
                "products": [],
            }],
            "machines": [{
                "name": "assembling-machine-2",
                "crafting_speed": 0.75,
            }],
        },
    }


class CatalogSnapshotTests(unittest.TestCase):
    def test_observed_catalog_preserves_the_authoritative_rows(self):
        snapshot = catalog_snapshot(frame())
        self.assertTrue(snapshot.known)
        self.assertEqual(snapshot.recipes[0]["name"], "iron-gear-wheel")
        self.assertEqual(snapshot.research, ("automation",))
        self.assertEqual(snapshot.machines[0]["name"], "assembling-machine-2")
        self.assertEqual(snapshot.game_version, "2.1.23")
        self.assertEqual(snapshot.tick, 42)
        self.assertTrue(snapshot.complete)

    def test_missing_catalog_is_not_an_empty_complete_catalog(self):
        snapshot = catalog_snapshot(None)
        self.assertFalse(snapshot.known)
        self.assertFalse(snapshot.complete)
        self.assertEqual(snapshot.recipes, ())
        self.assertIn("unavailable", catalog_status_text(snapshot).lower())

    def test_a_truncated_assembled_catalog_remains_partial(self):
        snapshot = catalog_snapshot(frame(truncated=True))
        self.assertFalse(snapshot.complete)
        self.assertIn("Partial catalog", catalog_status_text(snapshot))

    def test_a_single_page_is_explicitly_partial(self):
        snapshot = catalog_snapshot(frame(status="ok"))
        self.assertFalse(snapshot.complete)
        self.assertIn("Partial catalog page", catalog_status_text(snapshot))

    def test_a_stale_catalog_keeps_its_rows_but_not_its_completeness_claim(self):
        snapshot = catalog_snapshot(frame(), state=STALE, detail="backoff")
        self.assertTrue(snapshot.known)
        self.assertEqual(snapshot.state, STALE)
        self.assertIn("Stale", catalog_status_text(snapshot))

    def test_an_unavailable_catalog_keeps_no_observed_rows(self):
        snapshot = catalog_snapshot(frame(), state=UNAVAILABLE)
        self.assertFalse(snapshot.known)
        self.assertEqual(snapshot.recipes, ())
        self.assertEqual(snapshot.research, ())

    def test_malformed_rows_and_names_are_omitted(self):
        source = frame()
        source["capabilities"]["recipes"] = ["bad", {"name": "valid"}]
        source["capabilities"]["research"] = ["ok", "bad\nvalue"]
        snapshot = catalog_snapshot(source)
        self.assertEqual(len(snapshot.recipes), 1)
        self.assertEqual(snapshot.research, ("ok",))

    def test_observed_state_is_the_default(self):
        self.assertEqual(catalog_snapshot(frame()).state, OBSERVED)


class BackendCatalogShapeTests(unittest.TestCase):
    """The backend's own catalog frame shape must be read faithfully."""

    def test_the_backend_total_and_page_count_are_read(self):
        """The backend reports "total" and "page_count", not the mod's names."""
        snapshot = catalog_snapshot({
            "catalog_status": {
                "page": 1, "page_size": 16, "status": "ok",
                "total": 662, "page_count": 42, "partial": False,
            },
            "capabilities": {
                "recipes": [{"name": "iron-gear-wheel"}],
                "research": [], "current_research": "automation",
            },
        })
        self.assertEqual(snapshot.total_count, 662)
        self.assertEqual(snapshot.total_pages, 42)
        self.assertEqual(snapshot.page, 1)
        self.assertEqual(len(snapshot.recipes), 1)

    def test_the_backend_research_rows_are_read_as_names(self):
        """The backend carries one row object per researched technology."""
        snapshot = catalog_snapshot({
            "catalog_status": {"status": "ok", "page": 1},
            "capabilities": {
                "recipes": [],
                "research": [{"name": "automation"}, {"name": "logistics"}],
            },
        })
        self.assertEqual(snapshot.research, ("automation", "logistics"))

    def test_plain_research_names_are_still_read(self):
        """The mod's own envelope carries plain names."""
        snapshot = catalog_snapshot({
            "catalog_status": {"status": "ok", "page": 1},
            "capabilities": {
                "recipes": [], "research": ["automation"],
            },
        })
        self.assertEqual(snapshot.research, ("automation",))

    def test_a_backend_catalog_page_is_not_reported_as_unavailable(self):
        """A real catalog page must not be labelled unavailable."""
        snapshot = catalog_snapshot({
            "catalog_status": {
                "page": 1, "page_size": 16, "status": "ok",
                "total": 662, "page_count": 42, "partial": False,
            },
            "capabilities": {
                "recipes": [{"name": "iron-gear-wheel"}],
                "research": [{"name": "automation"}],
            },
        })
        self.assertTrue(snapshot.known)
        self.assertEqual(snapshot.status, "ok")
        self.assertNotIn("unavailable",
                         catalog_status_text(snapshot).lower())


if __name__ == "__main__":
    unittest.main()


class ExcludedCatalogSnapshotTests(unittest.TestCase):
    def test_unsupported_recipe_is_accounted_without_becoming_supported(self):
        raw=frame()
        raw["catalog_status"]["total_count"]=2
        raw["capabilities"]["excluded"]=[{"name":"unsupported","reason":"shape"}]
        snapshot=catalog_snapshot(raw)
        self.assertTrue(snapshot.complete)
        self.assertEqual(len(snapshot.recipes),1)
        self.assertIn("1 explicitly unsupported",catalog_status_text(snapshot))

    def test_stale_or_overlapping_coverage_cannot_claim_completeness(self):
        self.assertFalse(catalog_snapshot(frame(),state=STALE).complete)
        raw=frame()
        raw["catalog_status"]["total_count"]=2
        raw["capabilities"]["excluded"]=[{"name":"iron-gear-wheel","reason":"shape"}]
        self.assertFalse(catalog_snapshot(raw).complete)


class PartialAssemblyLabelTests(unittest.TestCase):
    def test_missing_pages_are_not_labeled_complete(self):
        raw=frame()
        raw["catalog_status"]["total_count"]=100
        snapshot=catalog_snapshot(raw)
        self.assertFalse(snapshot.complete)
        self.assertIn("Partial catalog",catalog_status_text(snapshot))
