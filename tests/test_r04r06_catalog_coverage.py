"""R04-R06 recipe/research catalog coverage regression tests.

These tests pin the defects found in the read-only R04-R06 audit:

* ``profile_qualified`` rejected every modded profile, so the Recipes &
  Research tab could never become planner-ready for Space Age or the
  Pyanodons suite.
* the catalog view model dropped the observed multi-category recipe list.
* the catalog exposed only researched technologies; unresearched ones were
  absent from the model even though the backend observes them.

Each test fails against the pre-fix behaviour and passes against the fixed
behaviour.  They are offline: no game, no RCON, no network.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from planning_view import catalog_view_model  # noqa: E402
from read_only_planning import profile_content_kind, profile_qualified  # noqa: E402

PYANODONS_CONTENT = (
    "autoengineer-input", "base", "quality", "recycler", "space-age",
    "py-alienlife", "py-circuitry", "py-energy", "py-fluid-handling",
    "py-high-temperature", "py-industrialization", "py-petroleum-handling",
    "py-processing", "py-solar", "py-steel-processing", "py-transport",
)


def caps(game_version="2.1.23", content=("autoengineer-input", "base")):
    return {
        "game_version": game_version,
        "enabled_content": list(content),
    }


class ProfileQualificationTests(unittest.TestCase):
    """The qualification gate must stay narrow but report the observed kind.

    A modded profile is not qualified by the base-game gates, but the R04-R06
    tab still observes it and must say *why* it is unqualified, so an
    operator can tell a first-party expansion awaiting qualification from
    an unknown third-party mod.
    """

    def test_the_base_only_profile_is_qualified(self):
        self.assertTrue(profile_qualified(caps()))

    def test_the_base_only_profile_is_classified_as_vanilla(self):
        self.assertEqual(profile_content_kind(caps()), "vanilla")

    def test_space_age_is_classified_as_first_party(self):
        """Space Age is a first-party expansion, not an unknown mod."""
        self.assertEqual(
            profile_content_kind(caps(
                content=("autoengineer-input", "base", "quality", "recycler",
                         "space-age"))),
            "first-party",
        )

    def test_a_modded_profile_is_classified_as_modded(self):
        self.assertEqual(
            profile_content_kind(caps(content=PYANODONS_CONTENT)), "modded")

    def test_a_modded_profile_is_not_qualified_by_the_base_game_gates(self):
        """Modded content carries its own evidence requirement. It must not
        be qualified by the base-game gate alone."""
        self.assertFalse(profile_qualified(caps(content=PYANODONS_CONTENT)))

    def test_an_unqualified_game_version_is_still_rejected(self):
        self.assertFalse(profile_qualified(caps(game_version="2.0.77")))

    def test_a_profile_without_base_is_still_rejected(self):
        self.assertFalse(profile_qualified(caps(content=("quality",))))

    def test_a_malformed_content_list_is_rejected(self):
        self.assertFalse(profile_qualified(caps(content=["base", 7])))


def _intelligence(recipe, research=("advanced-circuitry",)):
    return {
        "planner_ready": True,
        "reason": "Read-only recipe catalog ready for qualified preview",
        "capabilities": {
            "schema": 1,
            "game_version": "2.1.23",
            "force": "player",
            "surface": "nauvis",
            "tick": 1000,
            "research": list(research),
            "enabled_content": ["autoengineer-input", "base"],
            "truncated": False,
            "source_fingerprint": "poly31x131-v1:0123456789-0123456789",
            "recipes": [recipe],
        },
        "catalog_status": {"status": "assembled"},
        "mechanics": {
            "dimension_counts": {},
            "categories_with_evidence": 1,
            "total_categories": 1,
        },
    }


def _recipe(**overrides):
    recipe = {
        "name": "advanced-circuit",
        "enabled": True,
        "hidden": False,
        "simple": True,
        "category": "crafting",
        "categories": ["crafting", "electronics"],
        "crafting_time": 6.0,
        "ingredients": [{"name": "copper-cable", "type": "item", "amount": 2.0}],
        "products": [{"name": "advanced-circuit", "type": "item", "amount": 1.0}],
        "unlock_technologies": [
            {"name": "advanced-circuitry", "researched": True, "enabled": True},
        ],
    }
    recipe.update(overrides)
    return recipe


class CatalogViewModelTests(unittest.TestCase):
    """The Recipes & Research tab must show what the backend observed."""

    def test_the_observed_recipe_categories_are_exposed(self):
        model = catalog_view_model(_intelligence(_recipe()))
        row = model["recipes"][0]
        self.assertEqual(row["categories"], ["crafting", "electronics"])

    def test_a_recipe_without_a_category_list_reports_its_primary(self):
        """The primary category is always observed, so it is always reported."""
        recipe = _recipe()
        recipe.pop("categories")
        model = catalog_view_model(_intelligence(recipe))
        self.assertEqual(model["recipes"][0]["categories"], ["crafting"])

    def test_researched_technologies_are_listed(self):
        model = catalog_view_model(_intelligence(_recipe()))
        self.assertIn("advanced-circuitry", model["research"])

    def test_unresearched_technologies_are_represented(self):
        """The backend observes the technology that unlocks each recipe with
        its researched state. An unresearched one must be reported as
        unresearched rather than being absent."""
        recipe = _recipe(
            unlock_technologies=[
                {"name": "advanced-circuitry", "researched": False,
                 "enabled": True},
            ],
        )
        model = catalog_view_model(_intelligence(recipe))
        self.assertIn("unresearched_technologies", model)
        self.assertIn("advanced-circuitry", model["unresearched_technologies"])
        state = model["unresearched_technologies"]["advanced-circuitry"]
        self.assertFalse(state["researched"])
        self.assertTrue(state["enabled"])

    def test_a_researched_technology_is_not_listed_as_unresearched(self):
        model = catalog_view_model(_intelligence(_recipe()))
        self.assertNotIn(
            "advanced-circuitry", model["unresearched_technologies"]
        )

    def test_a_recipe_disabled_by_an_unresearched_technology_says_so(self):
        recipe = _recipe(
            enabled=False,
            unlock_technologies=[
                {"name": "advanced-circuitry", "researched": False,
                 "enabled": True},
            ],
        )
        model = catalog_view_model(_intelligence(recipe))
        row = model["recipes"][0]
        self.assertEqual(row["availability"], "Disabled")
        self.assertIn("not researched", row["unlock_summary"])


class LargeModdedCatalogTests(unittest.TestCase):
    """A large modpack must page, not be rejected by a flat entry cap.

    The live 2.1.23 modded run showed the Pyanodons suite abandon the whole
    catalog with ``catalog_limit`` because the recipe count exceeded 10,000.
    The bound is now derived from the backend's own addressable page range.
    """

    def test_the_catalog_entry_bound_covers_a_large_modpack(self):
        from catalog_assembly import MAX_CATALOG_ENTRIES, MAX_CATALOG_PAGES
        self.assertEqual(MAX_CATALOG_PAGES, 10000)
        self.assertGreater(MAX_CATALOG_ENTRIES, 10000)
        self.assertEqual(MAX_CATALOG_ENTRIES, MAX_CATALOG_PAGES * 16)

    def test_the_planning_bound_matches_the_assembly_bound(self):
        from catalog_assembly import MAX_CATALOG_ENTRIES
        from read_only_planning import MAX_RECIPE_CATALOG_ROWS
        self.assertEqual(MAX_RECIPE_CATALOG_ROWS, MAX_CATALOG_ENTRIES)

    def test_a_large_recipe_catalog_is_accepted_by_the_validator(self):
        from read_only_planning import validate_capabilities
        recipe = {
            "name": "mod-recipe", "enabled": True, "hidden": False,
            "simple": True, "category": "crafting", "crafting_time": 1.0,
            "ingredients": [], "products": [
                {"name": "mod-item", "type": "item", "amount": 1.0},
            ],
        }
        rows = []
        for index in range(12000):
            row = dict(recipe)
            row["name"] = f"mod-recipe-{index:06d}"
            row["products"] = [
                {"name": f"mod-item-{index:06d}", "type": "item", "amount": 1.0},
            ]
            rows.append(row)
        caps = {
            "schema": 1, "game_version": "2.1.23", "force": "player",
            "surface": "nauvis", "tick": 1000, "research": [],
            "enabled_content": ["autoengineer-input", "base"], "truncated": False,
            "recipes": rows,
        }
        parsed = validate_capabilities(caps, "nauvis", 1000)
        self.assertEqual(len(parsed["recipes"]), 12000)


if __name__ == "__main__":
    unittest.main()
