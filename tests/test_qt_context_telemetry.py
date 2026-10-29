"""Validate new live context independently of legacy production/power schemas."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from qt_telemetry import build_model


def payload():
    return {"protocol": 1, "status": "ok", "tick": 1,
            "production": {"status": "unavailable"}, "power": {"status": "unavailable"}}


class ContextModelTests(unittest.TestCase):
    def test_valid_context_is_preserved_with_local_coverage(self):
        raw = payload()
        raw.update(research={"status": "ok", "active": True, "name": "mining", "progress": .5},
                   pollution={"status": "ok", "coverage": "character_chunk", "amount": 12})
        model = build_model(raw)
        self.assertTrue(model.research_active)
        self.assertEqual(model.research_progress, .5)
        self.assertEqual(model.pollution_amount, 12)

    def test_invalid_or_missing_values_are_unknown_not_zero(self):
        raw = payload()
        raw.update(research={"status": "ok", "active": True, "name": "mining", "progress": 3},
                   pollution={"status": "ok", "coverage": "entire_surface", "amount": 12})
        model = build_model(raw)
        self.assertIsNone(model.research_active)
        self.assertIsNone(model.pollution_amount)
        model = build_model(payload())
        self.assertIsNone(model.research_progress)
