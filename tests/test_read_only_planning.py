"""Read-only R04-R06 integration and legacy gameplay-entry safety regressions."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from dashboard_feed import PREFIX, parse_frame, snapshot
from read_only_planning import (
    preview_simple_recipe,
    validate_capabilities,
    view_intelligence,
)
from safe_executor import main as legacy_executor_main


def frame():
    return {
        "status": "ok", "x": 0.0, "y": 2.0, "position": {"x": 0, "y": 2},
        "tick": 120, "surface": "nauvis", "inventory": [
            {"name": "iron-plate", "quality": "normal", "count": 30},
        ], "inventory_available": True, "truncated": False,
    }


def caps():
    return {
        "schema": 1, "tick": 120, "surface": "nauvis", "game_version": "2.0.77",
        "force": "player", "research": ["automation"], "enabled_content": ["base"],
        "truncated": False,
        "recipes": [
            {"name": "iron-gear-wheel", "enabled": True, "simple": True,
             "crafting_time": 0.5,
             "ingredients": [{"type": "item", "name": "iron-plate", "amount": 2}],
             "products": [{"type": "item", "name": "iron-gear-wheel", "amount": 1}]},
        ],
    }


class ReadOnlyObservations(unittest.TestCase):
    def test_current_backend_is_observed_but_not_recipe_ready(self):
        result = view_intelligence(dict(status='ok', **snapshot(frame())), received_at=100)
        self.assertEqual(result["status"], "observed")
        self.assertFalse(result["planner_ready"])
        self.assertIsNone(result["capabilities"])
        self.assertEqual(result["mechanics"]["dimension_counts"]["verified"], 0)
        self.assertEqual(result["mechanics"]["dimension_counts"]["observed"], 2)
        self.assertEqual(result["mechanics"]["dimension_counts"]["action_permitted"], 0)

    def test_missing_and_partial_inventory_never_claims_verified(self):
        raw = frame()
        raw["inventory_available"] = False
        observed = view_intelligence(dict(status='ok', **snapshot(raw)), received_at=100)
        self.assertEqual(observed["mechanics"]["dimension_counts"]["observed"], 1)
        raw["inventory_available"] = True
        raw["truncated"] = True
        observed = view_intelligence(dict(status='ok', **snapshot(raw)), received_at=100)
        self.assertFalse(observed["planner_ready"])
        self.assertEqual(observed["mechanics"]["dimension_counts"]["verified"], 0)

    def test_unavailable_frame_disables_planning(self):
        result = view_intelligence({"status": "unavailable"})
        self.assertFalse(result["planner_ready"])

    def test_same_tick_catalog_can_roundtrip_through_child_frame(self):
        raw = frame()
        raw["capabilities"] = caps()
        wire = dict(schema=1, status="ok", **snapshot(raw), visited=[], failed=[],
                    resources=[], objective=None, proposal=None)
        parsed = parse_frame(PREFIX + json.dumps(wire))
        result = view_intelligence(parsed, received_at=100)
        self.assertTrue(result["planner_ready"])
        self.assertEqual(result["capabilities"]["recipes"][0]["name"], "iron-gear-wheel")
        self.assertEqual(result["mechanics"]["dimension_counts"]["verified"], 0)
        self.assertEqual(result["mechanics"]["dimension_counts"]["action_permitted"], 0)
        self.assertEqual(result["status"], "live")

    def test_modified_mods_recipes_or_research_change_fingerprint(self):
        a = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=caps()))), received_at=100)
        changed = caps()
        changed["enabled_content"] = ["base", "quality"]
        b = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=changed))), received_at=100)
        self.assertNotEqual(a["fingerprint"], b["fingerprint"])
        changed = caps()
        changed["recipes"][0]["ingredients"][0]["amount"] = 3
        c = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=changed))), received_at=100)
        self.assertNotEqual(a["fingerprint"], c["fingerprint"])

    def test_wrong_surface_tick_truncated_and_bad_metadata_fail_closed(self):
        cases = [
            {"tick": 119},
            {"surface": "vulcanus"},
            {"truncated": "false"},
            {"game_version": "1.1.10"},
            {"recipes": [{"name": "gear"}]},
        ]
        for update in cases:
            p = dict(caps(), **update)
            with self.subTest(update=str(update)), self.assertRaises(ValueError):
                snapshot(dict(frame(), capabilities=p))
        p = caps()
        p["truncated"] = True
        self.assertFalse(view_intelligence(
            snapshot(dict(frame(), capabilities=p)), received_at=100)["planner_ready"])

    def test_recipe_pagination_empty_or_missing_is_not_ready(self):
        p = caps()
        p["recipes"] = []
        result = view_intelligence(dict(status='ok', **snapshot(dict(frame(), capabilities=p))), received_at=100)
        self.assertFalse(result["planner_ready"])
        with self.assertRaises(ValueError):
            validate_capabilities(dict(caps(), recipes=[caps()["recipes"][0]] * 129), "nauvis", 120)

    def test_physical_preview_requires_explicit_observed_rates(self):
        data = validate_capabilities(caps(), "nauvis", 120)
        plan = preview_simple_recipe(
            data, "iron-gear-wheel", machine_speed=1, machine_power_kw=100,
            input_rates={"iron-plate": 1}, power_kw=1000, target_rate=5,
        )
        self.assertAlmostEqual(plan.achievable_rate_gps, 0.5)
        self.assertEqual(plan.feasibility_status, "partial")
        self.assertIn("supply-iron-plate", plan.supply_limiting)

    def test_fluid_or_complex_recipe_is_explicitly_unsupported(self):
        p = caps()
        p["enabled_content"] = ["base", "space-age", "quality", "elevated-rails"]
        p["recipes"][0]["simple"] = False
        c = validate_capabilities(p, "nauvis", 120)
        with self.assertRaises(ValueError):
            preview_simple_recipe(
                c, "iron-gear-wheel", machine_speed=1, machine_power_kw=100,
                input_rates={"iron-plate": 100}, power_kw=1000, target_rate=5)


class LegacyExecutorSafety(unittest.IsolatedAsyncioTestCase):
    async def test_execute_fails_before_any_mcp_or_gameplay_call(self):
        with patch("safe_executor.mcp_parameters") as parameters:
            with self.assertRaisesRegex(PermissionError, "Legacy --execute disabled"):
                await legacy_executor_main(True)
            parameters.assert_not_called()
