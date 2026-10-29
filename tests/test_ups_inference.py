"""Regression checks for mandatory real tick admission before local AI calls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from ups_inference import (  # noqa: E402
    InferenceDeferred,
    UPSAdmission,
    guarded_urlopen,
    live_status_tick,
)


class Clock:
    def __init__(self):
        self.at = 100.0

    def now(self):
        return self.at

    def sleep(self, seconds):
        self.at += seconds


class AdmissionTests(unittest.TestCase):
    def test_four_real_60ups_samples_admit_one_inference(self):
        clock = Clock()
        ticks = iter([0, 252, 504, 756])
        guard = UPSAdmission(lambda: next(ticks), clock=clock.now,
                             sleep=clock.sleep)
        budget = guard.admit()
        self.assertTrue(budget.ai_allowed)
        rate = budget.estimated_ups
        assert rate is not None
        self.assertAlmostEqual(rate, 60, delta=0.1)

    def test_unknown_game_refuses_without_model(self):
        clock = Clock()
        sample = Mock(side_effect=ConnectionError("Game missing"))
        with self.assertRaises(InferenceDeferred):
            UPSAdmission(sample, clock=clock.now, sleep=clock.sleep).admit()
        self.assertEqual(sample.call_count, 1)

    def test_slow_or_paused_game_prevents_inference(self):
        for ticks in ([0, 220, 440, 660], [0, 0, 0, 0]):
            clock = Clock()
            with self.subTest(ticks=ticks), self.assertRaises(InferenceDeferred):
                UPSAdmission(iter(ticks).__next__, clock=clock.now,
                             sleep=clock.sleep).admit()

    def test_fast_timetools_game_is_not_mistaken_for_headroom(self):
        clock = Clock()
        with self.assertRaisesRegex(InferenceDeferred, "Nonstandard"):
            UPSAdmission(iter([0, 504, 1008, 1512]).__next__,
                         clock=clock.now, sleep=clock.sleep).admit()

    def test_invalid_or_reversing_tick_does_not_admit(self):
        for ticks in ([0, 252, -1, 756], [200, 452, 2, 254]):
            clock = Clock()
            with self.subTest(ticks=ticks), self.assertRaises(InferenceDeferred):
                UPSAdmission(iter(ticks).__next__, clock=clock.now,
                             sleep=clock.sleep).admit()

    def test_required_password_prevents_anonymous_requests(self):
        with patch.dict("os.environ", {"FACTORIO_RCON_PASSWORD": ""}):
            with self.assertRaises(InferenceDeferred):
                live_status_tick()

    def test_local_registered_health_is_source_of_ticks(self):
        rcon = Mock()
        rcon.health.return_value = {"players": 1, "character": True, "tick": 950}
        with (patch.dict("os.environ", {"FACTORIO_RCON_PASSWORD": "fixture"}),
              patch("launcher_services.Rcon", return_value=rcon),
              patch("autoengineer_config.get_settings", return_value={
                  "rcon_host": "127.0.0.1", "rcon_port": 27015})):
            self.assertEqual(live_status_tick(), 950)
            rcon.health.assert_called_once_with()
            rcon.close.assert_called_once_with()

    def test_untrusted_or_missing_status_never_admits(self):
        rcon = Mock()
        rcon.health.return_value = {"players": 0, "character": False, "tick": 5}
        with (patch.dict("os.environ", {"FACTORIO_RCON_PASSWORD": "fixture"}),
              patch("launcher_services.Rcon", return_value=rcon),
              patch("autoengineer_config.get_settings", return_value={
                  "rcon_host": "127.0.0.1", "rcon_port": 27015})):
            with self.assertRaises(InferenceDeferred):
                live_status_tick()
            rcon.close.assert_called_once_with()

    def test_completion_does_not_open_when_gate_deferred(self):
        req = Mock()
        with (patch("ups_inference.UPSAdmission.admit", side_effect=InferenceDeferred("UPS")),
              patch("ups_inference.urllib.request.urlopen") as send):
            with self.assertRaises(InferenceDeferred):
                with guarded_urlopen(req):
                    pass
            send.assert_not_called()

    def test_live_helper_planner_routes_model_request_through_gate(self):
        import io
        import json

        import live_planner

        value = {"choices": [{"message": {"content": "observe"}}]}
        with (patch("ups_inference.UPSAdmission.admit") as admission,
              patch("ups_inference.urllib.request.urlopen",
                    return_value=io.BytesIO(json.dumps(value).encode()))):
            self.assertEqual(live_planner.ask_qwen({}), "observe")
            admission.assert_called_once_with()

    def test_ai_movement_request_also_respects_gate(self):
        import io
        import json

        import ai_movement

        value = {"choices": [{"message": {"content": '{"action":"walk","x":1,"y":1}'}}]}
        with (patch("ups_inference.UPSAdmission.admit") as admission,
              patch("ups_inference.urllib.request.urlopen",
                    return_value=io.BytesIO(json.dumps(value).encode()))):
            proposal = ai_movement.ask_qwen({"position": {"x": 0, "y": 0}})
            self.assertEqual(proposal["action"], "walk")
            admission.assert_called_once_with()

    def test_admitted_completion_passes_through_one_http_request(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with (patch("ups_inference.UPSAdmission.admit"),
              patch("ups_inference.urllib.request.urlopen", return_value=response) as send):
            with guarded_urlopen(Mock(), timeout=20) as got:
                self.assertIs(got, response)
            send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
