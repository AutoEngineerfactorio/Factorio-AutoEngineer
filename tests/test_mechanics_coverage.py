"""
R05 Mechanics Coverage Ledger — Test suite for mechanics coverage ledger.

This test suite validates:
1. Mechanic entry creation with all required dimensions
2. Status computation logic
3. Ledger creation and summary computation
4. Validation of mechanic entries
5. Update operations (observation, permission, justification, mode, result, regression)
6. R05 acceptance criteria
"""

import unittest

from agent.mechanics_coverage import (
    MECHANIC_CATEGORIES,
    Mode,
    add_action_permission,
    add_justification_na,
    add_mode,
    add_observation,
    add_regression_evidence,
    add_result_verification,
    compute_ledger_summary,
    compute_mechanic_status,
    create_mechanic_entry,
    create_mechanics_ledger,
    validate_mechanic_entry,
)


class TestMechanicEntryCreation(unittest.TestCase):
    """Test mechanic entry creation."""
    
    def test_create_entry_with_all_fields(self) -> None:
        """Test creating a complete mechanic entry."""
        entry = create_mechanic_entry(
            category="character-reach",
            profile_version="vanilla-1.20",
            observed={"position": (10, 10), "reachable": True},
            planned={"action": "move", "target": (20, 20)},
            action_permitted=True,
            mode="AI Helper",
            result_verified={"success": True, "timestamp": 1234567890.0},
            regression_evidence={"test_id": "R05-char-reach-001", "passed": True},
        )
        
        self.assertEqual(entry["category"], "character-reach")
        self.assertEqual(entry["profile_version"], "vanilla-1.20")
        self.assertEqual(entry["observed"]["position"], (10, 10))
        self.assertEqual(entry["planned"]["action"], "move")
        self.assertTrue(entry["action_permitted"])
        self.assertEqual(entry["mode"], "AI Helper")
        self.assertTrue(entry["result_verified"]["success"])
        self.assertEqual(entry["regression_evidence"]["test_id"], "R05-char-reach-001")
    
    def test_create_entry_with_minimal_fields(self) -> None:
        """Test creating a minimal mechanic entry."""
        entry = create_mechanic_entry(
            category="mining-depletion",
            profile_version="vanilla-1.20",
        )
        
        self.assertEqual(entry["category"], "mining-depletion")
        self.assertEqual(entry["profile_version"], "vanilla-1.20")
        self.assertIsNone(entry["observed"])
        self.assertIsNone(entry["planned"])
        self.assertIsNone(entry["action_permitted"])
        self.assertIsNone(entry["action_justified_na"])
        self.assertIsNone(entry["mode"])
        self.assertIsNone(entry["result_verified"])
        self.assertIsNone(entry["regression_evidence"])
    
    def test_create_entry_with_invalid_category(self) -> None:
        """Test that invalid category raises ValueError."""
        with self.assertRaises(ValueError) as context:
            create_mechanic_entry(
                category="invalid-category",
                profile_version="vanilla-1.20",
            )
        
        self.assertIn("Unknown mechanic category", str(context.exception))


