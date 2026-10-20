"""Offline configuration tests; no backend, network, model, or game access."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import autoengineer_config as config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.root_patch = patch.object(config, "PROJECT_ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def write_config(self, text, name="config.local.json"):
        (self.root / name).write_text(text, encoding="utf-8")

    def test_missing_password_fails_before_backend_resolution(self):
        with patch.object(config.shutil, "which") as resolve:
            with self.assertRaisesRegex(ValueError, "FACTORIO_RCON_PASSWORD"):
                config.mcp_parameters()
            resolve.assert_not_called()

    def test_blank_password_is_rejected(self):
        os.environ["FACTORIO_RCON_PASSWORD"] = "   "
        with self.assertRaises(ValueError):
            config.mcp_parameters()

    def test_credentials_cannot_be_put_in_json(self):
        self.write_config('{"password": "fake-test-value"}')
        with self.assertRaises(ValueError):
            config.get_settings()

    def test_bad_ports_are_rejected(self):
        for value in ("true", "0", "65536", '"27015"'):
            with self.subTest(value=value):
                self.write_config('{"rcon_port": ' + value + "}")
                with self.assertRaises(ValueError):
                    config.get_settings()

    def test_url_credentials_are_rejected_without_echo(self):
        self.write_config('{"llm_api_url":"http://user:fake-test-value@localhost/v1"}')
        with self.assertRaises(ValueError) as caught:
            config.get_settings()
        self.assertNotIn("fake-test-value", str(caught.exception))

    def test_invalid_json_is_not_echoed(self):
        self.write_config('{"password": "fake-test-value",')
        with self.assertRaises(ValueError) as caught:
            config.get_settings()
        self.assertNotIn("fake-test-value", str(caught.exception))

    def test_relative_config_and_dll_resolve_from_project(self):
        self.write_config(
            '{"mcp_server_dll":"backend/server.dll", "rcon_port":28000}', "custom.json"
        )
        os.environ["AUTOENGINEER_CONFIG"] = "custom.json"
        os.environ["FACTORIO_RCON_PASSWORD"] = "fake-test-value"
        dll = self.root / "backend/server.dll"
        dll.parent.mkdir()
        dll.write_bytes(b"")
        fake_mcp = SimpleNamespace(StdioServerParameters=lambda **kwargs: SimpleNamespace(**kwargs))
        with (
            patch.dict(sys.modules, {"mcp": fake_mcp}),
            patch.object(config.shutil, "which", return_value="dotnet"),
        ):
            params = config.mcp_parameters()
        self.assertEqual(params.args, [str(dll.resolve())])
        assert params.env is not None
        self.assertEqual(params.env["FACTORIO_RCON_PASSWORD"], "fake-test-value")
        self.assertEqual(params.env["FACTORIO_RCON_PORT"], "28000")

    def test_missing_backend_is_rejected(self):
        os.environ["FACTORIO_RCON_PASSWORD"] = "fake-test-value"
        with self.assertRaises(FileNotFoundError):
            config.mcp_parameters()

    def test_missing_dotnet_is_rejected(self):
        self.write_config('{"mcp_server_dll":"server.dll"}')
        (self.root / "server.dll").write_bytes(b"")
        os.environ["FACTORIO_RCON_PASSWORD"] = "fake-test-value"
        with patch.object(config.shutil, "which", return_value=None):
            with self.assertRaises(FileNotFoundError):
                config.mcp_parameters()


if __name__ == "__main__":
    unittest.main()
