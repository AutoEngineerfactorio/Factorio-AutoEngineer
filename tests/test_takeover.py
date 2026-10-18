import io
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from autoengineer_dashboard import Dashboard
from session_safety import ConsoleControl


class TakeoverTests(unittest.TestCase):
    def view(self):
        v = Dashboard.__new__(Dashboard)
        v.proc = NS(poll=lambda: None, stdin=io.StringIO())
        v.stop_requested = False
        v.stop_confirmed = False
        v.current_mode = "semi"
        v.closing = False
        v.waiting_for_approval = True
        v.manual_control = False
        for key in (
            "status",
            "mode",
            "mode_note",
            "resume_button",
            "start_button",
            "approve_button",
            "reject_button",
            "stop_button",
        ):
            setattr(v, key, Mock())
        v.sync_mode_controls = Mock()
        v.append = Mock()
        v.live_view = NS(
            available=True,
            received=time.monotonic() + 0.001,
            last=dict(
                control=dict(
                    input_adapter=True, character_control=True, lease_active=False, walking=False
                )
            ),
        )
        return v

    def test_takeover_blocks_late_approval_and_keeps_helper(self):
        v = self.view()
        with patch("autoengineer_dashboard.threading.Thread"):
            v.take_control()
            v.answer("y")
            v.set_approval(True)
        self.assertEqual(v.proc.stdin.getvalue(), "q\n")
        self.assertTrue(v.manual_control)
        self.assertEqual(v.current_mode, "helper")
        self.assertFalse(v.waiting_for_approval)

    def test_resume_requires_stop_and_observation_after_takeover(self):
        v = self.view()
        v.manual_control = True
        v.takeover_started = time.monotonic()
        with (
            patch("autoengineer_dashboard.messagebox.showinfo"),
            patch("autoengineer_dashboard.messagebox.askyesno", return_value=True) as confirm,
        ):
            v.resume_control()
            confirm.assert_not_called()
            v.proc = None
            v.stop_requested = True
            v.resume_control()
            confirm.assert_not_called()
            v.stop_confirmed = True
            v.live_view.received = v.takeover_started - 0.1
            v.resume_control()
            confirm.assert_not_called()
            v.takeover_started -= 1
            v.live_view.received = time.monotonic()
            v.resume_control()
        self.assertFalse(v.manual_control)
        self.assertEqual(v.current_mode, "semi")
        self.assertIsNone(v.proc)

    def test_resume_refuses_remote_view_and_missing_adapter(self):
        for field in ("character_control", "input_adapter"):
            v = self.view()
            v.proc = None
            v.manual_control = True
            v.takeover_started = 0
            v.live_view.last["control"][field] = False
            with (
                patch("autoengineer_dashboard.messagebox.showinfo"),
                patch("autoengineer_dashboard.messagebox.askyesno") as confirm,
            ):
                v.resume_control()
                confirm.assert_not_called()
            self.assertTrue(v.manual_control)

    def test_console_stop_discards_buffered_approval(self):
        c = ConsoleControl()
        c.awaiting_answer = True
        c.feed("y\n")
        c.feed("q\n")
        self.assertTrue(c.stop.is_set())
        self.assertTrue(c.answers.empty())