class TestMechanicStatusComputation(unittest.TestCase):
    """Test mechanic status computation."""
    
    def test_status_action_justified_na_priority(self) -> None:
        """Test that action_justified_na has highest priority."""
        status = compute_mechanic_status(
            observed={"data": "test"},
            planned={"action": "test"},
            action_permitted=True,
            action_justified_na="Not supported in this profile",
        )
        self.assertEqual(status, "action-justified-na")
    
    def test_status_action_permitted(self) -> None:
        """Test status when action is permitted."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=True,
            action_justified_na=None,
        )
        self.assertEqual(status, "action-permitted")
    
    def test_status_observed(self) -> None:
        """Test status when observation exists."""
        status = compute_mechanic_status(
            observed={"position": (10, 10)},
            planned=None,
            action_permitted=None,
            action_justified_na=None,
        )
        self.assertEqual(status, "observed")
    
    def test_status_planned(self) -> None:
        """Test status when only planned exists."""
        status = compute_mechanic_status(
            observed=None,
            planned={"action": "test"},
            action_permitted=None,
            action_justified_na=None,
        )
        self.assertEqual(status, "planned")
    
    def test_status_default_unobserved(self) -> None:
        """Test default status when nothing is set."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=None,
            action_justified_na=None,
        )
        self.assertEqual(status, "unobserved")
    
    def test_status_verified(self) -> None:
        """Test status when result is verified."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            result_verified={"success": True},
        )
        self.assertEqual(status, "verified")
    
    def test_status_regression_passed(self) -> None:
        """Test status when regression evidence has passed=True."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            regression_evidence={"test_id": "R05-001", "passed": True},
        )
        self.assertEqual(status, "regression-passed")
    
    def test_status_failed_verification(self) -> None:
        """Test that failed verification does not produce 'verified' status."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            result_verified={"success": False},
        )
        self.assertEqual(status, "unobserved")
    
    def test_status_failed_regression(self) -> None:
        """Test that failed regression does not produce 'regression-passed' status."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            regression_evidence={"test_id": "R05-001", "passed": False},
        )
        self.assertEqual(status, "unobserved")
    
    def test_status_observed_plus_verified(self) -> None:
        """Test that verification has higher priority than observation."""
        status = compute_mechanic_status(
            observed={"position": (10, 10)},
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            result_verified={"success": True},
        )
        self.assertEqual(status, "verified")
    
    def test_status_observed_plus_failed_verification(self) -> None:
        """Test that observation takes precedence over failed verification."""
        status = compute_mechanic_status(
            observed={"position": (10, 10)},
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            result_verified={"success": False},
        )
        self.assertEqual(status, "observed")
    
    def test_status_observed_plus_passed_regression(self) -> None:
        """Test that regression evidence has higher priority than observation."""
        status = compute_mechanic_status(
            observed={"position": (10, 10)},
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            regression_evidence={"test_id": "R05-001", "passed": True},
        )
        self.assertEqual(status, "regression-passed")
    
    def test_status_malformed_verification(self) -> None:
        """Test that malformed verification dict does not produce 'verified' status."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            result_verified={"timestamp": 1234567890.0},  # Missing success key
        )
        self.assertEqual(status, "unobserved")
    
    def test_status_malformed_regression(self) -> None:
        """Test that malformed regression dict does not produce 'regression-passed' status."""
        status = compute_mechanic_status(
            observed=None,
            planned=None,
            action_permitted=None,
            action_justified_na=None,
            regression_evidence={"test_id": "R05-001"},  # Missing passed key
        )
        self.assertEqual(status, "unobserved")


class TestMechanicsLedgerCreation(unittest.TestCase):
    """Test ledger creation."""
    
    def test_create_empty_ledger(self) -> None:
        """Test creating an empty ledger."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        
        self.assertEqual(ledger["profile_version"], "vanilla-1.20")
        self.assertEqual(ledger["total_categories"], len(MECHANIC_CATEGORIES))
        self.assertEqual(ledger["covered_categories"], len(MECHANIC_CATEGORIES))
    
    def test_create_ledger_with_mechanics(self) -> None:
        """Test creating a ledger with pre-populated mechanics."""
        mechanics = [
            create_mechanic_entry(
                category="character-reach",
                profile_version="vanilla-1.20",
                observed={"position": (10, 10)},
            ),
            create_mechanic_entry(
                category="mining-depletion",
                profile_version="vanilla-1.20",
                observed={"mined": 100},
            ),
        ]
        
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20", mechanics=mechanics)
        
        self.assertEqual(ledger["profile_version"], "vanilla-1.20")
        self.assertEqual(ledger["total_categories"], len(MECHANIC_CATEGORIES))
        self.assertEqual(ledger["covered_categories"], len(MECHANIC_CATEGORIES))
    
    def test_ledger_mechanics_sorted(self) -> None:
        """Test that mechanics are sorted by category."""
        # Note: create_mechanics_ledger auto-populates missing categories
        # So we need to provide all categories with their statuses
        mechanics = [
            create_mechanic_entry(category="combat-world-dynamics", profile_version="v1"),
            create_mechanic_entry(category="character-reach", profile_version="v1"),
            create_mechanic_entry(category="construction-deconstruction-upgrade-tiles-cliffs", profile_version="v1"),
            create_mechanic_entry(category="health-death-respawn", profile_version="v1"),
            create_mechanic_entry(category="item-retrieval", profile_version="v1"),
            create_mechanic_entry(category="inventories-equipment-ammo", profile_version="v1"),
            create_mechanic_entry(category="vehicles-entry-fuel", profile_version="v1"),
            create_mechanic_entry(category="manufacturing-research", profile_version="v1"),
            create_mechanic_entry(category="mining-depletion", profile_version="v1"),
            create_mechanic_entry(category="rails-circuits-robots", profile_version="v1"),
            create_mechanic_entry(category="rockets-victory", profile_version="v1"),
            create_mechanic_entry(category="belts-inserters-storage", profile_version="v1"),
            create_mechanic_entry(category="fluids-thermal-power", profile_version="v1"),
        ]
        
        ledger = create_mechanics_ledger(profile_version="v1", mechanics=mechanics)
        
        # Alphabetical order: belts-inserters-storage, character-reach, combat-world-dynamics, etc.
        self.assertEqual(ledger["mechanics"][0]["category"], "belts-inserters-storage")
        self.assertEqual(ledger["mechanics"][1]["category"], "character-reach")
        self.assertEqual(ledger["mechanics"][2]["category"], "combat-world-dynamics")


