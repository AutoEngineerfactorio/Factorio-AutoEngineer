"""Contract tests for the R10-A concurrent dashboard stress harness."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "agent"))


class DashboardStressContractTests(unittest.TestCase):
    """The harness must stay read-only and must measure the real stack."""

    def setUp(self):
        self.source = (ROOT / "tests" / "live_r10a_dashboard_stress.py").read_text(
            encoding="utf-8")

    def test_the_harness_uses_the_real_observation_path(self):
        """The dashboard must run the shipped bridge and shell."""
        self.assertIn("ObservationBridge", self.source)
        self.assertIn("ObservationService", self.source)
        self.assertIn("ShellWindow", self.source)
        self.assertIn("start_observations", self.source)

    def test_the_harness_uses_the_real_backend(self):
        """The dashboard must talk to the restricted C# backend."""
        self.assertIn("RESTRICTED_BACKEND", self.source)
        self.assertIn("stdio_client", self.source)

    def test_the_harness_drives_the_catalog(self):
        """The Recipes & Research workspace must ask for the catalog."""
        self.assertIn("refresh_button.click()", self.source)
        self.assertIn("catalog_latencies", self.source)

    def test_the_harness_runs_offscreen(self):
        """The dashboard must not need a display server."""
        self.assertIn("QT_QPA_PLATFORM", self.source)

    def test_the_harness_never_prints_the_password(self):
        """The RCON password must never reach the report or the console."""
        self.assertNotIn("print(password", self.source)
        self.assertNotIn("password\":", self.source)

    def test_the_harness_calls_no_gameplay_tool(self):
        """Only the read-only observation tools may be named."""
        for forbidden in ("autoengineer_operation", "autoengineer_arm",
                          "walk_to_position", "autoengineer_renew"):
            self.assertNotIn(f'"{forbidden}"', self.source)

    def test_the_harness_waits_for_the_games_rcon_port(self):
        """The backend gives up if the RCON port is not open yet."""
        self.assertIn("_wait_for_rcon", self.source)
        self.assertIn("create_connection", self.source)

    def test_the_tail_summary_reports_the_real_minimum(self):
        """The UPS summary must include the minimum, not only the average."""
        import live_r10a_dashboard_stress as harness

        summary = harness._tail([60.0, 59.5, 60.2])
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["minimum"], 59.5)
        self.assertEqual(summary["maximum"], 60.2)
        self.assertEqual(harness._tail([]), {"count": 0})

    def test_the_credentials_are_read_from_the_private_host_config(self):
        """The port and password come from the harness-owned private file."""
        import live_r10a_dashboard_stress as harness

        self.assertIsNone(harness._read_host_credentials(ROOT / "no-such-dir"))
        work = ROOT / ".local" / "r10a-credential-probe"
        work.mkdir(parents=True, exist_ok=True)
        config = work / "host.private.ini"
        config.write_text(
            "[other]\nlocal-rcon-socket=127.0.0.1:29999\n"
            "local-rcon-password=not-a-real-secret\n", encoding="utf-8")
        try:
            credentials = harness._read_host_credentials(work)
            assert credentials is not None
            port, password = credentials
            self.assertEqual(port, 29999)
            self.assertEqual(password, "not-a-real-secret")
        finally:
            config.unlink(missing_ok=True)
            try:
                work.rmdir()
            except OSError:
                pass



def _main_thread_qt_probe():
    import os
    from importlib import import_module

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = import_module("PySide6.QtWidgets").QApplication([])
    window = import_module("qt_shell").ShellWindow()
    window.show()
    app.processEvents()
    window.close()
    app.processEvents()


class MainThreadQtProcessTests(unittest.TestCase):
    def test_dedicated_qt_process_exits_cleanly(self):
        from importlib import import_module, util

        if util.find_spec("PySide6") is None:
            self.skipTest("Qt unavailable")
        context = import_module("multiprocessing").get_context("spawn")
        child = context.Process(target=_main_thread_qt_probe)
        child.start()
        child.join(timeout=15)
        if child.is_alive():
            child.terminate()
            child.join(timeout=3)
            self.fail("Qt probe did not stop")
        self.assertEqual(child.exitcode, 0)


class DashboardVerdictTests(unittest.TestCase):
    def test_partial_or_failed_worker_cannot_pass_on_game_statistics_alone(self):
        from copy import deepcopy

        from live_r10a_dashboard_stress import dashboard_pass

        report = {"error": None, "worker_exit_code": 0, "worker_stopped": True,
                  "frames_emitted": 10, "pillow_evidence": {"not_blank": True,
                  "network_rows": 1, "catalog_complete": True,
                  "catalog_surface": "nauvis", "surface": "nauvis"}}
        self.assertTrue(dashboard_pass(report))
        for field, value in (("catalog_complete", False), ("catalog_surface", "different"),
                             ("not_blank", False), ("network_rows", 0)):
            failed = deepcopy(report)
            failed["pillow_evidence"][field] = value
            self.assertFalse(dashboard_pass(failed))
        report["worker_exit_code"] = 1
        self.assertFalse(dashboard_pass(report))

if __name__ == "__main__":
    unittest.main()
