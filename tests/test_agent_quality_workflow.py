"""Automated coding workflow verification."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory"))
import agent_quality_workflow as q


class AgentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = patch.object(q, "BASELINE", self.root / "baseline.json")
        self.b = patch.object(q, "FILE_BASELINE", self.root / "files.json")
        self.c = patch.object(q, "REPORT", self.root / "report.json")
        self.d = patch.object(q, "file_digests", return_value={})
        for p in (self.a, self.b, self.c, self.d):
            p.start()
            self.addCleanup(p.stop)

    def begin(self, sources=None):
        q.BASELINE.write_text("{}", encoding="utf-8")
        q.FILE_BASELINE.write_text(json.dumps(sources or {}), encoding="utf-8")

    def test_finish_executes_both_gates(self):
        self.begin()
        with patch.object(q, "run", return_value=Mock(returncode=0)) as runner:
            with patch.object(sys, "argv", ["workflow", "finish"]):
                self.assertEqual(q.main(), 0)
        self.assertEqual(runner.call_count, 2)
        self.assertTrue(json.loads(q.REPORT.read_text())["passed"])

    def test_finish_blocks_without_baseline(self):
        with patch.object(sys, "argv", ["workflow", "finish"]):
            self.assertEqual(q.main(), 2)

    def test_failed_check_blocks(self):
        self.begin()
        with patch.object(q, "run", return_value=Mock(returncode=1)):
            with patch.object(sys, "argv", ["workflow", "finish"]):
                self.assertEqual(q.main(), 1)

    def test_changed_source_requires_regression_test(self):
        self.assertEqual(q.regression_check(
            {"agent/a.py": "old"}, {"agent/a.py": "new"}), (False, 1, 0))
        self.assertEqual(q.regression_check(
            {"agent/a.py": "old"}, {"agent/a.py": "new", "tests/test_a.py": "new"}),
            (True, 1, 1))

    def test_new_bugfix_without_test_fails_finish(self):
        self.begin({"agent/a.py": "old"})
        q.file_digests.return_value = {"agent/a.py": "new"}
        with patch.object(q, "run", return_value=Mock(returncode=0)):
            with patch.object(sys, "argv", ["workflow", "finish"]):
                self.assertEqual(q.main(), 1)


if __name__ == "__main__":
    unittest.main()
