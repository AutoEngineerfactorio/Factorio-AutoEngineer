"""Offline regression and adversarial checks for replayable Factorio flow telemetry."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from factory_reality_test import (
    TraceError,
    evaluate_trace,
    load_trace,
    make_demo_trace,
)


def sample(tick, output, *, consumed=None, power: float | None = 1.0):
    return {"tick": tick, "produced": output, "consumed": consumed or [],
            "power_satisfaction": power}


def flow(name, total, *, kind="item", quality=None):
    value = {"kind": kind, "name": name, "total": total}
    if quality is not None:
        value["quality"] = quality
    return value


def short_trace(targets, samples, *, evidence="external_capture_unverified"):
    return {
        "schema": 1, "evidence": evidence,
        "profile": {"game_version": "2.1.23", "force": "player", "surface": "nauvis",
                    "content": ["base"], "tick_rate": 60},
        "targets": targets, "samples": samples,
    }


class RealisticReplay(unittest.TestCase):
    def test_ten_minute_demo_reports_recovered_and_shortfall_windows(self):
        report = evaluate_trace(make_demo_trace())
        self.assertFalse(report["live_game_verified"])
        self.assertEqual(report["evidence"], "synthetic_fixture")
        self.assertEqual(report["sample_count"], 601)
        gear = next(p for p in report["products"] if p["name"] == "iron-gear-wheel")
        self.assertAlmostEqual(gear["windows_minutes"]["1"]["observed_rate"], 300)
        self.assertAlmostEqual(gear["windows_minutes"]["5"]["observed_rate"], 228)
        self.assertAlmostEqual(gear["windows_minutes"]["10"]["observed_rate"], 264)
        self.assertEqual(gear["windows_minutes"]["1"]["status"], "WITHIN_TARGET")
        self.assertEqual(gear["windows_minutes"]["5"]["status"], "BELOW_TARGET")
        self.assertEqual(report["minimum_power_satisfaction"], 0.55)

    def test_fluid_output_is_measured_independently(self):
        report = evaluate_trace(make_demo_trace())
        water = next(p for p in report["products"] if p["name"] == "water")
        self.assertEqual(water["kind"], "fluid")
        for minutes in ("1", "5", "10"):
            self.assertEqual(water["windows_minutes"][minutes]["observed_rate"], 1200)
            self.assertEqual(water["windows_minutes"][minutes]["status"], "WITHIN_TARGET")

    def test_any_item_and_quality_with_only_one_minute_capture(self):
        trace = short_trace(
            [{"kind": "item", "name": "processing-unit", "quality": "rare",
              "target_per_minute": 60}],
            [sample(0, [flow("processing-unit", 0, quality="rare")]),
             sample(3600, [flow("processing-unit", 65, quality="rare")])],
        )
        result = evaluate_trace(trace, tolerance=0.10)
        p = result["products"][0]
        self.assertEqual(p["quality"], "rare")
        self.assertEqual(p["windows_minutes"]["1"]["status"], "WITHIN_TARGET")
        self.assertEqual(p["windows_minutes"]["5"]["status"], "NOT_MEASURED")
        self.assertEqual(p["windows_minutes"]["10"]["status"], "NOT_MEASURED")
        self.assertFalse(result["live_game_verified"])

    def test_above_target_is_distinguished_from_shortfall(self):
        trace = short_trace(
            [{"kind": "item", "name": "some-future-mod-item", "target_per_minute": 10}],
            [sample(0, [flow("some-future-mod-item", 0)]),
             sample(3600, [flow("some-future-mod-item", 12)])],
        )
        self.assertEqual(
            evaluate_trace(trace)["products"][0]["windows_minutes"]["1"]["status"],
            "ABOVE_TARGET",
        )

    def test_missing_exact_window_does_not_guess(self):
        trace = short_trace(
            [{"kind": "fluid", "name": "steam", "target_per_minute": 600}],
            [sample(0, [flow("steam", 0, kind="fluid")]),
             sample(3540, [flow("steam", 600, kind="fluid")]),
             sample(7200, [flow("steam", 1200, kind="fluid")])],
        )
        result = evaluate_trace(trace)
        self.assertEqual(result["products"][0]["windows_minutes"]["1"]["status"], "NOT_MEASURED")

    def test_consumption_is_not_mistaken_for_production(self):
        trace = short_trace(
            [{"kind": "item", "name": "iron-plate", "target_per_minute": 100}],
            [sample(0, [flow("iron-plate", 0)], consumed=[flow("iron-plate", 0)]),
             sample(3600, [flow("iron-plate", 0)], consumed=[flow("iron-plate", 10000)])],
        )
        report = evaluate_trace(trace)
        self.assertEqual(report["products"][0]["windows_minutes"]["1"]["observed_rate"], 0)
        self.assertEqual(report["products"][0]["windows_minutes"]["1"]["status"], "BELOW_TARGET")

    def test_prediction_deviation_and_net_consumption_are_distinct(self):
        trace = short_trace(
            [{"kind": "item", "name": "steel-plate", "target_per_minute": 100,
              "predicted_per_minute": 80}],
            [sample(0, [flow("steel-plate", 0)], consumed=[flow("steel-plate", 10)]),
             sample(3600, [flow("steel-plate", 60)], consumed=[flow("steel-plate", 25)])],
        )
        window = evaluate_trace(trace)["products"][0]["windows_minutes"]["1"]
        self.assertEqual(window["status"], "BELOW_TARGET")
        self.assertEqual(window["predicted_rate"], 80)
        self.assertEqual(window["prediction_error_percent"], -25)
        self.assertEqual(window["produced"], 60)
        self.assertEqual(window["consumed"], 15)

    def test_no_consumption_data_is_unknown_not_zero(self):
        trace = short_trace(
            [{"kind": "fluid", "name": "steam", "target_per_minute": 20}],
            [sample(0, [flow("steam", 0, kind="fluid")]),
             sample(3600, [flow("steam", 20, kind="fluid")])],
        )
        window = evaluate_trace(trace)["products"][0]["windows_minutes"]["1"]
        self.assertIsNone(window["consumed"])
        self.assertIsNone(window["prediction_error_percent"])

    def test_invalid_prediction_not_silently_accepted(self):
        trace = make_demo_trace()
        trace["targets"][0]["predicted_per_minute"] = float("inf")
        with self.assertRaises(TraceError):
            evaluate_trace(trace)

    def test_counter_reset_fails_closed(self):
        trace = short_trace(
            [{"kind": "item", "name": "steel-plate", "target_per_minute": 60}],
            [sample(0, [flow("steel-plate", 200)]),
             sample(3600, [flow("steel-plate", 100)])],
        )
        with self.assertRaisesRegex(TraceError, "decreased"):
            evaluate_trace(trace)

    def test_invalid_schema_cannot_substitute_inventory_for_flow(self):
        trace = make_demo_trace()
        trace["samples"][0]["inventory"] = {"iron-gear-wheel": 9999999}
        with self.assertRaises(TraceError):
            evaluate_trace(trace)

    def test_missing_product_fails_closed(self):
        trace = make_demo_trace()
        trace["samples"][1]["produced"].pop()
        with self.assertRaisesRegex(TraceError, "missing"):
            evaluate_trace(trace)

    def test_duplicate_product_fails_closed(self):
        trace = make_demo_trace()
        trace["samples"][1]["produced"].append(
            copy.deepcopy(trace["samples"][1]["produced"][0])
        )
        with self.assertRaisesRegex(TraceError, "Duplicate"):
            evaluate_trace(trace)

    def test_missing_power_measurement_is_unknown(self):
        trace = short_trace(
            [{"kind": "item", "name": "iron-plate", "target_per_minute": 60}],
            [sample(0, [flow("iron-plate", 0)], power=None),
             sample(3600, [flow("iron-plate", 60)], power=None)],
        )
        result = evaluate_trace(trace)
        self.assertIsNone(result["minimum_power_satisfaction"])
        self.assertEqual(result["products"][0]["windows_minutes"]["1"]["status"],
                         "WITHIN_TARGET")

    def test_invalid_tick_and_power_fail_closed(self):
        for mutation in ("repeat_tick", "bad_power", "future_version"):
            with self.subTest(mutation=mutation):
                trace = make_demo_trace()
                if mutation == "repeat_tick":
                    trace["samples"][1]["tick"] = 0
                elif mutation == "bad_power":
                    trace["samples"][2]["power_satisfaction"] = 1.5
                else:
                    trace["profile"]["tick_rate"] = 120
                with self.assertRaises(TraceError):
                    evaluate_trace(trace)

    def test_cannot_claim_verified_live_via_json(self):
        trace = make_demo_trace()
        trace["evidence"] = "live_verified"
        with self.assertRaises(TraceError):
            evaluate_trace(trace)

    def test_invalid_fluid_quality_rejected(self):
        trace = short_trace(
            [{"kind": "fluid", "name": "water", "quality": "epic",
              "target_per_minute": 200}],
            [sample(0, [flow("water", 0, kind="fluid", quality="epic")]),
             sample(3600, [flow("water", 200, kind="fluid", quality="epic")])],
        )
        with self.assertRaises(TraceError):
            evaluate_trace(trace)

    def test_large_dynamic_product_catalog(self):
        targets = [{"kind": "item", "name": f"product-{i}",
                    "target_per_minute": 100} for i in range(128)]
        start = [flow(f"product-{i}", 0) for i in range(128)]
        end = [flow(f"product-{i}", 100) for i in range(128)]
        trace = short_trace(targets, [sample(0, start), sample(3600, end)])
        report = evaluate_trace(trace)
        self.assertEqual(len(report["products"]), 128)
        self.assertTrue(all(p["windows_minutes"]["1"]["status"] == "WITHIN_TARGET"
                            for p in report["products"]))

    def test_trace_loader_rejects_oversized_files(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.json"
            path.write_bytes(b"x" * 5_000_001)
            with self.assertRaises(TraceError):
                load_trace(path)

    def test_good_external_json_is_unverified_not_game_proof(self):
        trace = short_trace(
            [{"kind": "item", "name": "copper-cable", "target_per_minute": 120}],
            [sample(0, [flow("copper-cable", 0)]),
             sample(3600, [flow("copper-cable", 120)])],
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.json"
            path.write_text(json.dumps(trace), encoding="utf-8")
            report = evaluate_trace(load_trace(path))
        self.assertEqual(report["validation"], "offline_counter_replay_only")
        self.assertFalse(report["live_game_verified"])


if __name__ == "__main__":
    unittest.main()
