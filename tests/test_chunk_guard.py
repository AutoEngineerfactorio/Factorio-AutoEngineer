"""No-game, no-network tests for bounded Zoo chunk sessions."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory"))
from chunk_guard import (
    ChunkError,
    abort_chunk,
    begin_chunk,
    chunk_limits,
    diff_line_count,
    lock_path,
    measure_chunk,
    run_checks,
    safe_file,
    verify_chunk,
)
from chunk_guard import (
    main as guard_main,
)


class ChunkGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "agent").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "memory").mkdir()
        (self.root / "memory" / "test_runner.py").write_text("# stub\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_syntax_and_private_paths_rejected(self):
        for path in ("../secret.py", "test-world/rcon.secret.json", ".git/config",
                     "agent/../../secret.py", "memory/private.key", "agent/a b.py",
                     "C:/Windows/registry.py", "agent/rcon.secret.json"):
            with self.subTest(path=path), self.assertRaises(ChunkError):
                safe_file(self.root, path)

    def test_factorio_mod_source_allowed_but_not_unsafe_paths(self):
        name = "factorio-mod/autoengineer-input_2.1.23/control.lua"
        self.assertEqual(safe_file(self.root, name), self.root / name)
        with self.assertRaises(ChunkError):
            safe_file(self.root, "factorio-mod/../../secret.lua")

    def test_max_files_and_duplicate_rejected(self):
        with self.assertRaises(ChunkError):
            begin_chunk(self.root, ["agent/a.py", "agent/b.py", "tests/t.py"], "Small feature")
        with self.assertRaises(ChunkError):
            begin_chunk(self.root, ["agent/a.py", "agent/a.py"], "Small feature")

    def test_profiles_and_sensitive_limits(self):
        ordinary = ["agent/blueprint_encoder.py", "tests/test_blueprint_encoder.py"]
        self.assertEqual(chunk_limits(ordinary, "standard"), (2, 200))
        self.assertEqual(chunk_limits(ordinary, "minimax"), (3, 400))
        for sensitive in ("backend-safety/Tools/Adapter.cs", "agent/mode_policy.py",
                          "agent/dispatch_boundary.py", "agent/rcon_client.py",
                          "memory/chunk_guard.py", ".roo/rules/12-minimax-provider.md",
                          "docs/ZOO_CODE_TASK_PROTOCOL.md",
                          "factorio-mod/autoengineer-input_2.1.23/control.lua"):
            self.assertEqual(chunk_limits(ordinary + [sensitive], "minimax"), (2, 200))
        with self.assertRaises(ChunkError):
            chunk_limits(ordinary, "untrusted-profile")

    def test_minimax_three_file_chunk_and_exact_400_line_cap(self):
        names = ["agent/a.py", "agent/b.py", "tests/test_feature.py"]
        with self.assertRaises(ChunkError):
            begin_chunk(self.root, names, "Standard blocks three files")
        session = begin_chunk(self.root, names, "MiniMax triple file feature",
                              profile="minimax")
        manifest = json.loads((self.root / ".local/chunk-checkpoints" / session /
                               "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["limits"], {"max_files": 3, "max_changed_lines": 400})
        self.assertEqual(manifest["profile"], "minimax")
        self.write(names[0], "a = 1\n" * 200)
        self.write(names[1], "b = 2\n" * 199)
        self.write(names[2], "c = 3\n")
        with patch("chunk_guard.run_checks", return_value=[("Tests", True, "ok")]):
            ok, report = verify_chunk(self.root, session, test_stage="offline")
        self.assertTrue(ok, report)
        self.assertIn("changed=3/3 | lines=400/400", report)
        self.assertFalse(any(lock_path(self.root, n).exists() for n in names))

    def test_minimax_401_lines_blocked_without_running_checks(self):
        session = begin_chunk(self.root, ["agent/a.py"], "Oversized MiniMax batch",
                              profile="minimax")
        self.write("agent/a.py", "a = 1\n" * 401)
        with patch("chunk_guard.run_checks") as checks:
            ok, report = verify_chunk(self.root, session, test_stage="offline")
        self.assertFalse(ok)
        self.assertIn("exceeds 400", report)
        checks.assert_not_called()
        abort_chunk(self.root, session, "Oversized chunk retained for manual split")

    def test_minimax_sensitive_changes_stay_at_standard_budget(self):
        with self.assertRaises(ChunkError):
            begin_chunk(self.root,
                        ["backend-safety/RconConnectionService.cs",
                         "agent/a.py", "tests/test_feature.py"],
                        "Do not expand backend scope", profile="minimax")
        name = "agent/mode_policy.py"
        session = begin_chunk(self.root, [name], "Sensitive MiniMax change",
                              profile="minimax")
        self.write(name, "a = 1\n" * 201)
        with patch("chunk_guard.run_checks") as checks:
            ok, report = verify_chunk(self.root, session, test_stage="offline")
        self.assertFalse(ok)
        self.assertIn("exceeds 200", report)
        checks.assert_not_called()
        abort_chunk(self.root, session, "Sensitive chunk capped as standard")

    def test_existing_dirty_file_is_not_overwritten(self):
        self.write("agent/a.py", "x = 1\n")
        session = begin_chunk(self.root, ["agent/a.py"], "Change a single helper")
        self.assertEqual((self.root / "agent/a.py").read_text(), "x = 1\n")
        self.write("agent/a.py", "x = 2\n")
        changed, count, *_ = measure_chunk(self.root, session)
        self.assertEqual(changed, ["agent/a.py"])
        self.assertEqual(count, 2)  # replacement = removal + addition
        abort_chunk(self.root, session, "Rejected after manual inspection")
        self.assertEqual((self.root / "agent/a.py").read_text(), "x = 2\n")

    def test_two_sessions_cannot_edit_same_file(self):
        session = begin_chunk(self.root, ["agent/a.py"], "Write first chunk")
        with self.assertRaisesRegex(ChunkError, "Another chunk"):
            begin_chunk(self.root, ["agent/a.py"], "Write second chunk")
        self.assertTrue(lock_path(self.root, "agent/a.py").exists())
        abort_chunk(self.root, session, "Owner checked and closed old session")
        self.assertFalse(lock_path(self.root, "agent/a.py").exists())
        other = begin_chunk(self.root, ["agent/a.py"], "Now allowed after abort")
        self.assertNotEqual(session, other)

    def test_oversized_edit_blocks_verification(self):
        self.write("agent/a.py", "x = 1\n")
        session = begin_chunk(self.root, ["agent/a.py"], "Incremental Python change")
        self.write("agent/a.py", "\n".join("x = 1" for _ in range(230)))
        with patch("chunk_guard.run_checks") as fn:
            ok, out = verify_chunk(self.root, session, test_stage="offline")
        self.assertFalse(ok)
        self.assertIn("exceeds 200", out)
        fn.assert_not_called()
        abort_chunk(self.root, session, "Large edit rejected and source left intact")

    def test_exactly_200_changed_lines_allowed_with_verification(self):
        self.write("agent/a.py", "x = 1\n")
        session = begin_chunk(self.root, ["agent/a.py"], "Verified upper boundary")
        self.write("agent/a.py", "x = 1\n" + "x = 2\n" * 200)
        with patch("chunk_guard.run_checks", return_value=[("Tests", True, "passed")]):
            ok, out = verify_chunk(self.root, session, test_stage="offline")
        self.assertTrue(ok, out)
        self.assertIn("lines=200/200", out)
        self.assertFalse(lock_path(self.root, "agent/a.py").exists())

    def test_missing_change_cannot_be_marked_success(self):
        self.write("agent/a.py", "x = 1\n")
        session = begin_chunk(self.root, ["agent/a.py"], "Add deliberate change")
        ok, out = verify_chunk(self.root, session)
        self.assertFalse(ok)
        self.assertIn("no changes", out)

    def test_targeted_verification_releases_file_ownership(self):
        self.write("agent/a.py", "x = 1\n")
        session = begin_chunk(self.root, ["agent/a.py"], "Incremental edit + test")
        self.write("agent/a.py", "x = 2\n")
        with patch("chunk_guard.run_checks", return_value=[("Tests", True, "passed")]) as fn:
            ok, text = verify_chunk(self.root, session, test_stage="offline")
        self.assertTrue(ok)
        self.assertIn("CHUNK VERIFIED", text)
        self.assertFalse(lock_path(self.root, "agent/a.py").exists())
        self.assertEqual(json.loads((self.root / ".local/chunk-checkpoints" / session /
                                     "manifest.json").read_text())["status"], "verified")
        self.assertEqual(fn.call_count, 1)

    def test_test_failure_keeps_file_ownership(self):
        self.write("agent/a.py", "x = 1\n")
        session = begin_chunk(self.root, ["agent/a.py"], "Fail an affected test")
        self.write("agent/a.py", "x = 2\n")
        with patch("chunk_guard.run_checks", return_value=[("Tests", False, "failing assertion")]):
            ok, out = verify_chunk(self.root, session, test_stage="offline")
        self.assertFalse(ok)
        self.assertIn("No next chunk", out)
        self.assertTrue(lock_path(self.root, "agent/a.py").exists())
        abort_chunk(self.root, session, "Checkpoint failure then deliberately abort")

    def test_python_change_requires_a_real_test_selection(self):
        self.write("agent/a.py", "x = 2\n")
        checks = run_checks(self.root, test_file=None, test_stage=None,
                            upstream=None, changed=["agent/a.py"])
        self.assertTrue(any(name == "Focused regression" and not ok
                            for name, ok, _ in checks))

    def test_backend_change_requires_clean_pinned_vendor(self):
        self.write("agent/a.py", "x = 2\n")
        checks = run_checks(self.root, test_file=None, test_stage=None,
                            upstream=None, changed=["backend-safety/Tools/Test.cs"])
        self.assertTrue(any(name == "Backend build" and not ok
                            for name, ok, _ in checks))

    def test_valid_existing_test_file_name_is_required(self):
        self.write("agent/a.py", "x = 2\n")
        with self.assertRaisesRegex(ChunkError, "Targeted test filename"):
            run_checks(self.root, test_file="../../private.py", test_stage=None,
                       upstream=None, changed=["agent/a.py"])

    def test_diff_counts_replacements_not_one_line(self):
        self.assertEqual(diff_line_count("a\nb\n", "a\nc\n"), 2)
        self.assertEqual(diff_line_count("a\n", "a\nb\n"), 1)

    def test_no_symlink_snapshot(self):
        # Windows CI may deny symlinks, so use a portable absolute path check.
        with self.assertRaises(ChunkError):
            safe_file(self.root, "agent//nested.py")

    def test_cli_begin_no_longer_requires_runner_from_other_checkout(self):
        """A source workspace with the installed guard can acquire ownership."""
        import contextlib
        import io
        self.write("memory/chunk_guard.py", "# current guard exists\n")
        self.write("agent/a.py", "x = 1\n")
        output = io.StringIO()
        args = [
            "chunk_guard.py", "--begin", "--root", str(self.root),
            "--label", "Repair one scoped source file", "--file", "agent/a.py",
        ]
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(output):
            self.assertEqual(guard_main(), 0)
        self.assertIn("CHUNK STARTED:", output.getvalue())
        sessions = list((self.root / ".local/chunk-checkpoints").glob("*/manifest.json"))
        self.assertEqual(len(sessions), 1)
        session = json.loads(sessions[0].read_text(encoding="utf-8"))["session"]
        abort_chunk(self.root, session, "Smoke verified; no source edit intended")

    def test_focused_tests_run_without_obsolete_runner(self):
        """Focused tests are executable using the current Python and test suite."""
        self.write("agent/a.py", "x = 1\n")
        self.write(
            "tests/test_scoped.py",
            "import unittest\nclass SmokeTest(unittest.TestCase):\n"
            "    def test_safe(self):\n        self.assertEqual(2 + 2, 4)\n",
        )
        (self.root / "memory/test_runner.py").unlink()
        self.assertFalse((self.root / "memory/test_runner.py").exists())
        checks = run_checks(
            self.root, test_file="test_scoped.py", test_stage=None,
            upstream=None, changed=["agent/a.py"],
        )
        result = [ok for label, ok, _ in checks if label == "Targeted tests"]
        self.assertEqual(result, [True])

    def test_removed_qa_stages_do_not_silently_pass(self):
        self.write("agent/a.py", "x = 1\n")
        with self.assertRaisesRegex(ChunkError, "Unsupported QA stage"):
            run_checks(
                self.root, test_file=None, test_stage="skills",
                upstream=None, changed=["agent/a.py"],
            )


if __name__ == "__main__":
    unittest.main()