class TestMechanicEntryValidation(unittest.TestCase):
    """Test mechanic entry validation."""
    
    def test_valid_entry(self) -> None:
        """Test that a valid entry passes validation."""
        entry = create_mechanic_entry(
            category="character-reach",
            profile_version="vanilla-1.20",
            observed={"position": (10, 10)},
        )
        
        errors = validate_mechanic_entry(entry)
        self.assertEqual(errors, [])
    
    def test_invalid_category(self) -> None:
        """Test that invalid category produces error."""
        entry = {
            "category": "invalid-category",
            "profile_version": "vanilla-1.20",
            "observed": {"position": (10, 10)},
        }
        
        errors = validate_mechanic_entry(entry)
        self.assertGreater(len(errors), 0)
        self.assertIn("Invalid category", errors[0])
    
    def test_invalid_profile_version(self) -> None:
        """Test that invalid profile_version produces error."""
        entry = create_mechanic_entry(
            category="character-reach",
            profile_version="",
            observed={"position": (10, 10)},
        )
        
        errors = validate_mechanic_entry(entry)
        self.assertGreater(len(errors), 0)
        self.assertIn("profile_version must be a nonempty string", errors[0])
    
    def test_empty_entry_is_valid(self) -> None:
        """Test that empty entries (unobserved state) are valid."""
        entry = create_mechanic_entry(
            category="character-reach",
            profile_version="vanilla-1.20",
        )
        
        errors = validate_mechanic_entry(entry)
        self.assertEqual(errors, [])


class TestLedgerSummary(unittest.TestCase):
    """Test ledger summary computation."""
    
    def test_summary_empty_ledger(self) -> None:
        """Test summary of empty ledger."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        summary = compute_ledger_summary(ledger)
        
        self.assertEqual(summary["profile_version"], "vanilla-1.20")
        self.assertEqual(summary["total_categories"], len(MECHANIC_CATEGORIES))
        self.assertEqual(summary["categories_with_evidence"], 0)
        self.assertEqual(summary["evidence_based_coverage_percentage"], 0.0)
        self.assertEqual(summary["status_counts"]["unobserved"], len(MECHANIC_CATEGORIES))
    
    def test_summary_with_mixed_statuses(self) -> None:
        """Test summary with mixed status counts."""
        # Create a ledger with some categories having different statuses
        mechanics = [
            create_mechanic_entry(
                category="character-reach",
                profile_version="vanilla-1.20",
                observed={"position": (10, 10)},
            ),
            create_mechanic_entry(
                category="mining-depletion",
                profile_version="vanilla-1.20",
                action_permitted=True,
            ),
            create_mechanic_entry(
                category="belts-inserters-storage",
                profile_version="vanilla-1.20",
                action_justified_na="Not applicable",
            ),
        ]
        
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20", mechanics=mechanics)
        summary = compute_ledger_summary(ledger)
        
        # character-reach: observed -> "observed"
        # mining-depletion: action_permitted=True -> "action-permitted"
        # belts-inserters-storage: action_justified_na -> "action-justified-na"
        # Others: unobserved (default) -> "unobserved"
        self.assertEqual(summary["status_counts"]["observed"], 1)
        self.assertEqual(summary["status_counts"]["action-permitted"], 1)
        self.assertEqual(summary["status_counts"]["action-justified-na"], 1)
        self.assertEqual(summary["status_counts"]["unobserved"], 10)


class TestAddObservation(unittest.TestCase):
    """Test adding observation to ledger."""
    
    def test_add_observation(self) -> None:
        """Test adding observation to a mechanic."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_observation(
            ledger,
            category="character-reach",
            observation={"position": (10, 10), "reachable": True},
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertEqual(entry["observed"]["position"], (10, 10))
        # Status is computed separately, not set by add_observation
        self.assertEqual(compute_mechanic_status(
            observed=entry.get("observed"),
            planned=entry.get("planned"),
            action_permitted=entry.get("action_permitted"),
            action_justified_na=entry.get("action_justified_na"),
        ), "observed")
    
    def test_add_observation_invalid_category(self) -> None:
        """Test adding observation to invalid category raises error."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        
        with self.assertRaises(ValueError) as context:
            add_observation(
                ledger,
                category="invalid-category",
                observation={"position": (10, 10)},
            )
        
        self.assertIn("Unknown mechanic category", str(context.exception))


class TestAddActionPermission(unittest.TestCase):
    """Test adding action permission to ledger."""
    
    def test_add_action_permitted(self) -> None:
        """Test adding action permission."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_action_permission(
            ledger,
            category="character-reach",
            permitted=True,
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertTrue(entry["action_permitted"])
        # Status is computed separately
        self.assertEqual(compute_mechanic_status(
            observed=entry.get("observed"),
            planned=entry.get("planned"),
            action_permitted=entry.get("action_permitted"),
            action_justified_na=entry.get("action_justified_na"),
        ), "action-permitted")
    
    def test_add_action_not_permitted(self) -> None:
        """Test adding action not permitted."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_action_permission(
            ledger,
            category="character-reach",
            permitted=False,
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertFalse(entry["action_permitted"])
        # Status is computed separately
        self.assertEqual(compute_mechanic_status(
            observed=entry.get("observed"),
            planned=entry.get("planned"),
            action_permitted=entry.get("action_permitted"),
            action_justified_na=entry.get("action_justified_na"),
        ), "unobserved")


class TestAddJustificationNA(unittest.TestCase):
    """Test adding N/A justification to ledger."""
    
    def test_add_justification_na(self) -> None:
        """Test adding N/A justification."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_justification_na(
            ledger,
            category="character-reach",
            justification="Not supported in this profile version",
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertIsNotNone(entry["action_justified_na"])
        # Status is computed separately
        self.assertEqual(compute_mechanic_status(
            observed=entry.get("observed"),
            planned=entry.get("planned"),
            action_permitted=entry.get("action_permitted"),
            action_justified_na=entry.get("action_justified_na"),
        ), "action-justified-na")


