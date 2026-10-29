"""Tests for the AI model diagnostics.

The tests use a **local HTTP server** on the loopback interface, so the
whole diagnostic path is exercised without a model server and without any
network access beyond the machine.

No credential is ever sent to the server in these tests, and the tests
prove that the diagnostic never exposes one.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import model_diagnostics as diagnostics  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    """A model endpoint that answers what the test asks for."""

    #: The routes the test server offers.
    models: tuple[str, ...] = ("frog-nano", "other-model")
    tool_calls = True
    inference_ok = True

    def log_message(self, *args):  # pragma: no cover - the server is quiet
        return

    def _send(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - the http.server API
        if self.path.endswith("/models"):
            self._send(200, {"data": [{"id": name}
                                      for name in self.models]})
            return
        self._send(200, {"object": "list"})

    def do_POST(self):  # noqa: N802 - the http.server API
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if "tools" in payload:
            if type(self).tool_calls:
                self._send(200, {"choices": [{"message": {
                    "tool_calls": [{"function": {"name": "report_status"}}]}}]})
            else:
                self._send(200, {"choices": [{"message": {"content": "no"}}]})
            return
        if type(self).inference_ok:
            self._send(200, {"choices": [{"message": {"content": "pong"}}]})
            return
        self._send(500, {"error": "failed"})


class DiagnosticsTestCase(unittest.TestCase):
    """A test with a local model endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        _Handler.models = ("frog-nano", "other-model")
        _Handler.tool_calls = True
        _Handler.inference_ok = True
        self.previous = os.environ.get("FACTORIO_LLM_API_KEY")
        os.environ.pop("FACTORIO_LLM_API_KEY", None)
        self.addCleanup(self._restore)

    def _restore(self):
        if self.previous is None:
            os.environ.pop("FACTORIO_LLM_API_KEY", None)
        else:
            os.environ["FACTORIO_LLM_API_KEY"] = self.previous


class EndpointTests(DiagnosticsTestCase):
    def test_a_reachable_endpoint_is_reported(self):
        reachable, detail = diagnostics.check_endpoint(self.endpoint)
        self.assertTrue(reachable)
        self.assertIn("HTTP", detail)

    def test_an_unreachable_endpoint_is_reported(self):
        reachable, detail = diagnostics.check_endpoint(
            "http://127.0.0.1:1/v1")
        self.assertFalse(reachable)
        self.assertIn("did not answer", detail)

    def test_a_remote_endpoint_is_refused(self):
        reachable, detail = diagnostics.check_endpoint(
            "https://api.example.com/v1")
        self.assertFalse(reachable)
        self.assertIn("loopback", detail)

    def test_an_endpoint_with_credentials_is_refused(self):
        reachable, detail = diagnostics.check_endpoint(
            "http://user:pass@127.0.0.1:8080/v1")
        self.assertFalse(reachable)
        self.assertIn("credentials", detail)

    def test_an_empty_endpoint_is_refused(self):
        reachable, detail = diagnostics.check_endpoint("")
        self.assertFalse(reachable)
        self.assertIn("empty", detail)


class DiscoveryTests(DiagnosticsTestCase):
    def test_the_models_are_discovered(self):
        models, detail = diagnostics.discover_models(self.endpoint)
        self.assertEqual(models, ("frog-nano", "other-model"))
        self.assertIn("2 model(s)", detail)

    def test_a_provider_without_a_model_list_is_not_an_error(self):
        models, detail = diagnostics.discover_models(
            "http://127.0.0.1:1/v1")
        self.assertEqual(models, ())
        self.assertIn("did not answer", detail)

    def test_a_remote_endpoint_lists_nothing(self):
        models, detail = diagnostics.discover_models(
            "https://api.example.com/v1")
        self.assertEqual(models, ())
        self.assertIn("loopback", detail)


class InferenceTests(DiagnosticsTestCase):
    def test_a_successful_inference_is_reported(self):
        ok, detail = diagnostics.test_inference(self.endpoint, "frog-nano")
        self.assertTrue(ok)
        self.assertIn("answered", detail)

    def test_a_failing_inference_is_reported(self):
        _Handler.inference_ok = False
        ok, detail = diagnostics.test_inference(self.endpoint, "frog-nano")
        self.assertFalse(ok)
        self.assertIn("HTTP", detail)

    def test_tool_calling_is_verified(self):
        ok, detail = diagnostics.test_tool_calling(self.endpoint, "frog-nano")
        self.assertTrue(ok)
        self.assertIn("tool call", detail)

    def test_a_model_without_tool_calling_is_reported(self):
        _Handler.tool_calls = False
        ok, detail = diagnostics.test_tool_calling(self.endpoint, "frog-nano")
        self.assertFalse(ok)
        self.assertIn("without a tool call", detail)


