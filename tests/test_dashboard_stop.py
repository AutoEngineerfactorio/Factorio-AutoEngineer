"""Exercise dashboard shutdown without creating a Tk window or child process."""
import io
from pathlib import Path
import queue
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from autoengineer_dashboard import Dashboard


class DashboardStopTests(unittest.TestCase):
    def dashboard(self):
        view = Dashboard.__new__(Dashboard)
        view.proc = SimpleNamespace(poll=lambda: None, stdin=io.StringIO())
        view.q = queue.Queue()
        view.stop_requested = False
        view.stop_confirmed = False
        view.closing = False
        view.waiting_for_approval = True
        view.status = Mock()
        view.root = Mock()
        view.start_button = Mock()
        view.stop_button = Mock()
        view.approve_button = Mock()
        view.reject_button = Mock()
        view.append = Mock()
        view.inspect_line = Mock()
        return view

    def test_stop_is_idempotent_and_blocks_approval(self):
        view = self.dashboard()
        with patch("autoengineer_dashboard.threading.Thread") as thread:
            view.stop()
            view.stop()
            view.answer("y")
        self.assertEqual(view.proc.stdin.getvalue(), "q\n")
        self.assertTrue(view.stop_requested)
        self.assertFalse(view.waiting_for_approval)
        self.assertEqual(thread.call_count, 1)

    def test_old_session_exit_cannot_clear_current_session(self):
        view = self.dashboard()
        current = view.proc
        view.q.put((object(), "exit", 0))
        view.q.put((object(), "line", "SAFETY_STOP_CONFIRMED\n"))
        view.process_events()
        self.assertIs(view.proc, current)
        self.assertFalse(view.stop_confirmed)

    def test_prompt_after_stop_does_not_reenable_approval(self):
        view = self.dashboard()
        view.stop_requested = True
        view.waiting_for_approval = False
        view.q.put((view.proc, "prompt", None))
        view.process_events()
        self.assertFalse(view.waiting_for_approval)

    def test_close_waits_for_controller_exit(self):
        view = self.dashboard()
        with patch("autoengineer_dashboard.messagebox.askyesno", return_value=True), patch.object(view, "stop") as stop:
            view.on_close()
        stop.assert_called_once()
        view.root.destroy.assert_not_called()
        view.q.put((view.proc, "exit", 0))
        view.process_events()
        view.root.destroy.assert_called_once()
        view.status.set.assert_called_with("Exited; game-side stop unconfirmed")

    def test_close_when_controller_exits_during_confirmation(self):
        view = self.dashboard()
        def controller_exits(*args):
            view.proc = None  # Nested dialog event loop has consumed the exit event.
            return True
        with patch("autoengineer_dashboard.messagebox.askyesno", side_effect=controller_exits):
            view.on_close()
        view.root.destroy.assert_called_once()

    def test_closing_dashboard_cannot_start_another_session(self):
        view = self.dashboard()
        view.proc = None
        view.closing = True
        with patch("autoengineer_dashboard.subprocess.Popen") as launch:
            view.start()
        launch.assert_not_called()

    def test_only_explicit_acknowledgement_confirms_stop(self):
        view = self.dashboard()
        view.q.put((view.proc, "line", "SAFETY_STOP_CONFIRMED\n"))
        view.q.put((view.proc, "exit", 0))
        view.process_events()
        self.assertTrue(view.stop_confirmed)
        view.status.set.assert_called_with("Game-side stop acknowledged")

    def test_late_planning_output_cannot_replace_stopping_status(self):
        view = self.dashboard()
        view.stop_requested = True
        Dashboard.inspect_line(view, "AI CYCLE 2/3")
        view.status.set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
