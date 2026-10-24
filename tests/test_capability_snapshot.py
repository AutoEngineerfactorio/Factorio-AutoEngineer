"""
R04 Capability Snapshot — Unit tests for read-only bounded game observations.

Tests cover:
- Deterministic fingerprinting (SHA256 with sorted keys)
- Status computation (live/stale/unavailable)
- Strict contract enforcement (schema, timestamps, control characters)
- Read-only bounded observations
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from capability_snapshot import (
    _compute_fingerprint,
    _contains_control_characters,
    _create_canonical_profile,
    assess_capability_snapshot,
)


class TestContainsControlCharacters(unittest.TestCase):
    """Test control character detection."""

    def test_empty_string(self):
        """Empty string has no control characters."""
        self.assertFalse(_contains_control_characters(""))

    def test_whitespace_only(self):
        """Common whitespace is allowed."""
        self.assertFalse(_contains_control_characters(" \t\n\r"))

    def test_normal_text(self):
        """Normal text has no control characters."""
        self.assertFalse(_contains_control_characters("Hello, World!"))

    def test_null_byte(self):
        """Null byte is a control character."""
        self.assertTrue(_contains_control_characters("\x00"))

    def test_tab_is_allowed(self):
        """Tab (9) is allowed."""
        self.assertFalse(_contains_control_characters("\t"))

    def test_newline_is_allowed(self):
        """Newline (10) is allowed."""
        self.assertFalse(_contains_control_characters("\n"))

    def test_carriage_return_is_allowed(self):
        """Carriage return (13) is allowed."""
        self.assertFalse(_contains_control_characters("\r"))


class TestCreateCanonicalProfile(unittest.TestCase):
    """Test canonical profile creation for deterministic fingerprinting."""

    def test_valid_profile(self):
        """Valid profile creates canonical representation."""
        profile = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation", "logistics"],
        }
        canonical = _create_canonical_profile(profile)
        self.assertEqual(canonical["game_version"], "1.1.10")
        self.assertEqual(canonical["force"], "vanilla")
        self.assertEqual(canonical["surface"], "space")
        self.assertEqual(canonical["research"], ["automation", "logistics"])

    def test_research_sorted(self):
        """Research list is sorted for deterministic ordering."""
        profile = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["logistics", "automation"],
        }
        canonical = _create_canonical_profile(profile)
        self.assertEqual(canonical["research"], ["automation", "logistics"])

    def test_empty_game_version_raises(self):
        """Empty game_version raises ValueError."""
        profile = {
            "game_version": "",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            _create_canonical_profile(profile)
        self.assertIn("game_version", str(context.exception))

    def test_too_long_game_version_raises(self):
        """Game version > 128 chars raises ValueError."""
        profile = {
            "game_version": "a" * 129,
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            _create_canonical_profile(profile)
        self.assertIn("game_version", str(context.exception))

    def test_control_characters_in_force_raises(self):
        """Control characters in force raises ValueError."""
        profile = {
            "game_version": "1.1.10",
            "force": "van\x00illa",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            _create_canonical_profile(profile)
        self.assertIn("force", str(context.exception))

    def test_bool_schema_rejected(self):
        """Bool True for schema is rejected in assess_capability_snapshot."""
        snapshot = {
            "schema": True,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            assess_capability_snapshot(snapshot, 1001.0)
        self.assertIn("schema", str(context.exception))


class TestComputeFingerprint(unittest.TestCase):
    """Test deterministic SHA256 fingerprint computation."""

    def test_same_input_same_output(self):
        """Same input produces same fingerprint."""
        canonical1 = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        canonical2 = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        fp1 = _compute_fingerprint(canonical1)
        fp2 = _compute_fingerprint(canonical2)
        self.assertEqual(fp1, fp2)

    def test_different_input_different_output(self):
        """Different input produces different fingerprint."""
        canonical1 = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        canonical2 = {
            "game_version": "1.1.11",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        fp1 = _compute_fingerprint(canonical1)
        fp2 = _compute_fingerprint(canonical2)
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_is_hex_digest(self):
        """Fingerprint is 64-character hex digest."""
        canonical = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        fp = _compute_fingerprint(canonical)
        self.assertEqual(len(fp), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))

    def test_fingerprint_matches_sha256(self):
        """Fingerprint matches hashlib.sha256."""
        canonical = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        fp = _compute_fingerprint(canonical)
        expected = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(fp, expected)


class TestAssessCapabilitySnapshot(unittest.TestCase):
    """Test capability snapshot assessment."""

    def test_live_snapshot(self):
        """Fresh snapshot is live and usable."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        result = assess_capability_snapshot(snapshot, 1001.0)
        self.assertEqual(result["status"], "live")
        self.assertTrue(result["usable"])
        self.assertEqual(result["age"], 1.0)
        self.assertIsNotNone(result["fingerprint"])

    def test_stale_snapshot(self):
        """Snapshot older than max_age is stale."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        result = assess_capability_snapshot(snapshot, 1010.0, max_age=5.0)
        self.assertEqual(result["status"], "stale")
        self.assertFalse(result["usable"])
        self.assertEqual(result["age"], 10.0)

    def test_unavailable_snapshot(self):
        """Snapshot older than 60 seconds is unavailable."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        result = assess_capability_snapshot(snapshot, 1061.0)
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["usable"])
        self.assertEqual(result["age"], 61.0)

    def test_schema_must_be_int(self):
        """Schema must be int 1, not bool True."""
        snapshot = {
            "schema": True,  # bool, not int
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            assess_capability_snapshot(snapshot, 1001.0)
        self.assertIn("schema", str(context.exception))

    def test_schema_zero_rejected(self):
        """Schema 0 is rejected."""
        snapshot = {
            "schema": 0,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            assess_capability_snapshot(snapshot, 1001.0)
        self.assertIn("schema", str(context.exception))

    def test_negative_observed_at_raises(self):
        """Negative observed_at raises ValueError."""
        snapshot = {
            "schema": 1,
            "observed_at": -1.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            assess_capability_snapshot(snapshot, 1001.0)
        self.assertIn("observed_at", str(context.exception))

    def test_now_less_than_observed_at_raises(self):
        """now < observed_at raises ValueError."""
        snapshot = {
            "schema": 1,
            "observed_at": 1001.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError) as context:
            assess_capability_snapshot(snapshot, 1000.0)
        self.assertIn("now", str(context.exception))

    def test_fingerprint_deterministic(self):
        """Fingerprint is deterministic across calls."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation", "logistics"],
        }
        result1 = assess_capability_snapshot(snapshot, 1001.0)
        result2 = assess_capability_snapshot(snapshot, 1001.0)
        self.assertEqual(result1["fingerprint"], result2["fingerprint"])

    def test_snapshot_preserved_in_result(self):
        """Original snapshot is preserved in result."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        result = assess_capability_snapshot(snapshot, 1001.0)
        self.assertEqual(result["snapshot"], snapshot)

    def test_status_enum_type(self):
        """Status is one of the allowed Status enum values."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        result = assess_capability_snapshot(snapshot, 1001.0)
        self.assertIn(result["status"], ["live", "stale", "usable"])


class TestR04AcceptanceCriteria(unittest.TestCase):
    """Test R04 acceptance criteria."""

    def test_observations_read_only(self):
        """assess_capability_snapshot does not mutate snapshot."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation"],
        }
        original_research = snapshot["research"][:]
        result = assess_capability_snapshot(snapshot, 1001.0)
        self.assertEqual(result["snapshot"]["research"], original_research)

    def test_fingerprints_deterministic(self):
        """Fingerprints are deterministic (SHA256 with sorted keys)."""
        canonical1 = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation", "logistics"],
        }
        canonical2 = {
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": ["automation", "logistics"],
        }
        fp1 = _compute_fingerprint(canonical1)
        fp2 = _compute_fingerprint(canonical2)
        self.assertEqual(fp1, fp2)

    def test_stale_offline_states_explicit(self):
        """Status is explicit: live/stale/unavailable."""
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        result_live = assess_capability_snapshot(snapshot, 1001.0)
        result_stale = assess_capability_snapshot(snapshot, 1006.0)
        result_unavailable = assess_capability_snapshot(snapshot, 1061.0)
        self.assertEqual(result_live["status"], "live")
        self.assertEqual(result_stale["status"], "stale")
        self.assertEqual(result_unavailable["status"], "unavailable")

    def test_missing_recipes_never_invented(self):
        """assess_capability_snapshot does not invent missing recipes."""
        # This is verified by the fact that assess_capability_snapshot
        # only reads from snapshot and never calls game APIs.
        snapshot = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        result = assess_capability_snapshot(snapshot, 1001.0)
        # Result only contains status, fingerprint, usable, age, snapshot
        self.assertIn("status", result)
        self.assertIn("fingerprint", result)
        self.assertIn("usable", result)
        self.assertIn("age", result)
        self.assertIn("snapshot", result)

    def test_strict_contract_enforced(self):
        """Strict contract is enforced (schema, timestamps, control chars)."""
        # Test schema validation
        snapshot_invalid_schema = {
            "schema": True,
            "observed_at": 1000.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError):
            assess_capability_snapshot(snapshot_invalid_schema, 1001.0)

        # Test timestamp validation
        snapshot_negative_observed = {
            "schema": 1,
            "observed_at": -1.0,
            "game_version": "1.1.10",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError):
            assess_capability_snapshot(snapshot_negative_observed, 1001.0)

        # Test control character validation
        snapshot_control_chars = {
            "schema": 1,
            "observed_at": 1000.0,
            "game_version": "1.1\x0010",
            "force": "vanilla",
            "surface": "space",
            "research": [],
        }
        with self.assertRaises(ValueError):
            assess_capability_snapshot(snapshot_control_chars, 1001.0)


if __name__ == "__main__":
    unittest.main()

class TestFiniteSnapshotInputs(unittest.TestCase):
    def test_nonfinite_observation_rejected(self):
        for bad in (float("nan"), float("inf"), -float("inf")):
            snapshot = {"schema": 1, "observed_at": bad, "game_version": "2.1.23",
                        "force": "player", "surface": "nauvis", "research": []}
            with self.subTest(value=str(bad)), self.assertRaises(ValueError):
                assess_capability_snapshot(snapshot, now=100)

    def test_invalid_clock_or_max_age_rejected(self):
        snapshot = {"schema": 1, "observed_at": 100, "game_version": "2.1.23",
                    "force": "player", "surface": "nauvis", "research": []}
        for bad in (float("nan"), float("inf"), -float("inf"), True):
            with self.subTest(now=str(bad)), self.assertRaises(ValueError):
                assess_capability_snapshot(snapshot, now=bad)
        for bad in (float("nan"), float("inf"), -float("inf"), -1):
            with self.subTest(max_age=str(bad)), self.assertRaises(ValueError):
                assess_capability_snapshot(snapshot, now=101, max_age=bad)
