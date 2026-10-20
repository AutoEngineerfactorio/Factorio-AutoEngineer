import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from dashboard_feed import snapshot
from production_telemetry import telemetry_view_model, validate_telemetry


def group(cap, series, prototype_count=None):
    count = cap if prototype_count is None else prototype_count
    return {
        "status": "ok",
        "unit": "units_per_minute",
        "precision": "ten_minutes",
        "sample_interval_seconds": 2,
        "sample_count": 60,
        "window_seconds": 120,
        "prototype_count": count,
        "candidate_cap": cap,
        "candidate_bucket": 1,
        "candidate_bucket_count": max(1, (count + cap - 1) // cap),
        "partial": count > cap,
        "series": series,
    }


def telemetry(tick=123):
    return {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": "partial",
            "reason": "Only one bounded prototype bucket is sampled",
            "items": group(128, [{
                "name": "iron-plate",
                "input": [10.0] * 60,
                "output": [2.0] * 60,
            }], prototype_count=130),
            "fluids": group(64, []),
        },
        "power": {
            "status": "ok",
            "unit": "joules_per_tick",
            "tick": tick,
            "networks": [{
                "network_id": 1,
                "tick": tick,
                "maximum_production": 1000,
                "maximum_consumption": 900,
                "consumption_satisfaction": 0.9,
                "production_satisfaction": 1,
                "accumulator_energy": 0,
                "accumulator_capacity": 0,
            }],
            "partial": False,
        },
    }


class ProductionTelemetryTests(unittest.TestCase):
    def test_validates_partial_sampled_flows_and_power(self):
        validated = validate_telemetry(telemetry(), 123)
        model = telemetry_view_model(validated)
        self.assertEqual(validated["production"]["status"], "partial")
        self.assertEqual(model["items"][0]["name"], "iron-plate")
        self.assertEqual(model["networks"][0]["consumption_satisfaction"], 0.9)
        self.assertFalse(model["power_partial"])
        self.assertTrue(any("iron-plate" in row["title"] for row in model["recommendations"]))
        self.assertTrue(any("network 1" in row["title"] for row in model["recommendations"]))

    def test_older_backend_is_explicitly_unavailable_and_dashboard_safe(self):
        normalized = validate_telemetry(None, 123)
        model = telemetry_view_model(normalized)
        self.assertEqual(model["production_status"], "unavailable")
        self.assertEqual(model["power_status"], "unavailable")
        self.assertEqual(model["networks"], [])

        frame = snapshot({
            "status": "ok", "x": 0, "y": 0, "tick": 123, "surface": "nauvis",
            "inventory": [], "inventory_available": True, "truncated": False,
        })
        self.assertEqual(frame["telemetry"], normalized)

    def test_rejects_stale_tick_malformed_samples_and_unbounded_values(self):
        invalid = telemetry()
        invalid["tick"] = 122
        with self.assertRaises(ValueError):
            validate_telemetry(invalid, 123)

        invalid = telemetry()
        invalid["production"]["items"]["series"][0]["input"].pop()
        with self.assertRaises(ValueError):
            validate_telemetry(invalid, 123)

        invalid = telemetry()
        invalid["production"]["items"]["series"][0]["output"][0] = 10**100
        with self.assertRaises(ValueError):
            validate_telemetry(invalid, 123)

        invalid = telemetry()
        invalid["power"]["networks"][0]["consumption_satisfaction"] = float("nan")
        with self.assertRaises(ValueError):
            validate_telemetry(invalid, 123)

    def test_recommendations_require_measured_imbalance_or_low_power_satisfaction(self):
        data = telemetry()
        data["production"]["items"]["series"][0]["input"] = [4.0] * 60
        data["production"]["items"]["series"][0]["output"] = [4.0] * 60
        data["power"]["networks"][0]["consumption_satisfaction"] = 1.0
        model = telemetry_view_model(validate_telemetry(data, 123))
        self.assertEqual(len(model["recommendations"]), 1)
        self.assertEqual(model["recommendations"][0]["severity"], "info")
        self.assertIn("not considered healthy", model["recommendations"][0]["detail"])

    def test_rejects_wrong_candidate_bucket_metadata(self):
        invalid = telemetry()
        invalid["production"]["items"]["candidate_bucket"] = 3
        with self.assertRaises(ValueError):
            validate_telemetry(invalid, 123)


if __name__ == "__main__":
    unittest.main()
