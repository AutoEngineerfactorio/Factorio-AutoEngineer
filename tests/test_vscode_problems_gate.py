"""Unit tests for actual VS Code diagnostics regression gate."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory"))
from vscode_problems_gate import capture, check, load_snapshot


def snapshot(path, issues, stamp="2026-10-24T21:15:00Z"):
    import datetime
    if stamp == "now":
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data = {"available": True, "truncated": False, "updatedAt": stamp,
            "errors": sum(i["severity"] == "error" for i in issues),
            "warnings": sum(i["severity"] == "warning" for i in issues),
            "total": len(issues), "shown": len(issues), "issues": issues}
    path.write_text(json.dumps(data), encoding="utf-8")


class ProblemsGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "actual.json"
        self.base = Path(self.tmp.name) / "baseline.json"
        self.issue = {"severity": "error", "file": "foo.py", "source": "Pylance",
                      "code": "reportOptionalMemberAccess", "message": "None access"}

    def test_preexisting_error_does_not_block(self):
        snapshot(self.source, [self.issue], "now")
        capture(self.base, self.source)
        from datetime import datetime, timedelta, timezone
        later = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        snapshot(self.source, [self.issue], later)
        current, added = check(self.base, self.source)
        self.assertEqual(current["errors"], 1)
        self.assertFalse(added)

    def test_new_error_blocks(self):
        snapshot(self.source, [], "now")
        capture(self.base, self.source)
        from datetime import datetime, timedelta, timezone
        later = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
        snapshot(self.source, [self.issue], later)
        _, added = check(self.base, self.source)
        self.assertEqual(sum(added.values()), 1)

    def test_stale_snapshot_fails_closed(self):
        snapshot(self.source, [], "2020-01-01T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "stale"):
            load_snapshot(self.source)

    def test_truncated_fails_closed(self):
        snapshot(self.source, [self.issue], "now")
        data = json.loads(self.source.read_text())
        data["truncated"] = True
        self.source.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "truncated"):
            load_snapshot(self.source)

    def test_no_refreshed_snapshot_blocks(self):
        snapshot(self.source, [], "now")
        capture(self.base, self.source)
        with self.assertRaisesRegex(ValueError, "refreshed"):
            check(self.base, self.source)


if __name__ == "__main__":
    unittest.main()
