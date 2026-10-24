"""Dashboard catalog evidence must not imply completeness when truncated."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from autoengineer_dashboard import catalog_notice


class CatalogNoticeTests(unittest.TestCase):
    def test_partial_page_is_explicit(self):
        frame = {"status": "ok", "catalog_status": {
            "status": "ok", "page": 1, "page_size": 16, "total_count": 662
        }, "capabilities": {"recipes": [{}] * 8, "truncated": True}}
        text = catalog_notice(frame, {"planner_ready": False, "reason": "not ready"})
        self.assertIn("8/16", text)
        self.assertIn("662", text)
        self.assertIn("disabled", text)

    def test_assembled_failure_is_not_hidden(self):
        frame = {"status": "ok", "catalog_status": {"status": "assembly_failed"}}
        self.assertIn("consistently", catalog_notice(frame, {"planner_ready": False}))

    def test_validated_catalog_reports_qualified(self):
        self.assertIn("qualified", catalog_notice({}, {"planner_ready": True}))

    def test_unavailable_observation_fails_closed(self):
        self.assertIn("disabled", catalog_notice(
            {"status": "unavailable"}, {"planner_ready": False}
        ))


if __name__ == "__main__":
    unittest.main()
