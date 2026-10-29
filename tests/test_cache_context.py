"""Tests for the cache context and the configurable cache limits.

The context is what decides whether a cached entry may be served. The
tests use **synthetic** profiles: they are fixtures, not vanilla or
Pyanodons data.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from cache_context import (  # noqa: E402
    DEFAULT_MAX_ENTRIES,
    DEFAULT_TTL_SECONDS,
    CacheContext,
    bounded_entries,
    bounded_ttl,
    current_context,
    limits,
)


class FakeProfile:
    """A stand-in for a stored profile."""

    def __init__(self, identifier="p1", version="2.1.23", fingerprint="abc"):
        self.identifier = identifier
        self.game_version = version
        self.fingerprint = fingerprint


class FakeManager:
    """A stand-in for the profile manager."""

    def __init__(self, profile=None, selected: str | None = "p1"):
        self._profile = profile
        self.selected = selected

    def load(self, identifier):
        if self._profile is None:
            raise ValueError("no profile")
        return self._profile


class ContextIdentityTests(unittest.TestCase):
    def test_two_identical_contexts_match(self):
        first = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        second = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        self.assertTrue(first.matches(second))

    def test_a_different_profile_does_not_match(self):
        first = CacheContext("p1", "2.1.23", "fp", "nauvis", "f")
        second = CacheContext("p2", "2.1.23", "fp", "nauvis", "f")
        self.assertFalse(first.matches(second))

    def test_a_different_mod_fingerprint_does_not_match(self):
        first = CacheContext("p", "2.1.23", "fp1", "nauvis", "f")
        second = CacheContext("p", "2.1.23", "fp2", "nauvis", "f")
        self.assertFalse(first.matches(second))

    def test_a_different_game_version_does_not_match(self):
        first = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        second = CacheContext("p", "2.1.22", "fp", "nauvis", "f")
        self.assertFalse(first.matches(second))

    def test_a_different_surface_does_not_match(self):
        first = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        second = CacheContext("p", "2.1.23", "fp", "vulcanus", "f")
        self.assertFalse(first.matches(second))

    def test_a_different_force_does_not_match(self):
        first = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        second = CacheContext("p", "2.1.23", "fp", "nauvis", "g")
        self.assertFalse(first.matches(second))

    def test_an_empty_context_never_matches(self):
        empty = CacheContext()
        other = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        self.assertFalse(empty.matches(other))
        self.assertFalse(other.matches(empty))

    def test_the_surface_can_be_replaced(self):
        context = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        other = context.with_surface("vulcanus")
        self.assertEqual(other.surface, "vulcanus")
        self.assertEqual(other.profile, "p")
        self.assertFalse(context.matches(other))

    def test_the_force_can_be_replaced(self):
        context = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        other = context.with_force("g")
        self.assertEqual(other.force, "g")
        self.assertFalse(context.matches(other))

    def test_the_key_is_stable(self):
        first = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        second = CacheContext("p", "2.1.23", "fp", "nauvis", "f")
        self.assertEqual(first.key, second.key)

    def test_the_description_hides_the_whole_fingerprint(self):
        context = CacheContext("p", "2.1.23", "x" * 64, "nauvis", "f")
        self.assertEqual(len(context.as_dict()["mod_fingerprint"]), 16)


class ContextFromProfileTests(unittest.TestCase):
    def test_a_profile_provides_the_identity(self):
        context = CacheContext.from_profile(FakeProfile())
        self.assertEqual(context.profile, "p1")
        self.assertEqual(context.game_version, "2.1.23")
        self.assertEqual(context.mod_fingerprint, "abc")

    def test_a_profile_without_a_fingerprint_still_has_an_identity(self):
        class _NoFingerprint:
            identifier = "p1"
            game_version = "2.1.23"

        context = CacheContext.from_profile(_NoFingerprint())
        self.assertEqual(context.profile, "p1")
        self.assertEqual(context.mod_fingerprint, "")

    def test_the_current_context_follows_the_selection(self):
        manager = FakeManager(FakeProfile())
        context = current_context(manager, surface="nauvis")
        self.assertEqual(context.profile, "p1")
        self.assertEqual(context.surface, "nauvis")

    def test_the_current_context_is_empty_without_a_selection(self):
        manager = FakeManager(FakeProfile(), selected=None)
        self.assertTrue(current_context(manager).empty)

    def test_the_current_context_survives_an_unreadable_profile(self):
        manager = FakeManager(None)
        self.assertTrue(current_context(manager).empty)


class CacheLimitTests(unittest.TestCase):
    def test_the_default_limit_is_used_when_the_value_is_missing(self):
        self.assertEqual(bounded_entries(None), DEFAULT_MAX_ENTRIES)

    def test_a_limit_below_the_minimum_is_raised(self):
        self.assertEqual(bounded_entries(1), 16)

    def test_a_limit_above_the_maximum_is_lowered(self):
        self.assertEqual(bounded_entries(10 ** 9), 65536)

    def test_a_valid_limit_is_kept(self):
        self.assertEqual(bounded_entries(256), 256)

    def test_a_non_integer_limit_is_refused(self):
        self.assertEqual(bounded_entries("many"), DEFAULT_MAX_ENTRIES)

    def test_the_ttl_is_bounded(self):
        self.assertEqual(bounded_ttl(0), 1)
        self.assertEqual(bounded_ttl(10 ** 9), 86400)
        self.assertEqual(bounded_ttl(60), 60)

    def test_the_limits_come_from_the_settings(self):
        class _Settings:
            def get(self, name):
                return {"cache_max_entries": 128,
                        "cache_ttl_seconds": 45}.get(name)

        self.assertEqual(limits(_Settings()), (128, 45))

    def test_the_limits_fall_back_without_the_settings(self):
        self.assertEqual(limits(object()),
                         (DEFAULT_MAX_ENTRIES, DEFAULT_TTL_SECONDS))


if __name__ == "__main__":
    unittest.main()