class DiagnoseTests(DiagnosticsTestCase):
    def test_a_capable_model_is_ready(self):
        status = diagnostics.diagnose(self.endpoint, "frog-nano")
        self.assertEqual(status.status, diagnostics.STATUS_READY)
        self.assertTrue(status.ready)
        self.assertTrue(status.endpoint_reachable)
        self.assertTrue(status.inference_succeeded)
        self.assertTrue(status.tool_calling_verified)
        self.assertTrue(status.compatible)
        self.assertEqual(status.models_discovered, ("frog-nano", "other-model"))

    def test_a_model_without_tool_calling_is_only_partially_verified(self):
        _Handler.tool_calls = False
        status = diagnostics.diagnose(self.endpoint, "frog-nano")
        self.assertEqual(status.status, diagnostics.STATUS_PARTIAL)
        self.assertFalse(status.ready)
        self.assertTrue(status.inference_succeeded)
        self.assertFalse(status.tool_calling_verified)
        self.assertFalse(status.compatible)

    def test_a_failing_inference_is_only_partially_verified(self):
        _Handler.inference_ok = False
        status = diagnostics.diagnose(self.endpoint, "frog-nano")
        self.assertEqual(status.status, diagnostics.STATUS_PARTIAL)
        self.assertFalse(status.inference_succeeded)

    def test_an_unreachable_endpoint_is_offline(self):
        status = diagnostics.diagnose("http://127.0.0.1:1/v1", "frog-nano")
        self.assertEqual(status.status, diagnostics.STATUS_OFFLINE)
        self.assertTrue(status.endpoint_checked)
        self.assertFalse(status.endpoint_reachable)
        self.assertFalse(status.inference_checked)

    def test_a_remote_endpoint_is_unsupported(self):
        status = diagnostics.diagnose("https://api.example.com/v1", "x")
        self.assertEqual(status.status, diagnostics.STATUS_UNSUPPORTED)
        self.assertFalse(status.endpoint_checked)

    def test_the_status_is_json_safe(self):
        status = diagnostics.diagnose(self.endpoint, "frog-nano")
        document = json.dumps(status.as_dict())
        self.assertIn("frog-nano", document)

    def test_the_unverified_steps_are_not_claimed(self):
        status = diagnostics.diagnose(
            self.endpoint, "frog-nano", check_inference=False,
            check_tools=False)
        self.assertFalse(status.inference_checked)
        self.assertFalse(status.tool_calling_checked)
        self.assertFalse(status.inference_succeeded)
        self.assertFalse(status.compatible)
        self.assertNotEqual(status.status, diagnostics.STATUS_READY)

    def test_the_problems_are_listed(self):
        _Handler.tool_calls = False
        status = diagnostics.diagnose(self.endpoint, "frog-nano")
        self.assertTrue(status.problems)


class CredentialTests(DiagnosticsTestCase):
    def test_a_missing_credential_is_reported(self):
        self.assertFalse(diagnostics.credential_present())
        status = diagnostics.diagnose(self.endpoint, "frog-nano")
        self.assertFalse(status.credential_present)

    def test_a_credential_is_never_exposed(self):
        os.environ["FACTORIO_LLM_API_KEY"] = "top-secret-key"
        self.assertTrue(diagnostics.credential_present())
        status = diagnostics.diagnose(self.endpoint, "frog-nano")
        document = json.dumps(status.as_dict())
        self.assertNotIn("top-secret-key", document)
        self.assertTrue(status.credential_present)

    def test_the_credential_is_only_in_the_header(self):
        os.environ["FACTORIO_LLM_API_KEY"] = "top-secret-key"
        headers = diagnostics._headers()
        self.assertIn("Authorization", headers)
        self.assertIn("top-secret-key", headers["Authorization"])
        self.assertNotIn("top-secret-key", headers.get("Content-Type", ""))


if __name__ == "__main__":
    unittest.main()
