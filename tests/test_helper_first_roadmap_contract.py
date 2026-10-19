"""Checks that the published engineering contract stays internally consistent."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_contract(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class TestHelperFirstDocumentation(unittest.TestCase):
    def test_roadmap_has_helper_first_gate(self) -> None:
        roadmap = read_contract("ROADMAP.md")
        self.assertIn("Gate H1 — mandatory Helper + Dashboard acceptance", roadmap)
        self.assertIn("**never place entities in Helper mode**", roadmap)
        self.assertIn("pre-R07 data/math/safety readiness", roadmap)
        self.assertIn("pY continuously in isolation", roadmap)

    def test_safety_rules_keep_autonomy_locked(self) -> None:
        spec = read_contract("docs/HELPER_FIRST_GATE_H1.md")
        guide = read_contract("docs/ZOO_CODE_TASK_PROTOCOL.md")
        self.assertIn("No Semi-Autonomous feature expansion", spec)
        self.assertIn("Fully Autonomous development before H1 is accepted", spec)
        self.assertIn("Fully Autonomous stays locked", guide)
        self.assertIn("no game placement in Helper", guide)

    def test_qualified_modded_gameplay_is_later(self) -> None:
        requirements = read_contract("docs/PLANNING_REQUIREMENTS.md")
        benchmarks = read_contract("docs/CONTINUOUS_MOD_BENCHMARKS.md")
        self.assertIn("live third-party gameplay automation", requirements)
        self.assertIn("separate, isolated Factorio profile", benchmarks)
        self.assertIn("actual_pyanodons_data", read_contract("benchmarks/modded_recipe_graph.py"))


if __name__ == "__main__":
    unittest.main()
