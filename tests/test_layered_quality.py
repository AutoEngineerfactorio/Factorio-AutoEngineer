"""Tests for layered verification gate."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory"))
from layered_quality import command, run_checks


class LayeredTests(unittest.TestCase):
    def test_missing_tool_blocks(self):
        with patch("layered_quality.shutil.which", return_value=None):
            self.assertEqual(command("unknown", ["nonexistent_autoengineer_binary"])[1], "BLOCKED")

    def test_failed_command_is_not_pass(self):
        with patch("layered_quality.shutil.which", return_value="tool"):
            with patch("layered_quality.subprocess.run", return_value=Mock(returncode=2, stdout="", stderr="error")):
                self.assertEqual(command("bad", ["tool"])[1], "FAIL")

    def test_successful_command_passes(self):
        with patch("layered_quality.shutil.which", return_value="tool"):
            with patch("layered_quality.subprocess.run", return_value=Mock(returncode=0, stdout="ok", stderr="")):
                self.assertEqual(command("good", ["tool"])[1], "PASS")

    def test_requested_problems_gate_is_included(self):
        with patch("layered_quality.command", side_effect=lambda name, argv, **kw: (name, "PASS", "ok")):
            result = run_checks(problems=True, typing=True, tests=True)
        self.assertEqual({name for name, _, _ in result}, {
            "Ruff", "Patch whitespace", "Unit tests", "Pyright", "VS Code Problems"
        })

    def test_optional_factorio_gates_require_explicit_selection(self):
        with patch("layered_quality.command", side_effect=lambda name, argv, **kw: (name, "PASS", "ok")):
            selected = run_checks(problems=False, tests=False, lua=True,
                                  backend=Path("pinned-upstream"), live=True)
        names = {name for name, _, _ in selected}
        self.assertIn("Factorio LuaLS", names)
        self.assertIn("Isolated .NET backend", names)
        self.assertIn("Read-only Factorio smoke", names)

    def test_luals_binary_falls_back_to_vscode_extension(self):
        from layered_quality import luals_executable
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / ".vscode" / "extensions" / "sumneko.lua-3.19.2" / "server" / "bin"
            package.mkdir(parents=True)
            binary = package / "lua-language-server.exe"
            binary.write_bytes(b"")
            with patch("layered_quality.shutil.which", return_value=None), patch(
                "layered_quality.Path.home", return_value=Path(folder)
            ):
                self.assertEqual(luals_executable(), str(binary))

    def test_explicit_bootstrap_mode_omits_diagnostics(self):
        with patch("layered_quality.command", side_effect=lambda name, argv, **kw: (name, "PASS", "ok")):
            result = run_checks(problems=False, typing=False, tests=False)
        self.assertNotIn("VS Code Problems", {name for name, _, _ in result})


if __name__ == "__main__":
    unittest.main()
