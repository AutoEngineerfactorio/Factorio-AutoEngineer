"""Observer bursts must not redraw every intermediate Tk frame."""
import io
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import autoengineer_dashboard as dashboard
from autoengineer_dashboard import Dashboard
from dashboard_feed import PREFIX


class Stub:
    process_events = Dashboard.process_events
    read_output = Dashboard.read_output

    def __init__(self):
        self.observer = object()
        self.proc = None
        self.q = queue.Queue()
        self.root = Mock()
        self.display_frame = Mock()
        self.live_view = Mock()
        self.append = Mock()


class ObserverEnvironmentTests(unittest.TestCase):
    def test_uses_isolated_profile_without_storing_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / '.local/launcher-profiles/2.1.23/config.ini'
            backend = root / '.local/live-pillow-2.1.23/backend-patched-2.1.23/FactorioMCP.dll'
            profile.parent.mkdir(parents=True)
            backend.parent.mkdir(parents=True)
            profile.write_text('local-rcon-socket=127.0.0.1:27015\nlocal-rcon-password=test-only-secret\n')
            backend.write_bytes(b'dummy')
            with patch.object(dashboard, 'AGENT', root / 'agent/supervised_agent.py'):
                env = dashboard.isolated_observer_environment()
            self.assertEqual(env['FACTORIO_RCON_PASSWORD'], 'test-only-secret')
            self.assertEqual(env['AUTOENGINEER_MODE'], 'helper')
            self.assertNotIn('test-only-secret', Path(env['AUTOENGINEER_CONFIG']).read_text())


class PerformanceModeTests(unittest.TestCase):
    def test_default_mode_does_not_spawn_expensive_observer(self):
        app = Mock()
        app.closing = False
        app.observer = None
        with patch.dict('os.environ', {'AUTOENGINEER_ENABLE_LIVE_MAP': '0'}), patch.object(
            dashboard, 'isolated_observer_environment', return_value={}
        ), patch.object(dashboard.subprocess, 'Popen') as start, patch.object(
            dashboard, 'component_command', return_value=['telemetry']
        ):
            dashboard.Dashboard.start_observer(app)
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0], ['telemetry'])


class MapFreeTelemetryDispatchTests(unittest.TestCase):
    def test_valid_map_free_frame_reaches_telemetry_without_map(self):
        from production_telemetry import validate_telemetry

        app = Mock()
        raw = {"schema": 1, "telemetry_only": True, "status": "ok", "tick": 42,
               "surface": "nauvis", "x": 1.25, "y": -3.5,
               "sampled_item_flow": [{"name": "iron-plate", "input": 2.0, "output": 3.0}],
               "telemetry": validate_telemetry(None, 42)}
        dashboard.Dashboard.display_frame(app, PREFIX + __import__('json').dumps(raw))
        app.telemetry_view.update_frame.assert_called_once()
        sent = app.telemetry_view.update_frame.call_args.args[0]
        self.assertEqual(sent["sampled_item_flow"][0]["name"], "iron-plate")
        app.live_view.update_frame.assert_called_once_with(
            {"status": "ok", "surface": "nauvis", "tick": 42})
        app.position.set.assert_called_once_with("1.25, -3.50")
        app.live_view.request_viewport.assert_not_called()

    def test_invalid_samples_do_not_reach_view(self):
        from production_telemetry import validate_telemetry

        app = Mock()
        raw = {"schema": 1, "telemetry_only": True, "status": "ok", "tick": 42,
               "sampled_item_flow": [{"name": "unsafe", "input": -3.0, "output": 1.0}],
               "telemetry": validate_telemetry(None, 42)}
        dashboard.Dashboard.display_frame(app, PREFIX + __import__('json').dumps(raw))
        app.telemetry_view.update_frame.assert_called_once_with({"status": "unavailable"})


class ReaderTests(unittest.TestCase):
    def test_multimegabyte_observer_line_is_not_split(self):
        app = Stub()
        payload = PREFIX + '{"schema":1,"status":"unavailable"}' + " " * 1100000 + "\n"
        proc = Mock(stdout=io.StringIO(payload))
        app.observer = proc
        app.read_output(proc)
        first = app.q.get_nowait()
        self.assertEqual(first, (proc, "line", payload))
        self.assertEqual(app.q.get_nowait()[1], "exit")
        self.assertTrue(app.q.empty())

    def test_oversize_observation_is_dropped_as_single_line(self):
        app = Stub()
        line = PREFIX + "x" * (4 * 1048576) + "\n"
        proc = Mock(stdout=io.StringIO(line + "after\n"))
        app.observer = proc
        app.read_output(proc)
        self.assertIn("exceeds", app.q.get_nowait()[2])
        self.assertEqual(app.q.get_nowait(), (proc, "line", "after\n"))


class CoalescingTests(unittest.TestCase):
    def test_only_latest_observation_is_rendered(self):
        app = Stub()
        for n in range(30):
            app.q.put((app.observer, "line", PREFIX + str(n)))
        app.process_events()
        app.display_frame.assert_called_once_with(PREFIX + "29")
        app.root.after.assert_called_once_with(80, app.process_events)

    def test_non_frame_observer_output_is_not_dropped(self):
        app = Stub()
        app.q.put((app.observer, "line", "observer diagnostic"))
        app.q.put((app.observer, "line", PREFIX + "valid"))
        app.process_events()
        app.append.assert_called_once_with("observer diagnostic")
        app.display_frame.assert_called_once_with(PREFIX + "valid")


if __name__ == "__main__":
    unittest.main()
