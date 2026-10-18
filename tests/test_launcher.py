import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from app_runtime import component_command
from launcher_services import Profile, Supervisor


class LauncherTests(unittest.TestCase):
    def test_real_child_crash_is_reported_before_readiness_timeout(self):
        s = Supervisor(self.profile())
        p = subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(9)"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        s.owned["fixture"] = p
        try:
            with self.assertRaisesRegex(RuntimeError, "fixture exited"):
                s.wait(lambda: False, 5, "fixture")
        finally:
            p.wait(5)

    def test_cancellation_interrupts_real_readiness_wait(self):
        s = Supervisor(self.profile())
        timer = threading.Timer(0.1, s.cancel.set)
        timer.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "Startup cancelled"):
                s.wait(lambda: False, 5, "fixture")
        finally:
            timer.join()
        self.assertFalse(s.started)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.r = Path(self.tmp.name)
        save = self.r / "data/saves/test.zip"
        save.parent.mkdir(parents=True)
        with zipfile.ZipFile(save, "w") as z:
            z.writestr("test/level.dat", b"fixture")
        ini = self.r / "host.ini"
        ini.write_text(
            "[path]\nwrite-data="
            + str(save.parent.parent)
            + "\n[other]\nlocal-rcon-socket=127.0.0.1:27108\nlocal-rcon-password=fixture-only\n"
        )
        exe = self.r / "fake.exe"
        exe.touch()
        mods = self.r / "mods"
        mods.mkdir()
        settings = self.r / "settings.json"
        settings.write_text(json.dumps({"visibility": {"public": False, "lan": False}}))
        secret = self.r / "secret.json"
        secret.write_text(json.dumps({"rcon_password": "fixture-only"}))
        self.d = dict(
            llama_exe=str(exe),
            model_file=str(exe),
            factorio_exe=str(exe),
            client_exe=str(exe),
            server_config=str(ini),
            server_mods=str(mods),
            server_settings=str(settings),
            save_path=str(save),
            client_config=str(ini),
            client_mods=str(mods),
            mcp_server_dll=str(exe),
            profile_root=str(self.r),
            game_port=34208,
            rcon_port=27108,
            llm_port=8082,
            world_id="test",
            secret_file=str(secret),
            test_profile=True,
            game_mode="graphical-host",
        )
        self.path = self.r / "profile.json"

    def profile(self):
        self.path.write_text(json.dumps(self.d))
        return Profile(self.path)

    def test_valid_isolated_host(self):
        self.assertEqual(self.profile().data["game_mode"], "graphical-host")

    def test_profile_must_be_explicit_test(self):
        self.d["test_profile"] = False
        with self.assertRaises(ValueError):
            self.profile()

    def test_paths_cannot_escape_root(self):
        self.d["profile_root"] = str(self.r / "mods")
        with self.assertRaises(ValueError):
            self.profile()

    def test_private_host_required(self):
        Path(self.d["server_settings"]).write_text(
            json.dumps({"visibility": {"public": True, "lan": False}})
        )
        with self.assertRaises(ValueError):
            self.profile()

    def test_corrupt_save_denied(self):
        Path(self.d["save_path"]).write_bytes(b"bad")
        with self.assertRaises(zipfile.BadZipFile):
            self.profile()

    def test_remote_rcon_host_denied(self):
        p = Path(self.d["client_config"])
        p.write_text(p.read_text().replace("127.0.0.1:27108", "0.0.0.0:27108"))
        with self.assertRaises(ValueError):
            self.profile()

    def test_mismatched_secret_denied(self):
        p = Path(self.d["secret_file"])
        p.write_text(json.dumps({"rcon_password": "wrong"}))
        with self.assertRaises(ValueError):
            self.profile()

    def test_same_ports_denied(self):
        self.d["llm_port"] = 27108
        with self.assertRaises(ValueError):
            self.profile()

    def test_stop_never_terminates_attached_game_or_model(self):
        s = Supervisor(self.profile())
        a = Mock()
        s.attached = {"host": a, "llama": a}
        s.stop_owned(include_game=True)
        a.terminate.assert_not_called()
        a.kill.assert_not_called()

    def test_failed_save_keeps_owned_game_running(self):
        s = Supervisor(self.profile())
        p = Mock()
        p.poll.return_value = None
        s.owned["host"] = p
        with patch.object(s, "save_owned_game", side_effect=RuntimeError("not saved")):
            with self.assertRaises(RuntimeError):
                s.stop_owned(include_game=True)
        p.terminate.assert_not_called()

    def test_startup_cancellation_is_immediate(self):
        s = Supervisor(self.profile())
        s.cancel.set()
        with self.assertRaises(RuntimeError):
            s.wait(lambda: True, 5, "host")

    def test_queued_start_cannot_clear_emergency_cancel(self):
        s = Supervisor(self.profile())
        s.cancel.set()
        with patch.object(s, "acquire"), patch.object(s, "spawn") as spawn:
            with self.assertRaises(RuntimeError):
                s.start_all()
        spawn.assert_not_called()

    def test_frozen_workers_keep_console_pipe_entrypoint(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(self.r / "AutoEngineer.exe")),
        ):
            c = component_command("supervised_agent")
            self.assertEqual(Path(c[0]).name, "AutoEngineerWorker.exe")
            self.assertEqual(c[1:], ["--component", "supervised_agent"])

    def test_listener_collision_detected_without_connect_timeout(self):
        import socket

        s = Supervisor(self.profile())
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertTrue(s.port_open(port))
        self.assertFalse(s.port_open(port))

    def test_unknown_component_denied(self):
        with self.assertRaises(ValueError):
            component_command("shell")

    @unittest.skipUnless(os.name == "nt", "Windows profile locking")
    def test_duplicate_launcher_profile_lock(self):
        p = self.profile()
        a = Supervisor(p)
        b = Supervisor(p)
        try:
            a.acquire()
            with self.assertRaises(RuntimeError):
                b.acquire()
        finally:
            a.release()
            b.release()

    def test_model_loss_cancels_dashboard_without_killing_game(self):
        s = Supervisor(self.profile())
        s.started = True
        game = Mock()
        s.attached["host"] = game
        with (
            patch.object(s, "game", return_value={"players": 1, "character": True}),
            patch.object(s, "models", side_effect=OSError()),
            patch.object(s, "request_dashboard_stop") as stop,
        ):
            s.refresh_health()
        stop.assert_called_once()
        self.assertTrue(s.cancel.is_set())
        self.assertFalse(s.started)
        game.terminate.assert_not_called()

    def test_game_loss_cancels_and_does_not_auto_restart(self):
        s = Supervisor(self.profile())
        s.started = True
        with (
            patch.object(s, "game", side_effect=OSError()),
            patch.object(s, "models", return_value="local"),
            patch.object(s, "request_dashboard_stop") as stop,
            patch.object(s, "spawn") as spawn,
        ):
            s.refresh_health()
            s.refresh_health()
        stop.assert_called_once()
        spawn.assert_not_called()
        self.assertFalse(s.started)
