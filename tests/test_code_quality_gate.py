"""Minimal tests for Zoo's offline coding quality gate."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory"))
from code_quality_gate import (
    check_structured_files,
    check_syntax,
    decode_paths,
    is_sensitive_path,
    run_quick,
)


class QualityGateTests(unittest.TestCase):
    def test_private_paths_blocked(self):
        for path in ("test-world/rcon.secret.json", "launcher.local.json",
                     "config.local.json", ".local/logs/x", "models/secret.gguf",
                     "somedir/.env", "keys/private.pem"):
            with self.subTest(path=path):
                self.assertTrue(is_sensitive_path(path))
        self.assertFalse(is_sensitive_path("tests/test_code_quality_gate.py"))

    def test_git_nul_name_parsing(self):
        self.assertEqual(decode_paths(b"file with spaces.py\x00a.py\x00"),
                         ["file with spaces.py", "a.py"])

    def test_bad_python_syntax_is_rejected(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "invalid.py").write_text("def f(:\n", encoding="utf-8")
            result = check_syntax(root, ["invalid.py"])
            self.assertFalse(result.ok)

    def test_valid_python_syntax_passes_without_execution(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "valid.py").write_text("raise RuntimeError('never executed')\n", encoding="utf-8")
            result = check_syntax(root, ["valid.py"])
            self.assertTrue(result.ok)

    def test_malformed_json_and_empty_patch_fail(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "broken.json").write_text('{"name":', encoding="utf-8")
            (root / "backend.patch.new").write_bytes(b"")
            result = check_structured_files(root, ["broken.json", "backend.patch.new"])
            self.assertFalse(result.ok)
            self.assertIn("Bad JSON", result.detail)
            self.assertIn("Empty source/patch", result.detail)

    def test_git_changes_checked_without_writing_repo(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "normal.py").write_text("x=1\n", encoding="utf-8")
            results = run_quick(root)
            self.assertTrue(all(x.ok for x in results))
            (root / "broken.py").write_text("def :(\n", encoding="utf-8")
            bad = run_quick(root)
            self.assertFalse(all(x.ok for x in bad))


if __name__ == "__main__":
    unittest.main()
