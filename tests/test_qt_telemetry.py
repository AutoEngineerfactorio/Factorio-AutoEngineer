"""Regression tests for the Qt telemetry workspace model.

These tests import no Qt module: the telemetry model is pure logic, and it
must stay verifiable offline.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import qt_observation  # noqa: E402
import qt_telemetry  # noqa: E402


def _group(cap, series, prototype_count=None):
    """Return one validated flow group."""
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


def _telemetry(tick=123, satisfaction=0.9, production=1000,
               consumption=900):
    """Return one validated telemetry payload."""
    return {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": "partial",
            "reason": "Only one bounded prototype bucket is sampled",
            "items": _group(128, [{
                "name": "iron-plate",
                "input": [2.0] * 60,
                "output": [10.0] * 60,
            }], prototype_count=130),
            "fluids": _group(64, []),
        },
        "power": {
            "status": "ok",
            "unit": "joules_per_tick",
            "tick": tick,
            "networks": [{
                "network_id": 1,
                "tick": tick,
                "maximum_production": production,
                "maximum_consumption": consumption,
                "consumption_satisfaction": satisfaction,
                "production_satisfaction": 1,
                "accumulator_energy": 0,
                "accumulator_capacity": 0,
            }],
            "partial": False,
        },
    }


def _live_telemetry(tick=802, surface="nauvis"):
    """Return one **live** mod-command telemetry payload.

    This is the shape the ``/autoengineer-observe`` registered mod
    command really returns. It was captured from a live Factorio 2.1.23
    session and is kept verbatim, so the regression is proven against
    the observed document and not against an assumption.
    """
    return {
        "protocol": 1,
        "status": "ok",
        "tick": tick,
        "x": 0,
        "y": 0,
        "surface": surface,
        "production": {
            "status": "ok",
            "items": [
                {
                    "name": "burner-mining-drill",
                    "one_minute": {
                        "produced": 120.0,
                        "consumed": 0.0,
                        "per_second_produced": 24.0,
                        "per_second_consumed": None,
                    },
                    "five_seconds": {
                        "produced": 10.0,
                        "consumed": 0.0,
                        "per_second_produced": 2.0,
                        "per_second_consumed": None,
                    },
                },
            ],
            "item_names_sampled": 3,
            "item_names_truncated": False,
            "fluids": [
                {
                    "name": "ammonia",
                    "one_minute": {
                        "produced": 60.0,
                        "consumed": 30.0,
                        "per_second_produced": 12.0,
                        "per_second_consumed": 6.0,
                    },
                    "five_seconds": {
                        "produced": 5.0,
                        "consumed": 2.5,
                        "per_second_produced": 1.0,
                        "per_second_consumed": 0.5,
                    },
                },
            ],
            "fluid_status": "ok",
            "partial": True,
            "coverage": "sampled prototypes only; not a complete force-wide rate",
        },
        "power": {
            "status": "unavailable",
            "reason": "no nearby readable electric network",
            "unit": "joules_per_tick",
            "networks": {},
            "partial": False,
        },
    }


class LiveContractTelemetryTests(unittest.TestCase):
    """The live mod-command document reaches the dashboard.

    The live document travels over the **registered mod command**, which
    is the achievement-safe transport. It has its own contract, so the
    model must read it instead of rejecting it.
    """

    def test_a_live_document_is_recognised(self):
        """The live contract is told apart from the legacy one."""
        self.assertTrue(qt_telemetry.is_live_contract(_live_telemetry()))
        self.assertFalse(qt_telemetry.is_live_contract(_telemetry()))

    def test_a_live_document_is_accepted(self):
        """The live document produces an available model."""
        model = qt_telemetry.build_model(_live_telemetry())
        self.assertTrue(model.available)
        self.assertEqual(model.tick, 802)

    def test_a_live_document_reports_its_surface(self):
        """The surface the observation came from is carried."""
        model = qt_telemetry.build_model(_live_telemetry())
        self.assertEqual(model.surface, "nauvis")

    def test_a_live_document_yields_the_observed_flows(self):
        """The observed materials and fluids become flow rows."""
        model = qt_telemetry.build_model(_live_telemetry())
        names = {row.name for row in model.flows}
        self.assertIn("burner-mining-drill", names)
        self.assertIn("ammonia", names)
        rows = {row.name: row for row in model.flows}
        drill = rows["burner-mining-drill"]
        self.assertEqual(drill.output_per_minute, 120.0)
        self.assertEqual(drill.input_per_minute, 0.0)
        self.assertEqual(drill.kind, "item")
        ammonia = rows["ammonia"]
        self.assertEqual(ammonia.output_per_minute, 60.0)
        self.assertEqual(ammonia.input_per_minute, 30.0)
        self.assertEqual(ammonia.kind, "fluid")

    def test_a_live_document_reports_partial_coverage(self):
        """A sampled document is reported as partial, never as complete."""
        model = qt_telemetry.build_model(_live_telemetry())
        self.assertTrue(model.partial)
        self.assertTrue(all(row.partial for row in model.flows))

    def test_a_live_document_reports_an_unavailable_power(self):
        """The reason the power was not observed is carried."""
        model = qt_telemetry.build_model(_live_telemetry())
        self.assertEqual(model.power_status, "unavailable")
        self.assertEqual(model.networks, [])
        self.assertIn("no nearby readable electric network", model.reason)

    def test_real_live_electrical_network_reaches_history(self):
        from qt_telemetry_history import POWER_GENERATION, TelemetryHistory

        payload = _live_telemetry()
        payload["power"] = {
            "status": "ok", "unit": "joules_per_tick", "tick": 802,
            "networks": [{
                "network_id": 17, "tick": 802,
                "maximum_production": 1200.0,
                "maximum_consumption": 1100.0,
                "consumption_satisfaction": 0.9,
                "production_satisfaction": 1.0,
                "accumulator_energy": 0.0,
                "accumulator_capacity": 0.0,
            }], "partial": False,
        }
        model = qt_telemetry.build_model(payload)
        self.assertEqual(model.power_status, "ok")
        self.assertEqual(len(model.networks), 1)
        self.assertEqual(model.networks[0].network_id, 17)
        self.assertEqual(model.networks[0].generation_watts, 72000.0)
        history = TelemetryHistory()
        history.observe(payload, at=100.0)
        self.assertEqual(history.chart(f"{POWER_GENERATION}:network-17").values,
                         [72000.0])

    def test_invalid_live_power_never_becomes_observed_zero_watts(self):
        for mutation in ("wrong_tick", "negative", "nonnumeric", "bad_satisfaction"):
            payload = _live_telemetry()
            payload["power"] = {
                "status": "ok", "unit": "joules_per_tick", "tick": 802,
                "networks": [{
                    "network_id": 1, "tick": 802,
                    "maximum_production": 1000.0,
                    "maximum_consumption": 900.0,
                    "consumption_satisfaction": 0.9,
                    "production_satisfaction": 1.0,
                    "accumulator_energy": 0.0,
                    "accumulator_capacity": 0.0,
                }], "partial": False,
            }
            if mutation == "wrong_tick":
                payload["power"]["tick"] = 800
            elif mutation == "negative":
                payload["power"]["networks"][0]["maximum_production"] = -1
            elif mutation == "nonnumeric":
                payload["power"]["networks"][0]["maximum_production"] = None
            else:
                payload["power"]["networks"][0]["consumption_satisfaction"] = 1.2
            with self.subTest(mutation=mutation):
                model = qt_telemetry.build_model(payload)
                self.assertEqual(model.power_status, "unavailable")
                self.assertEqual(model.networks, [])
                self.assertTrue(model.reason)

    def test_missing_live_rate_is_not_fabricated_zero(self):
        payload = _live_telemetry()
        payload["production"]["items"][0]["one_minute"]["produced"] = None
        model = qt_telemetry.build_model(payload)
        self.assertNotIn("burner-mining-drill", {row.name for row in model.flows})
        self.assertIn("ammonia", {row.name for row in model.flows})

    def test_live_version_and_tick_are_checked(self):
        for mutation in ("version", "frame_tick", "nonfinite_tick"):
            payload = _live_telemetry()
            if mutation == "version":
                payload["protocol"] = 2
            if mutation == "nonfinite_tick":
                payload["tick"] = True
            model = qt_telemetry.build_model(payload, tick=803 if mutation == "frame_tick" else None)
            with self.subTest(mutation=mutation):
                self.assertFalse(model.available)
                self.assertEqual(model.flows, [])

    def test_an_unavailable_live_document_is_not_ok(self):
        """A document the game marked unavailable stays unavailable."""
        payload = _live_telemetry()
        payload["status"] = "unavailable"
        payload["reason"] = "no_connected_player_with_character"
        payload["production"] = {"status": "unavailable",
                                 "reason": "no player"}
        model = qt_telemetry.build_model(payload)
        self.assertFalse(model.available)
        self.assertEqual(model.flows, [])
        self.assertIn("no_connected_player_with_character", model.reason)

    def test_the_legacy_contract_still_works(self):
        """The legacy envelope is still accepted."""
        model = qt_telemetry.build_model(_telemetry())
        self.assertTrue(model.available)
        self.assertEqual(len(model.flows), 1)

    def test_a_live_document_reaches_the_history(self):
        """The live document is recorded by the bounded history."""
        from qt_telemetry_history import FLOW_OUTPUT, TelemetryHistory

        history = TelemetryHistory()
        history.observe(_live_telemetry(), at=100.0)
        chart = history.chart(f"{FLOW_OUTPUT}:burner-mining-drill")
        self.assertEqual(chart.values, [120.0])


class UnavailableTelemetryTests(unittest.TestCase):
    """A missing or invalid payload is unknown, never zero."""

    def test_no_payload_is_unavailable(self):
        model = qt_telemetry.build_model(None)
        self.assertFalse(model.available)
        self.assertEqual(model.flows, [])
        self.assertEqual(model.networks, [])

    def test_an_invalid_payload_is_rejected_with_a_reason(self):
        model = qt_telemetry.build_model({"schema": 9})
        self.assertFalse(model.available)
        self.assertTrue(model.reason)

    def test_a_payload_with_a_wrong_schema_is_rejected(self):
        payload = _telemetry()
        payload["schema"] = 9
        model = qt_telemetry.build_model(payload)
        self.assertFalse(model.available)
        self.assertIn("rejected", model.reason)

    def test_a_payload_for_another_tick_is_rejected(self):
        model = qt_telemetry.build_model(_telemetry(tick=123), tick=999)
        self.assertFalse(model.available)
        self.assertIn("tick", model.reason)

    def test_an_unavailable_model_has_no_zero_rates(self):
        model = qt_telemetry.build_model(None)
        self.assertEqual(model.total_input_per_minute(), 0.0)
        self.assertIsNone(model.worst_satisfaction())


class FlowRowTests(unittest.TestCase):
    """The observed and the derived rates stay apart."""

    def test_the_observed_minute_rates_are_kept(self):
        model = qt_telemetry.build_model(_telemetry())
        self.assertEqual(len(model.flows), 1)
        row = model.flows[0]
        self.assertEqual(row.name, "iron-plate")
        self.assertEqual(row.kind, "item")
        self.assertAlmostEqual(row.input_per_minute, 2.0)
        self.assertAlmostEqual(row.output_per_minute, 10.0)

    def test_the_per_second_rate_is_derived_from_the_minute_rate(self):
        model = qt_telemetry.build_model(_telemetry())
        row = model.flows[0]
        self.assertAlmostEqual(row.output_per_second, 10.0 / 60.0)

    def test_the_per_second_rate_is_an_estimate(self):
        model = qt_telemetry.build_model(_telemetry())
        observation = qt_telemetry.flow_rate_observation(model.flows[0])
        self.assertTrue(observation.estimated)
        self.assertIn("derived", observation.detail)

    def test_the_net_rate_is_the_observed_difference(self):
        model = qt_telemetry.build_model(_telemetry())
        self.assertAlmostEqual(model.flows[0].net_per_minute, 8.0)

    def test_an_imbalanced_flow_is_reported(self):
        model = qt_telemetry.build_model(_telemetry())
        self.assertTrue(model.flows[0].imbalanced)

    def test_a_balanced_flow_is_not_reported(self):
        model = qt_telemetry.build_model(_telemetry())
        row = model.flows[0]
        self.assertFalse(
            type(row)(name=row.name, kind=row.kind,
                      input_per_minute=10.0, output_per_minute=10.0,
                      input_per_second=1.0, output_per_second=1.0).imbalanced)

    def test_the_totals_are_the_sum_of_the_rows(self):
        model = qt_telemetry.build_model(_telemetry())
        self.assertAlmostEqual(model.total_output_per_minute(), 10.0)
        self.assertAlmostEqual(model.total_input_per_minute(), 2.0)


class PowerRowTests(unittest.TestCase):
    """The electrical networks keep the game's own units."""

    def test_the_network_is_read_from_the_observation(self):
        model = qt_telemetry.build_model(_telemetry())
        self.assertEqual(len(model.networks), 1)
        self.assertEqual(model.networks[0].network_id, 1)

    def test_the_watts_are_converted_from_joules_per_tick(self):
        model = qt_telemetry.build_model(_telemetry())
        network = model.networks[0]
        self.assertAlmostEqual(network.generation_watts, 1000 * 60.0)
        self.assertAlmostEqual(network.consumption_watts, 900 * 60.0)

    def test_an_unsatisfied_network_is_reported(self):
        model = qt_telemetry.build_model(_telemetry(satisfaction=0.9))
        self.assertFalse(model.networks[0].satisfied)

    def test_a_satisfied_network_is_reported(self):
        model = qt_telemetry.build_model(_telemetry(satisfaction=1.0))
        self.assertTrue(model.networks[0].satisfied)

    def test_the_worst_satisfaction_is_the_lowest(self):
        model = qt_telemetry.build_model(_telemetry(satisfaction=0.9))
        worst = model.worst_satisfaction()
        assert worst is not None
        self.assertAlmostEqual(worst, 0.9)

    def test_the_network_display_names_every_value(self):
        model = qt_telemetry.build_model(_telemetry())
        display = qt_telemetry.network_display(model.networks[0])
        for key in ("network", "generation", "consumption",
                    "energy_per_second", "satisfaction", "headroom"):
            self.assertIn(key, display)
            self.assertTrue(display[key])

    def test_the_power_observation_is_observed_not_estimated(self):
        model = qt_telemetry.build_model(_telemetry())
        observation = qt_telemetry.power_observation(model.networks[0])
        self.assertEqual(observation.state, qt_observation.OBSERVED)


