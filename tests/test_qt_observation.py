"""Regression tests for the Qt observation state model.

These tests import no Qt module and need no display server: the
truthfulness rules are pure logic, and they must stay verifiable when the
graphical dashboard cannot run.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import qt_observation  # noqa: E402


class ObservationStateTests(unittest.TestCase):
    """The observed / estimated / unavailable separation."""

    def test_unavailable_is_not_zero(self):
        observation = qt_observation.unavailable("Not observed")
        self.assertFalse(observation.known)
        self.assertIsNone(observation.value)
        self.assertEqual(observation.display(), "—")

    def test_observed_value_displays(self):
        observation = qt_observation.observed(12.5, "Observed snapshot")
        self.assertTrue(observation.known)
        self.assertTrue(observation.fresh)
        self.assertEqual(observation.display(), "12.50")
        self.assertEqual(observation.badge(), "observed")

    def test_estimated_requires_a_named_derivation(self):
        with self.assertRaises(ValueError):
            qt_observation.estimated(1.0, "")
        observation = qt_observation.estimated(
            2.0, "Per-second rate derived from a per-minute flow sample")
        self.assertTrue(observation.estimated)
        self.assertTrue(observation.known)
        self.assertEqual(observation.badge(), "estimated")

    def test_stale_keeps_the_last_value_but_is_not_fresh(self):
        first = qt_observation.observed(42.0, "Observed snapshot")
        aged = qt_observation.stale(first, 90.0)
        self.assertTrue(aged.known)
        self.assertFalse(aged.fresh)
        self.assertEqual(aged.value, 42.0)
        self.assertEqual(aged.badge(), "stale")
        self.assertIn("90", aged.detail)

    def test_stale_of_an_unknown_stays_unknown(self):
        aged = qt_observation.stale(qt_observation.unavailable("Not observed"), 30.0)
        self.assertFalse(aged.known)
        self.assertIsNone(aged.value)

    def test_non_finite_float_renders_as_unknown(self):
        observation = qt_observation.observed(float("nan"), "Observed")
        self.assertEqual(observation.display(), "—")

    def test_is_known_matches_the_state_set(self):
        self.assertTrue(qt_observation.is_known(qt_observation.OBSERVED))
        self.assertTrue(qt_observation.is_known(qt_observation.ESTIMATED))
        self.assertTrue(qt_observation.is_known(qt_observation.STALE))
        self.assertFalse(qt_observation.is_known(qt_observation.UNAVAILABLE))

    def test_a_custom_formatter_is_used(self):
        observation = qt_observation.observed(1234.0, "Observed")
        self.assertEqual(
            observation.display(formatter=lambda v: f"{v / 1000:.1f}k"), "1.2k")

    def test_the_formatter_is_not_called_for_an_unknown_value(self):
        calls = []

        def formatter(value):
            calls.append(value)
            return "x"

        observation = qt_observation.unavailable("Not observed")
        self.assertEqual(observation.display(formatter=formatter), "—")
        self.assertEqual(calls, [])


class OptionalFieldTests(unittest.TestCase):
    """Absent fields mean unknown, never zero."""

    def test_absent_number_is_none(self):
        self.assertIsNone(qt_observation.optional_number({}, "ups"))
        self.assertIsNone(qt_observation.optional_number(None, "ups"))

    def test_boolean_is_not_a_number(self):
        self.assertIsNone(qt_observation.optional_number({"ups": True}, "ups"))

    def test_non_finite_number_is_rejected(self):
        self.assertIsNone(
            qt_observation.optional_number({"ups": float("inf")}, "ups"))
        self.assertIsNone(
            qt_observation.optional_number({"ups": float("nan")}, "ups"))

    def test_number_is_returned_as_float(self):
        self.assertEqual(
            qt_observation.optional_number({"ups": 60}, "ups"), 60.0)

    def test_text_is_bounded_and_printable(self):
        self.assertEqual(
            qt_observation.optional_text({"a": "vanilla"}, "a"), "vanilla")
        self.assertIsNone(qt_observation.optional_text({"a": "x" * 500}, "a"))
        self.assertIsNone(qt_observation.optional_text({"a": "bad\nvalue"}, "a"))
        self.assertIsNone(qt_observation.optional_text({"a": ""}, "a"))

    def test_integer_rejects_bool(self):
        self.assertIsNone(qt_observation.optional_int({"n": True}, "n"))
        self.assertEqual(qt_observation.optional_int({"n": 7}, "n"), 7)
        self.assertIsNone(qt_observation.optional_int({"n": 7.5}, "n"))


class StateClosureTests(unittest.TestCase):
    """The state set is closed and every state has a badge."""

    def test_observation_states_are_closed(self):
        self.assertEqual(
            set(qt_observation.OBSERVATION_STATES),
            {qt_observation.OBSERVED, qt_observation.ESTIMATED,
             qt_observation.STALE, qt_observation.UNAVAILABLE},
        )

    def test_every_state_has_a_badge_and_an_object_name(self):
        for state in qt_observation.OBSERVATION_STATES:
            observation = qt_observation.Observation(
                value=1.0, state=state, detail="d")
            self.assertTrue(observation.badge())
            self.assertTrue(observation.badge_object_name().startswith("badge"))

    def test_age_of_never_observed_is_infinite(self):
        observation = qt_observation.Observation()
        self.assertTrue(math.isinf(observation.age_seconds))


class ModulePurityTests(unittest.TestCase):
    """The state model must stay testable without a display server."""

    def test_observation_module_does_not_import_qt(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_observation.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("PySide6", source)
        self.assertNotIn("QtWidgets", source)


class FreshnessTests(unittest.TestCase):
    """A failed refresh ages the value out instead of hiding it."""

    def test_age_of_a_never_observed_value_is_infinite(self):
        observation = qt_observation.Observation()
        self.assertTrue(math.isinf(qt_observation.age_of(observation, 100.0)))

    def test_age_of_a_known_value_is_measured(self):
        observation = qt_observation.observed(1.0, "Observed", observed_at=90.0)
        self.assertEqual(qt_observation.age_of(observation, 100.0), 10.0)

    def test_age_is_never_negative(self):
        observation = qt_observation.observed(1.0, "Observed", observed_at=100.0)
        self.assertEqual(qt_observation.age_of(observation, 50.0), 0.0)

    def test_refresh_with_a_replacement_returns_the_new_value(self):
        last = qt_observation.observed(1.0, "Observed", observed_at=0.0)
        fresh = qt_observation.observed(2.0, "Observed again", observed_at=100.0)
        result = qt_observation.refresh(last, 100.0, 10.0, fresh)
        self.assertIs(result, fresh)
        self.assertTrue(result.fresh)

    def test_refresh_without_a_replacement_ages_the_value_out(self):
        last = qt_observation.observed(1.0, "Observed", observed_at=0.0)
        result = qt_observation.refresh(last, 100.0, 10.0, None)
        self.assertFalse(result.fresh)
        self.assertEqual(result.state, qt_observation.STALE)
        self.assertEqual(result.value, 1.0)

    def test_refresh_keeps_a_value_that_is_still_fresh(self):
        last = qt_observation.observed(1.0, "Observed", observed_at=95.0)
        result = qt_observation.refresh(last, 100.0, 10.0, None)
        self.assertIs(result, last)
        self.assertTrue(result.fresh)


if __name__ == "__main__":
    unittest.main()
