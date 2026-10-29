"""Tests for the runtime settings bridge.

These tests prove that a stored setting becomes the value a service
actually uses, and that an unusable value falls back to the safe default
instead of breaking the service.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from runtime_settings import (  # noqa: E402
    DEFAULT_MODEL_ENDPOINT,
    PROVIDER_OLLAMA,
    cache_limits,
    history_retention,
    model_endpoint,
    model_name,
    model_runtime,
    observation_interval,
    observation_page_interval,
    observation_request_budget,
    request_timeout,
    runtime_report,
    telemetry_runtime,
)


def settings(**values):
    """Return a settings-like mapping with the given overrides."""
    base = {
        "llm_provider": "Local",
        "llm_endpoint": DEFAULT_MODEL_ENDPOINT,
        "llm_model": "",
        "llm_context_tokens": 8192,
        "llm_max_output_tokens": 2048,
        "llm_timeout_seconds": 120,
        "llm_max_parallel_requests": 1,
        "observation_interval_seconds": 20,
        "observation_page_interval_seconds": 120,
        "observation_max_requests": 4,
        "cache_max_entries": 512,
        "cache_ttl_seconds": 300,
        "history_retention_samples": 240,
    }
    base.update(values)
    return base


class ModelRuntimeTests(unittest.TestCase):
    def test_the_stored_endpoint_is_used(self):
        runtime = model_runtime(settings(llm_endpoint="http://127.0.0.1:9000/v1"))
        self.assertEqual(runtime.endpoint, "http://127.0.0.1:9000/v1")
        self.assertTrue(runtime.usable)

    def test_a_trailing_slash_is_removed(self):
        runtime = model_runtime(settings(llm_endpoint="http://127.0.0.1:9000/v1/"))
        self.assertEqual(runtime.endpoint, "http://127.0.0.1:9000/v1")

    def test_the_model_name_is_used(self):
        runtime = model_runtime(settings(llm_model="FrogNano-1B"))
        self.assertEqual(runtime.model, "FrogNano-1B")

    def test_a_frog_model_is_not_the_only_option(self):
        runtime = model_runtime(settings(llm_model="some-other-model"))
        self.assertEqual(runtime.model, "some-other-model")

    def test_a_remote_endpoint_is_refused(self):
        runtime = model_runtime(settings(llm_endpoint="https://api.example.com/v1"))
        self.assertIsNotNone(runtime.problem)
        self.assertFalse(runtime.usable)
        self.assertEqual(runtime.endpoint, DEFAULT_MODEL_ENDPOINT)

    def test_an_endpoint_with_credentials_is_refused(self):
        runtime = model_runtime(
            settings(llm_endpoint="http://user:pass@127.0.0.1:8080/v1"))
        self.assertIsNotNone(runtime.problem)

    def test_an_endpoint_with_a_query_is_refused(self):
        runtime = model_runtime(
            settings(llm_endpoint="http://127.0.0.1:8080/v1?key=secret"))
        self.assertIsNotNone(runtime.problem)

    def test_an_empty_endpoint_falls_back(self):
        runtime = model_runtime(settings(llm_endpoint=""))
        self.assertEqual(runtime.endpoint, DEFAULT_MODEL_ENDPOINT)

    def test_the_provider_is_used(self):
        runtime = model_runtime(settings(llm_provider=PROVIDER_OLLAMA))
        self.assertEqual(runtime.provider, PROVIDER_OLLAMA)

    def test_an_unknown_provider_falls_back_to_local(self):
        runtime = model_runtime(settings(llm_provider="Mystery"))
        self.assertEqual(runtime.provider, "Local")

    def test_the_limits_are_used(self):
        runtime = model_runtime(
            settings(llm_context_tokens=32768, llm_max_output_tokens=4096,
                     llm_timeout_seconds=45, llm_max_parallel_requests=3))
        self.assertEqual(runtime.context_tokens, 32768)
        self.assertEqual(runtime.max_output_tokens, 4096)
        self.assertEqual(runtime.timeout_seconds, 45)
        self.assertEqual(runtime.max_parallel_requests, 3)

    def test_a_zero_timeout_is_clamped_to_the_safe_minimum(self):
        runtime = model_runtime(settings(llm_timeout_seconds=0))
        self.assertEqual(runtime.timeout_seconds, 5)

    def test_an_enormous_timeout_is_clamped(self):
        runtime = model_runtime(settings(llm_timeout_seconds=10 ** 9))
        self.assertEqual(runtime.timeout_seconds, 3600)

    def test_a_zero_parallel_limit_is_clamped_to_one(self):
        runtime = model_runtime(settings(llm_max_parallel_requests=0))
        self.assertEqual(runtime.max_parallel_requests, 1)

    def test_the_report_never_contains_a_credential(self):
        os.environ["FACTORIO_LLM_API_KEY"] = "super-secret"
        try:
            report = runtime_report(settings())
        finally:
            os.environ.pop("FACTORIO_LLM_API_KEY", None)
        self.assertNotIn("super-secret", str(report))
        self.assertTrue(report["model"]["credential_present"])

    def test_a_broken_settings_object_falls_back(self):
        runtime = model_runtime(object())
        self.assertEqual(runtime.endpoint, DEFAULT_MODEL_ENDPOINT)


class TelemetryRuntimeTests(unittest.TestCase):
    def test_the_observation_interval_is_used(self):
        runtime = telemetry_runtime(settings(observation_interval_seconds=45))
        self.assertEqual(runtime.observation_interval_seconds, 45)

    def test_the_page_interval_is_used(self):
        runtime = telemetry_runtime(
            settings(observation_page_interval_seconds=300))
        self.assertEqual(runtime.page_interval_seconds, 300)

    def test_the_request_budget_is_used(self):
        runtime = telemetry_runtime(settings(observation_max_requests=9))
        self.assertEqual(runtime.request_budget, 9)

    def test_the_cache_limits_are_used(self):
        runtime = telemetry_runtime(
            settings(cache_max_entries=128, cache_ttl_seconds=60))
        self.assertEqual(runtime.cache_max_entries, 128)
        self.assertEqual(runtime.cache_ttl_seconds, 60)

    def test_the_history_retention_is_used(self):
        runtime = telemetry_runtime(settings(history_retention_samples=600))
        self.assertEqual(runtime.history_retention_samples, 600)

    def test_a_zero_interval_is_clamped(self):
        runtime = telemetry_runtime(settings(observation_interval_seconds=0))
        self.assertEqual(runtime.observation_interval_seconds, 1)

    def test_a_zero_request_budget_is_clamped_to_one(self):
        runtime = telemetry_runtime(settings(observation_max_requests=0))
        self.assertEqual(runtime.request_budget, 1)

    def test_a_tiny_cache_is_clamped(self):
        runtime = telemetry_runtime(settings(cache_max_entries=1))
        self.assertEqual(runtime.cache_max_entries, 16)

    def test_a_broken_settings_object_falls_back(self):
        runtime = telemetry_runtime(object())
        self.assertEqual(runtime.observation_interval_seconds, 20)


class AccessorTests(unittest.TestCase):
    def test_the_accessors_return_the_configured_values(self):
        values = settings(llm_endpoint="http://127.0.0.1:9100/v1",
                          llm_model="m", llm_timeout_seconds=30,
                          observation_interval_seconds=15,
                          observation_page_interval_seconds=60,
                          observation_max_requests=2,
                          cache_max_entries=64, cache_ttl_seconds=90,
                          history_retention_samples=100)
        self.assertEqual(model_endpoint(values), "http://127.0.0.1:9100/v1")
        self.assertEqual(model_name(values), "m")
        self.assertEqual(request_timeout(values), 30.0)
        self.assertEqual(observation_interval(values), 15.0)
        self.assertEqual(observation_page_interval(values), 60.0)
        self.assertEqual(observation_request_budget(values), 2)
        self.assertEqual(cache_limits(values), (64, 90.0))
        self.assertEqual(history_retention(values), 100)

    def test_the_accessors_never_freeze_at_import_time(self):
        """The endpoint must be read at the call, not once at import."""
        first = model_endpoint(settings(llm_endpoint="http://127.0.0.1:9001/v1"))
        second = model_endpoint(settings(llm_endpoint="http://127.0.0.1:9002/v1"))
        self.assertNotEqual(first, second)
        self.assertEqual(second, "http://127.0.0.1:9002/v1")


if __name__ == "__main__":
    unittest.main()
