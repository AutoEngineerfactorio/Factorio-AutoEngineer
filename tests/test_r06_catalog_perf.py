"""Regression tests for the catalog, search and machine performance harness.

The harness is an OFFLINE measurement tool. These tests pin the shape of
its inputs and outputs so the numbers it reports stay comparable, and they
prove that the measured path really is the path the dashboard uses.

The synthetic catalogs are SYNTHETIC fixtures. They are not Pyanodons
recipe data and they are not gameplay certification.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tests"))

from r06_catalog_perf_benchmark import (  # noqa: E402
    measure,
    observed_catalog,
    run_all,
    synthetic_catalog,
)


class CatalogPerformanceHarnessTests(unittest.TestCase):
    def test_a_synthetic_catalog_validates_and_is_plannable(self):
        report = measure(synthetic_catalog(200), label="SYNTHETIC-200")
        self.assertEqual(report["recipes"], 200)
        self.assertEqual(report["plan_status"], "ok")
        self.assertGreater(report["validate_seconds"], 0.0)
        self.assertGreater(report["search_0_matches"], 0)

    def test_the_search_sees_every_row_and_the_counts_match(self):
        catalog = synthetic_catalog(300)
        report = measure(catalog, label="SYNTHETIC-300",
                         search_terms=("synthetic-recipe-0001", "synthetic-recipe-"))
        # The narrow term matches the 0001xx names and the broad term matches
        # every row, which proves the search is not capped by the visible-row
        # limit the dashboard applies when it fills the tree view.
        self.assertEqual(report["search_0_term"], "synthetic-recipe-0001")
        self.assertEqual(report["search_0_matches"], 100)
        self.assertEqual(report["search_1_matches"], 300)

    def test_the_measurement_reports_a_bounded_memory_footprint(self):
        report = measure(synthetic_catalog(500), label="SYNTHETIC-500")
        self.assertGreater(report["peak_bytes"], 0)
        # 500 recipes must not cost more than a megabyte per recipe.
        self.assertLess(report["peak_bytes"], 500 * 1024 * 1024)

    def test_the_observed_catalog_is_used_when_the_evidence_is_present(self):
        catalog = observed_catalog()
        if catalog is None:
            self.skipTest("the captured observed rows are not present")
        self.assertGreater(len(catalog["recipes"]), 1000)
        report = measure(catalog, label="OBSERVED",
                         search_terms=("nano",))
        self.assertEqual(report["recipes"], len(catalog["recipes"]))

    def test_the_report_classifies_the_exclusions_and_the_planability(self):
        report = measure(synthetic_catalog(200), label="SYNTHETIC-200")
        # The synthetic catalog carries excluded rows with one reason.
        self.assertEqual(report["excluded_rows"], 4)
        self.assertEqual(report["exclusion_reasons"],
                         {"unknown_field:mod_specific_field": 4})
        # Every synthetic row is either disabled or plannable; the report must
        # say which and must not leave the split implicit.
        reasons = report["plannable_reasons"]
        self.assertEqual(sum(reasons.values()), 200)
        self.assertIn("disabled", reasons)
        self.assertIn("plannable", reasons)

    def test_every_input_is_measured(self):
        reports = run_all()
        labels = [report["label"] for report in reports]
        self.assertIn("SYNTHETIC-1000", labels)
        self.assertIn("SYNTHETIC-5000", labels)
        self.assertIn("SYNTHETIC-10000", labels)
        self.assertIn("OBSERVED-PYANODONS", labels)


if __name__ == "__main__":
    unittest.main()
