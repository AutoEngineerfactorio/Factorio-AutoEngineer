import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from dashboard_feed import snapshot
from production_telemetry import (
    convert_flow_rate,
    format_power,
    power_rate_display,
    telemetry_view_model,
    validate_telemetry,
)


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

    def test_live_empty_lua_tables_are_valid_empty_arrays(self):
        sample = telemetry()
        sample["production"]["items"]["series"] = {}
        sample["production"]["fluids"]["series"] = {}
        sample["power"] = {
            "status": "unavailable", "reason": "No visible electric network",
            "unit": "joules_per_tick", "tick": 123,
            "networks": {}, "partial": False,
        }
        observed = validate_telemetry(sample, 123)
        self.assertEqual(observed["production"]["items"]["series"], [])
        self.assertEqual(observed["production"]["fluids"]["series"], [])
        self.assertEqual(observed["power"]["networks"], [])

    def test_nonempty_object_is_not_mistaken_for_empty_array(self):
        sample = telemetry()
        sample["production"]["items"]["series"] = {"unexpected": 1}
        with self.assertRaises(ValueError):
            validate_telemetry(sample, 123)
        sample = telemetry()
        sample["power"]["networks"] = {"unexpected": 1}
        with self.assertRaises(ValueError):
            validate_telemetry(sample, 123)

    def test_complete_catalog_without_false_partial(self):
        observation = telemetry()
        observation["production"] = {
            "status": "ok",
            "items": group(10000, [{"name": "iron-plate", "input": [120] * 60, "output": [180] * 60}], prototype_count=342),
            "fluids": group(10000, [], prototype_count=33),
        }
        observed = validate_telemetry(observation, 123)
        self.assertEqual(observed["production"]["status"], "ok")
        self.assertEqual(observed["production"]["items"]["candidate_bucket_count"], 1)
        self.assertEqual(len(observed["production"]["items"]["series"]), 1)
        self.assertEqual(convert_flow_rate(180, "second"), 3)
        self.assertEqual(convert_flow_rate(180, "minute"), 180)

    def test_format_power_and_energy_from_joules_per_tick(self):
        row = telemetry()["power"]["networks"][0]
        rates = power_rate_display(row)
        self.assertEqual(rates["production"], "60.00 kW")
        self.assertEqual(rates["consumption"], "54.00 kW")
        self.assertEqual(rates["energy_per_second"], "54.00 kJ")
        self.assertEqual(rates["energy_per_minute_at_current_rate"], "3.24 MJ")
        self.assertEqual(format_power(1800000), "1.80 MW")
        with self.assertRaises(ValueError):
            convert_flow_rate(-1)
        with self.assertRaises(ValueError):
            convert_flow_rate(10, "hour")

    def test_full_scan_active_history_cap_is_explicit(self):
        sample = telemetry()
        item = group(10000, [
            {"name": f"item-{k:02d}", "input": [1] * 60, "output": [2] * 60}
            for k in range(16)
        ], prototype_count=10000)
        item["partial"] = True
        sample["production"]["items"] = item
        sample["production"]["fluids"] = group(10000, [], prototype_count=20)
        self.assertEqual(validate_telemetry(sample, 123)["production"]["status"], "partial")
        item["partial"] = False
        sample["production"]["status"] = "ok"
        self.assertEqual(validate_telemetry(sample, 123)["production"]["status"], "ok")
        item["partial"] = True
        item["series"].pop()
        sample["production"]["status"] = "partial"
        with self.assertRaises(ValueError):
            validate_telemetry(sample, 123)

    def test_legacy_2077_visible_network_with_empty_flow_is_partial_not_zero(self):
        sample = telemetry()
        sample["power"] = {
            "status": "partial", "partial": True,
            "reason": "2.0 historical electricity statistics; limits unknown",
            "unit": "joules_per_tick", "tick": 123,
            "networks": [{
                "network_id": 2, "tick": 123, "source": "legacy_statistics",
                "history_available": False, "observed_input": 0.0,
                "observed_output": 0.0,
            }],
        }
        valid = validate_telemetry(sample, 123)
        model = telemetry_view_model(valid)
        self.assertEqual(model["power_status"], "partial")
        self.assertTrue(model["power_partial"])
        self.assertEqual(model["networks"][0]["network_id"], 2)
        self.assertFalse(model["networks"][0]["history_available"])
        self.assertFalse(any(
            row["title"].startswith("Check power network")
            for row in model["recommendations"]
        ))

    def test_legacy_2077_historical_power_is_not_instantaneous_satisfaction(self):
        sample = telemetry()
        sample["power"] = {
            "status": "partial", "partial": True,
            "reason": "2.0 historical electricity statistics; satisfaction unknown",
            "unit": "joules_per_tick", "tick": 123,
            "networks": [{
                "network_id": 2, "tick": 123, "source": "legacy_statistics",
                "history_available": True, "observed_input": 125.25,
                "observed_output": 201.5,
            }],
        }
        valid = validate_telemetry(sample, 123)
        self.assertAlmostEqual(valid["power"]["networks"][0]["observed_input"], 125.25)
        self.assertNotIn("consumption_satisfaction", valid["power"]["networks"][0])
        self.assertEqual(telemetry_view_model(valid)["power_status"], "partial")

    def test_legacy_2077_rejects_fabricated_capacity_and_missing_history(self):
        sample = telemetry()
        sample["power"] = {
            "status": "partial", "partial": True, "reason": "historical only",
            "unit": "joules_per_tick", "tick": 123,
            "networks": [{
                "network_id": 2, "tick": 123, "source": "legacy_statistics",
                "history_available": False, "observed_input": 0.0,
                "observed_output": 0.0,
            }],
        }
        import copy
        bad = copy.deepcopy(sample)
        bad["power"]["networks"][0]["consumption_satisfaction"] = 1.0
        with self.assertRaises(ValueError):
            validate_telemetry(bad, 123)
        bad = copy.deepcopy(sample)
        bad["power"]["networks"][0]["observed_input"] = 1.0
        with self.assertRaises(ValueError):
            validate_telemetry(bad, 123)
        bad = copy.deepcopy(sample)
        bad["power"]["reason"] = ""
        with self.assertRaises(ValueError):
            validate_telemetry(bad, 123)
        bad = copy.deepcopy(sample)
        bad["power"]["status"] = "ok"
        with self.assertRaises(ValueError):
            validate_telemetry(bad, 123)

    def test_rejects_wrong_candidate_bucket_metadata(self):
        invalid = telemetry()
        invalid["production"]["items"]["candidate_bucket"] = 3
        with self.assertRaises(ValueError):
            validate_telemetry(invalid, 123)


if __name__ == "__main__":
    unittest.main()