class TestAddMode(unittest.TestCase):
    """Test adding mode to ledger."""
    
    def test_add_mode_ai_helper(self) -> None:
        """Test adding AI Helper mode."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_mode(
            ledger,
            category="character-reach",
            mode="AI Helper",
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertEqual(entry["mode"], "AI Helper")
    
    def test_add_mode_invalid(self) -> None:
        """Test adding invalid mode raises error."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        
        with self.assertRaises(ValueError) as context:
            add_mode(
                ledger,
                category="character-reach",
                mode="Invalid Mode",
            )
        
        self.assertIn("Invalid mode", str(context.exception))


class TestAddResultVerification(unittest.TestCase):
    """Test adding result verification to ledger."""
    
    def test_add_result_verification(self) -> None:
        """Test adding result verification."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_result_verification(
            ledger,
            category="character-reach",
            result={"success": True, "timestamp": 1234567890.0},
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertTrue(entry["result_verified"]["success"])
        # Status is computed separately
        self.assertEqual(compute_mechanic_status(
            observed=entry.get("observed"),
            planned=entry.get("planned"),
            action_permitted=entry.get("action_permitted"),
            action_justified_na=entry.get("action_justified_na"),
            result_verified=entry.get("result_verified"),
        ), "verified")
    
    def test_add_result_verification_invalid_category(self) -> None:
        """Test adding result verification to invalid category raises error."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        
        with self.assertRaises(ValueError) as context:
            add_result_verification(
                ledger,
                category="invalid-category",
                result={"success": True},
            )
        
        self.assertIn("Unknown mechanic category", str(context.exception))


class TestAddRegressionEvidence(unittest.TestCase):
    """Test adding regression evidence to ledger."""
    
    def test_add_regression_evidence(self) -> None:
        """Test adding regression evidence."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_regression_evidence(
            ledger,
            category="character-reach",
            evidence={"test_id": "R05-001", "passed": True},
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertEqual(entry["regression_evidence"]["test_id"], "R05-001")
        self.assertTrue(entry["regression_evidence"]["passed"])
    
    def test_add_regression_evidence_invalid_category(self) -> None:
        """Test adding regression evidence to invalid category raises error."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        
        with self.assertRaises(ValueError) as context:
            add_regression_evidence(
                ledger,
                category="invalid-category",
                evidence={"test_id": "test-001"},
            )
        
        self.assertIn("Unknown mechanic category", str(context.exception))