class BottleneckTests(unittest.TestCase):
    """A bottleneck is a candidate, never a verdict."""

    def test_the_recommendations_are_present(self):
        model = qt_telemetry.build_model(_telemetry())
        self.assertTrue(model.recommendations)

    def test_the_most_severe_candidate_comes_first(self):
        model = qt_telemetry.build_model(_telemetry())
        rows = model.bottleneck_rows()
        severities = [row.get("severity") for row in rows]
        if "high" in severities:
            self.assertEqual(severities[0], "high")

    def test_every_candidate_names_a_severity(self):
        model = qt_telemetry.build_model(_telemetry())
        for row in model.bottleneck_rows():
            self.assertIn(row.get("severity"), qt_telemetry.SEVERITIES)

    def test_a_candidate_is_named_as_a_candidate(self):
        model = qt_telemetry.build_model(_telemetry())
        for row in model.bottleneck_rows():
            self.assertIn("title", row)
            self.assertIn("detail", row)


class FreshnessTests(unittest.TestCase):
    """The freshness of the telemetry is stated, not assumed."""

    def test_a_fresh_observation_is_observed(self):
        model = qt_telemetry.build_model(_telemetry())
        observation = model.freshness(2.0)
        self.assertTrue(observation.known)
        self.assertEqual(observation.state, qt_observation.OBSERVED)

    def test_a_stale_observation_is_unavailable(self):
        model = qt_telemetry.build_model(_telemetry())
        observation = model.freshness(120.0)
        self.assertFalse(observation.known)

    def test_an_unavailable_model_has_no_freshness(self):
        model = qt_telemetry.build_model(None)
        self.assertFalse(model.freshness(1.0).known)

    def test_a_negative_age_is_rejected(self):
        model = qt_telemetry.build_model(_telemetry())
        self.assertFalse(model.freshness(-5.0).known)


class ModulePurityTests(unittest.TestCase):
    """The telemetry model must stay testable without a display server."""

    def test_the_telemetry_module_does_not_import_qt(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_telemetry.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("PySide6", source)
        self.assertNotIn("QtWidgets", source)

    def test_the_telemetry_module_holds_no_transport(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_telemetry.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("rcon", "call_tool", "send_command"):
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()


class DeliveredPowerTests(unittest.TestCase):
    def test_available_capacity_is_distinct_from_actual_delivery(self):
        row = qt_telemetry.PowerRow(1, 1000, 800, .5, .4, 0, 0)
        self.assertEqual(row.delivered_generation_watts, 400)
        self.assertEqual(row.delivered_consumption_watts, 400)
        self.assertEqual(row.headroom_watts, 200)
