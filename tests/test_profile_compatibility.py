"""Profile boundaries before R07; no live Factorio gameplay performed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from dashboard_feed import snapshot
from read_only_planning import preview_simple_recipe, validate_capabilities, view_intelligence
from test_read_only_planning import caps, frame


class CompatibilityGates(unittest.TestCase):
    def observed(self, cap):
        return view_intelligence(
            dict(status="ok", **snapshot(dict(frame(), capabilities=cap))),
            received_at=10.0,
        )

    def test_pinned_base_preview_is_qualified_but_not_game_verified(self):
        result = self.observed(caps())
        self.assertTrue(result["planner_ready"])
        self.assertEqual(result["mechanics"]["dimension_counts"]["verified"], 0)

    def test_space_age_quality_and_elevated_rails_remain_evidence_gated(self):
        for addition in ("space-age", "quality", "elevated-rails"):
            c = caps()
            c["enabled_content"].append(addition)
            with self.subTest(addition=addition):
                result = self.observed(c)
                self.assertFalse(result["planner_ready"])
                self.assertIn("not independently qualified", result["reason"])
                with self.assertRaises(ValueError):
                    preview_simple_recipe(
                        result["capabilities"], "iron-gear-wheel",
                        machine_speed=.75, machine_power_kw=150,
                        input_rates={"iron-plate": 10},
                        power_kw=1000, target_rate=5,
                    )

    def test_future_version_and_third_party_mod_remain_unqualified(self):
        for change in ({"game_version": "2.1.22"},
                       {"enabled_content": ["base", "space-exploration"]}):
            result = self.observed(dict(caps(), **change))
            self.assertFalse(result["planner_ready"])
            self.assertIsNotNone(result["fingerprint"])

    def test_unknown_recipe_quality_temperature_or_probability_never_discarded(self):
        for k, value in (("probability", 0.5), ("quality", "legendary"),
                         ("temperature", 200)):
            c = caps()
            c["recipes"][0][k] = value
            with self.subTest(k=k), self.assertRaises(ValueError):
                validate_capabilities(c, "nauvis", 120)
        c = caps()
        c["recipes"][0]["ingredients"][0]["minimum_temperature"] = 200
        with self.assertRaises(ValueError):
            validate_capabilities(c, "nauvis", 120)

    def test_changed_surface_or_tick_cannot_replay_catalog(self):
        c = caps()
        c["tick"] = 119
        with self.assertRaises(ValueError):
            validate_capabilities(c, "nauvis", 120)
        c = caps()
        with self.assertRaises(ValueError):
            validate_capabilities(c, "vulcanus", 120)

    def test_observation_without_catalog_remains_read_only(self):
        data = view_intelligence(dict(status="ok", **snapshot(frame())), received_at=10)
        self.assertEqual(data["status"], "observed")
        self.assertFalse(data["planner_ready"])