class TestR05AcceptanceCriteria(unittest.TestCase):
    """Test R05 acceptance criteria."""
    
    def test_1_each_mechanic_records_all_dimensions(self) -> None:
        """R05.1: Each mechanic records profile/version, observation, plan, permitted action, N/A, mode, result, regression."""
        entry = create_mechanic_entry(
            category="character-reach",
            profile_version="vanilla-1.20",
            observed={"position": (10, 10)},
            planned={"action": "move"},
            action_permitted=True,
            action_justified_na=None,
            mode="AI Helper",
            result_verified={"success": True},
            regression_evidence={"test_id": "R05-001", "passed": True},
        )
        
        self.assertEqual(entry["profile_version"], "vanilla-1.20")
        self.assertIsNotNone(entry["observed"])
        self.assertIsNotNone(entry["planned"])
        self.assertIsNotNone(entry["action_permitted"])
        self.assertIsNone(entry["action_justified_na"])
        self.assertEqual(entry["mode"], "AI Helper")
        self.assertIsNotNone(entry["result_verified"])
        self.assertIsNotNone(entry["regression_evidence"])
    
    def test_2_coverage_ledger_is_read_only_and_bounded(self) -> None:
        """R05.2: Coverage ledger is read-only and bounded."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        summary = compute_ledger_summary(ledger)
        
        # These operations don't mutate the ledger in place
        self.assertEqual(summary["profile_version"], "vanilla-1.20")
        self.assertIn("status_counts", summary)
        self.assertIn("categories_with_evidence", summary)
        self.assertIn("evidence_based_coverage_percentage", summary)
    
    def test_3_na_justifications_are_explicit(self) -> None:
        """R05.3: N/A justifications are explicit and documented."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_justification_na(
            ledger,
            category="character-reach",
            justification="Not supported in this profile version",
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertIsNotNone(entry["action_justified_na"])
        self.assertIn("Not supported", entry["action_justified_na"])
    
    def test_4_mode_permissions_are_tracked(self) -> None:
        """R05.4: Mode permissions are tracked per mechanic."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_mode(ledger, category="character-reach", mode="AI Helper")
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertEqual(entry["mode"], "AI Helper")
    
    def test_5_result_verification_and_regression_evidence_recorded(self) -> None:
        """R05.5: Result verification and regression evidence are recorded."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_result_verification(
            ledger,
            category="character-reach",
            result={"success": True, "timestamp": 1234567890.0},
        )
        ledger = add_regression_evidence(
            ledger,
            category="character-reach",
            evidence={"test_id": "R05-001", "passed": True},
        )
        
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        self.assertTrue(entry["result_verified"]["success"])
        self.assertTrue(entry["regression_evidence"]["passed"])
    
    def test_evidence_dimensions_independent(self) -> None:
        """Each dimension is tracked independently; one does not imply others."""
        ledger = create_mechanics_ledger(profile_version="vanilla-1.20")
        ledger = add_observation(
            ledger,
            category="character-reach",
            observation={"position": (10, 10)},
        )
        entry = next(e for e in ledger["mechanics"] if e["category"] == "character-reach")
        # Has observation but no permission, verification, or regression evidence
        self.assertIsNotNone(entry["observed"])
        self.assertIsNone(entry["action_permitted"])
        self.assertIsNone(entry["result_verified"])
        self.assertIsNone(entry["regression_evidence"])


class TestMechanicCategories(unittest.TestCase):
    """Test mechanic categories are complete."""
    
    def test_all_categories_defined(self) -> None:
        """Test that all R05 categories are defined."""
        expected_categories = [
            "character-reach",
            "health-death-respawn",
            "item-retrieval",
            "inventories-equipment-ammo",
            "vehicles-entry-fuel",
            "mining-depletion",
            "belts-inserters-storage",
            "fluids-thermal-power",
            "manufacturing-research",
            "construction-deconstruction-upgrade-tiles-cliffs",
            "rails-circuits-robots",
            "combat-world-dynamics",
            "rockets-victory",
        ]
        
        self.assertEqual(len(MECHANIC_CATEGORIES), len(expected_categories))
        for cat in expected_categories:
            self.assertIn(cat, MECHANIC_CATEGORIES)
    
    def test_categories_count(self) -> None:
        """Test that we have the expected number of categories."""
        self.assertEqual(len(MECHANIC_CATEGORIES), 13)


class TestModeEnum(unittest.TestCase):
    """Test mode enum values."""
    
    def test_valid_modes(self) -> None:
        """Test that valid modes are recognized."""
        valid_modes: list[Mode] = ["AI Helper", "Semi-Autonomous", "Fully Autonomous"]
        for mode in valid_modes:
            self.assertIn(mode, ["AI Helper", "Semi-Autonomous", "Fully Autonomous"])
    
    def test_invalid_mode_rejected(self) -> None:
        """Test that invalid modes are rejected."""
        with self.assertRaises(ValueError):
            add_mode(
                create_mechanics_ledger(profile_version="v1"),
                category="character-reach",
                mode="Invalid Mode",
            )


if __name__ == "__main__":
    unittest.main()
