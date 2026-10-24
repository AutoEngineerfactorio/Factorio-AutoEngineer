"""Optional entity geometry is forwarded only when explicitly observed."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_feed import observed_entity_footprint


class EntityGeometryTests(unittest.TestCase):
    def test_missing_geometry_stays_unknown(self):
        self.assertEqual(observed_entity_footprint({"name": "assembling-machine-3"}), {})

    def test_explicit_geometry_keeps_fractional_dimensions(self):
        self.assertEqual(
            observed_entity_footprint({"width": 2.5, "height": 3, "direction": 4}),
            {"width": 2.5, "height": 3, "direction": 4},
        )

    def test_absolute_observed_bounds_preserved(self):
        bounds = {"left_top": {"x": 10.5, "y": -1}, "right_bottom": {"x": 13.5, "y": 1}}
        self.assertEqual(observed_entity_footprint({"bounds": bounds})["bounds"], bounds)

    def test_incomplete_geometry_fails(self):
        with self.assertRaises(ValueError):
            observed_entity_footprint({"width": 3})

    def test_invalid_geometry_fails_closed(self):
        for case in (
            {"width": 0, "height": 1},
            {"width": float("nan"), "height": 3},
            {"width": True, "height": 2},
            {"width": 3, "height": 1e9},
            {"direction": 16},
            {"direction": 3.4},
        ):
            with self.subTest(case=case), self.assertRaises(ValueError):
                observed_entity_footprint(case)


if __name__ == "__main__":
    unittest.main()
