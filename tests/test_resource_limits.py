"""Tests for the inference concurrency and the resource limits.

The concurrency limit must be honoured, and the resource limits must say
plainly which of them are enforced and which are advisory.
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

import ups_inference  # noqa: E402
from resource_limits import (  # noqa: E402
    CPU_ENFORCEMENT,
    MEMORY_ENFORCEMENT,
    budget_entries,
    resource_limits,
)


class _Settings:
    """A settings-like mapping."""

    def __init__(self, **values):
        self.values = values

    def get(self, name):
        return self.values.get(name)


class InferenceConcurrencyTests(unittest.TestCase):
    """The model request concurrency comes from the settings."""

    def setUp(self):
        ups_inference._model_slots.clear()

    def test_the_default_limit_is_one(self):
        self.assertEqual(ups_inference.inference_concurrency(), 1)

    def test_the_configured_limit_is_used(self):
        original = ups_inference.inference_concurrency
        ups_inference.inference_concurrency = lambda: 3
        try:
            self.assertEqual(ups_inference._model_semaphore()._value, 3)
        finally:
            ups_inference.inference_concurrency = original

    def test_the_semaphore_is_reused_for_the_same_limit(self):
        first = ups_inference._model_semaphore()
        second = ups_inference._model_semaphore()
        self.assertIs(first, second)

    def test_a_nonsense_limit_falls_back_to_one(self):
        original = ups_inference.inference_concurrency
        ups_inference.inference_concurrency = lambda: 0
        try:
            semaphore = ups_inference._model_semaphore()
            self.assertEqual(semaphore._value, 1)
        finally:
            ups_inference.inference_concurrency = original

    def test_the_limit_bounds_the_simultaneous_requests(self):
        ups_inference._model_slots.clear()
        semaphore = threading.Semaphore(2)
        ups_inference._model_slots[2] = semaphore
        entered = []
        released = threading.Event()

        def worker():
            with semaphore:
                entered.append(1)
                released.wait(2)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        time.sleep(0.1)
        # Only the configured number of requests may be inside the slot.
        self.assertLessEqual(len(entered), 2)
        released.set()
        for thread in threads:
            thread.join(timeout=3)
        # The slots are released again, so the next test starts clean.
        ups_inference._model_slots.clear()


class ResourceLimitTests(unittest.TestCase):
    """The limits are bounded and their enforcement is honest."""

    def test_the_default_limits_are_used(self):
        limits = resource_limits(object())
        self.assertGreaterEqual(limits.cpu_percent, 1)
        self.assertGreaterEqual(limits.memory_mb, 128)

    def test_the_configured_limits_are_used(self):
        limits = resource_limits(
            _Settings(max_ai_cpu_percent=25, max_ai_memory_mb=2048))
        self.assertEqual(limits.cpu_percent, 25)
        self.assertEqual(limits.memory_mb, 2048)

    def test_a_zero_cpu_limit_is_clamped(self):
        limits = resource_limits(_Settings(max_ai_cpu_percent=0))
        self.assertEqual(limits.cpu_percent, 1)

    def test_an_enormous_cpu_limit_is_clamped(self):
        limits = resource_limits(_Settings(max_ai_cpu_percent=10 ** 6))
        self.assertEqual(limits.cpu_percent, 100)

    def test_a_tiny_memory_limit_is_clamped(self):
        limits = resource_limits(_Settings(max_ai_memory_mb=1))
        self.assertEqual(limits.memory_mb, 128)

    def test_the_memory_limit_is_advisory(self):
        limits = resource_limits(object())
        self.assertTrue(limits.memory_is_advisory)
        self.assertEqual(limits.memory_enforcement, MEMORY_ENFORCEMENT)

    def test_the_cpu_limit_is_enforced_as_a_priority(self):
        limits = resource_limits(object())
        self.assertFalse(limits.cpu_is_advisory)
        self.assertEqual(limits.cpu_enforcement, CPU_ENFORCEMENT)

    def test_the_description_says_what_is_advisory(self):
        description = resource_limits(object()).describe()
        self.assertTrue(description["memory_is_advisory"])
        self.assertIn("advisory", description["note"])

    def test_the_summary_names_the_enforcement(self):
        summary = resource_limits(object()).summary()
        self.assertIn("advisory", summary)
        self.assertIn("priority", summary)

    def test_the_budget_limits_the_cache_entries(self):
        entries = budget_entries(4096)
        self.assertGreater(entries, 0)
        self.assertLess(entries, budget_entries(8192))

    def test_a_zero_budget_yields_nothing(self):
        self.assertEqual(budget_entries(0), 0)


if __name__ == "__main__":
    unittest.main()
