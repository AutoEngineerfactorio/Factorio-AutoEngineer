"""Limited item flow is labelled and never mistaken for complete history."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from telemetry_view import TelemetryView


class LightFlowViewTests(unittest.TestCase):
    def test_limited_samples_have_explicit_coverage_label(self):
        stub = Mock()
        stub.last_tick = None
        frame = {"status": "unavailable",
                 "sampled_item_flow": [{"name": "iron-plate", "input": 2.5, "output": 3.0}]}
        TelemetryView.update_frame(stub, frame)
        written = stub.lightweight_flow.set.call_args.args[0]
        self.assertIn("NOT total factory production", written)
        self.assertIn("iron-plate", written)

    def test_empty_samples_are_not_claimed_as_full_factory_rates(self):
        stub = Mock()
        TelemetryView.update_frame(stub, {"status": "unavailable", "sampled_item_flow": []})
        self.assertIn("factory-wide rates unavailable",
                      stub.lightweight_flow.set.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
