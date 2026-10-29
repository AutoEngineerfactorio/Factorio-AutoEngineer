"""Regression tests for the Qt observed-catalog workspace."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication
    import qt_catalog_widget

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    QT_AVAILABLE = False


def frame(recipes=None):
    return {
        "catalog_status": {
            "status": "assembled",
            "page": 1,
            "page_size": 32,
            "total_count": len(recipes or [1]),
            "total_pages": 1,
        },
        "capabilities": {
            "game_version": "2.1.23",
            "force": "player",
            "surface": "nauvis",
            "tick": 42,
            "truncated": False,
            "source_fingerprint": "catalog-v1:abc",
            "research": ["automation"],
            "recipes": recipes if recipes is not None else [{
                "name": "iron-gear-wheel",
                "enabled": True,
                "hidden": False,
                "category": "crafting",
                "categories": ["crafting"],
                "crafting_time": 0.5,
                "ingredients": [{"type": "item", "name": "iron-plate"}],
                "products": [{"type": "item", "name": "iron-gear-wheel"}],
            }],
            "machines": [{
                "name": "assembling-machine-2",
                "crafting_speed": 0.75,
                "energy_usage": "150 kW",
            }],
        },
    }


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is not installed")
class CatalogWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widget = qt_catalog_widget.CatalogWidget()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()

    def test_an_observed_catalog_is_rendered(self):
        self.widget.set_frame(frame())
        self.assertEqual(self.widget.recipe_table.rowCount(), 1)
        self.assertEqual(
            self.widget.recipe_table.item(0, 0).text(), "iron-gear-wheel")
        self.assertEqual(self.widget.machine_table.rowCount(), 1)
        self.assertEqual(
            self.widget.machine_table.item(0, 0).text(), "assembling-machine-2")

    def test_a_missing_catalog_is_not_rendered_as_an_empty_complete_catalog(self):
        self.widget.set_frame(None)
        self.assertEqual(self.widget.recipe_table.rowCount(), 0)
        self.assertEqual(self.widget.machine_table.rowCount(), 0)
        self.assertIn("unavailable", self.widget.status.text().lower())

    def test_search_uses_observed_ingredients_and_products(self):
        self.widget.set_frame(frame())
        self.widget.search.setText("iron-plate")
        self.assertEqual(self.widget.recipe_table.rowCount(), 1)
        self.widget.search.setText("not-present")
        self.assertEqual(self.widget.recipe_table.rowCount(), 0)

    def test_a_partial_catalog_is_explicit(self):
        source = frame()
        source["capabilities"]["truncated"] = True
        self.widget.set_frame(source)
        self.assertIn("partial", self.widget.status.text().lower())
        self.assertIn("planning remains unavailable", self.widget.status.text())

    def test_hidden_and_disabled_recipes_keep_their_observed_state(self):
        source = frame([
            {"name": "hidden-recipe", "enabled": True, "hidden": True,
             "category": "crafting", "crafting_time": 1,
             "ingredients": [], "products": []},
            {"name": "disabled-recipe", "enabled": False, "hidden": False,
             "category": "crafting", "crafting_time": 1,
             "ingredients": [], "products": []},
        ])
        self.widget.set_frame(source)
        self.assertEqual(self.widget.recipe_table.item(0, 1).text(), "Hidden")
        self.assertEqual(self.widget.recipe_table.item(1, 1).text(), "Disabled")

    def test_the_visible_row_limit_is_bounded(self):
        recipes = [{
            "name": f"recipe-{index}", "enabled": True, "hidden": False,
            "category": "crafting", "crafting_time": 1,
            "ingredients": [], "products": [],
        } for index in range(qt_catalog_widget.MAX_VISIBLE_ROWS + 3)]
        self.widget.set_frame(frame(recipes))
        self.assertEqual(
            self.widget.recipe_table.rowCount(), qt_catalog_widget.MAX_VISIBLE_ROWS)
        self.assertIn("matching recipes", self.widget.status.text())

    def test_refresh_is_a_request_not_a_fetch(self):
        """The widget asks for a refresh; it never fetches by itself."""
        requests = []
        self.widget.refreshRequested.connect(lambda: requests.append("refresh"))
        self.widget.refresh_button.click()
        self.assertEqual(requests, ["refresh"])

    def test_load_more_is_a_request_not_a_fetch(self):
        requests = []
        self.widget.loadMoreRequested.connect(lambda: requests.append("more"))
        # The button is only enabled when the game reported more pages, so
        # the request path is exercised through the same enabled state the
        # user sees.
        source = frame()
        source["catalog_status"]["total_pages"] = 3
        self.widget.set_frame(source)
        self.assertTrue(self.widget.load_more_button.isEnabled())
        self.widget.load_more_button.click()
        self.assertEqual(requests, ["more"])

    def test_load_more_is_disabled_until_the_game_reports_more_pages(self):
        source = frame()
        source["catalog_status"]["total_pages"] = 1
        self.widget.set_frame(source)
        self.assertFalse(self.widget.load_more_button.isEnabled())

    def test_load_more_is_enabled_when_more_pages_are_reported(self):
        source = frame()
        source["catalog_status"]["total_pages"] = 3
        self.widget.set_frame(source)
        self.assertTrue(self.widget.load_more_button.isEnabled())

    def test_counts_show_the_real_totals(self):
        source = frame()
        source["catalog_status"]["total_count"] = 1234
        source["catalog_status"]["total_pages"] = 3
        self.widget.set_frame(source)
        text = self.widget.counts.text()
        self.assertIn("1 recipes", text)
        self.assertIn("1234 recipes reported", text)
        self.assertIn("1 researched", text)
        self.assertIn("1 machines", text)

    def test_ingredients_and_products_are_rendered(self):
        self.widget.set_frame(frame())
        self.assertEqual(
            self.widget.recipe_table.item(0, 4).text(), "item:iron-plate")
        self.assertEqual(
            self.widget.recipe_table.item(0, 5).text(), "item:iron-gear-wheel")

    def test_a_recipe_without_observed_parts_shows_an_em_dash(self):
        source = frame([{"name": "bare-recipe", "enabled": True,
                         "hidden": False, "category": "crafting",
                         "crafting_time": 1}])
        self.widget.set_frame(source)
        self.assertEqual(self.widget.recipe_table.item(0, 4).text(), "—")
        self.assertEqual(self.widget.recipe_table.item(0, 5).text(), "—")

    def test_an_unobserved_availability_stays_unknown(self):
        source = frame([{"name": "no-state-recipe", "category": "crafting"}])
        self.widget.set_frame(source)
        self.assertEqual(self.widget.recipe_table.item(0, 1).text(), "Unknown")

    def test_researched_technologies_are_rendered(self):
        source = frame()
        source["capabilities"]["research"] = ["automation", "logistics"]
        self.widget.set_frame(source)
        self.assertEqual(self.widget.research_table.rowCount(), 2)
        self.assertEqual(
            self.widget.research_table.item(0, 0).text(), "automation")

    def test_machine_fluid_boxes_are_rendered(self):
        source = frame()
        source["capabilities"]["machines"] = [{
            "name": "oil-refinery", "crafting_speed": 1,
            "energy_usage": "420 kW",
            "fluid_boxes": [{"production_type": "input", "filter": "water"}],
        }]
        self.widget.set_frame(source)
        self.assertEqual(
            self.widget.machine_table.item(0, 3).text(), "input:water")

    def test_an_assembly_is_shown_with_its_counts(self):
        from qt_catalog_pages import CatalogPager

        def fetch(page):
            return {
                "catalog_status": {
                    "status": "ok", "page": page, "page_size": 2,
                    "total_count": 4, "total_pages": 2,
                },
                "capabilities": {
                    "recipes": [{"name": f"recipe-{page}", "enabled": True,
                                 "hidden": False, "category": "crafting"}],
                    "machines": [], "research": [],
                    "truncated": False, "source_fingerprint": "fp",
                },
            }

        pager = CatalogPager(page_size=2, fetch=fetch)
        self.widget.set_pager(pager)
        assembly = pager.assemble()
        self.widget.set_assembly(assembly)
        shown = self.widget.assembly
        assert shown is not None
        self.assertEqual(shown.pages_loaded, (1, 2))
        self.assertEqual(self.widget.recipe_table.rowCount(), 2)
        self.assertIn("2 recipes", self.widget.counts.text())

    def test_an_applied_page_is_remembered_by_the_pager(self):
        from qt_catalog_pages import CatalogPager

        pager = CatalogPager(page_size=2)
        self.widget.set_pager(pager)
        self.widget.apply_page(frame())
        self.assertTrue(pager.has_page(1))

    def test_a_missing_catalog_disables_load_more(self):
        self.widget.set_frame(None)
        self.assertFalse(self.widget.load_more_button.isEnabled())
        self.assertEqual(self.widget.counts.text(), "")


    def test_background_pages_accumulate_until_catalog_is_complete(self):
        first=frame([{"name":"a"},{"name":"b"}])
        first["catalog_status"].update(status="ok",page=1,page_size=2,total_count=3,total_pages=2)
        second=frame([{"name":"c"}])
        second["catalog_status"].update(status="ok",page=2,page_size=2,total_count=3,total_pages=2)
        self.assertFalse(self.widget.apply_page(first).complete)
        final=self.widget.apply_page(second)
        self.assertTrue(final.complete)
        self.assertEqual([r["name"] for r in final.recipes],["a","b","c"])
        self.assertEqual(self.widget.recipe_table.rowCount(),3)


    def test_identical_snapshot_does_not_rebuild_visible_tables(self):
        from unittest.mock import patch

        from qt_catalog import catalog_snapshot
        snapshot=catalog_snapshot(frame())
        with patch.object(self.widget,"_fill_machines",wraps=self.widget._fill_machines) as machines:
            self.widget.set_snapshot(snapshot)
            original=self.widget.recipe_table.item(0,0)
            self.widget.set_snapshot(snapshot)
            self.assertEqual(machines.call_count,1)
            self.assertIs(self.widget.recipe_table.item(0,0),original)


if __name__ == "__main__":
    unittest.main()
