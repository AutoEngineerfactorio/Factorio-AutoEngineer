"""
R05 Mechanics Coverage Ledger — Track each mechanic's status across required dimensions.

This module provides a ledger that records each mechanic's coverage status with:
- profile/version
- observation (observed or justified N/A)
- plan (planned action or N/A)
- permitted action or justified N/A
- mode (AI Helper, Semi-Autonomous, Fully Autonomous)
- result verification
- regression/run evidence

Acceptance criteria (R05):
1. Each mechanic records all required dimensions
2. Coverage ledger is read-only and bounded
3. N/A justifications are explicit and documented
4. Mode permissions are tracked per mechanic
5. Result verification and regression evidence are recorded
"""

from typing import Any, Literal, Optional

# Operating modes
Mode = Literal["AI Helper", "Semi-Autonomous", "Fully Autonomous"]

# Mechanic status values
MechanicStatus = Literal["unobserved", "observed", "planned", "action-permitted", "action-justified-na", "verified", "regression-passed"]

# Mechanic categories from PLANNING_REQUIREMENTS.md R05
MECHANIC_CATEGORIES = [
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


def create_mechanic_entry(
    category: str,
    profile_version: str,
    observed: Optional[dict[str, Any]] = None,
    planned: Optional[dict[str, Any]] = None,
    action_permitted: Optional[bool] = None,
    action_justified_na: Optional[str] = None,
    mode: Optional[Mode] = None,
    result_verified: Optional[dict[str, Any]] = None,
    regression_evidence: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Create a mechanic coverage entry with all required dimensions.
    
    Args:
        category: The mechanic category (from MECHANIC_CATEGORIES)
        profile_version: The profile/version string for this mechanic
        observed: Dict with observation data (or None if not observed)
        planned: Dict with planned action data (or None if not planned)
        action_permitted: Whether action is permitted (or None if not applicable)
        action_justified_na: Justification for N/A status (or None if not N/A)
        mode: Operating mode (or None if not specified)
        result_verified: Dict with result verification data (or None)
        regression_evidence: Dict with regression test evidence (or None)
        
    Returns:
        A complete mechanic entry dict
        
    Raises:
        ValueError: If category is not in MECHANIC_CATEGORIES
    """
    if category not in MECHANIC_CATEGORIES:
        raise ValueError(f"Unknown mechanic category: {category}. Must be one of {MECHANIC_CATEGORIES}")
    
    entry: dict[str, Any] = {
        "category": category,
        "profile_version": profile_version,
        "observed": observed,
        "planned": planned,
        "action_permitted": action_permitted,
        "action_justified_na": action_justified_na,
        "mode": mode,
        "result_verified": result_verified,
        "regression_evidence": regression_evidence,
    }
    
    return entry


def compute_mechanic_status(
    observed: Optional[dict[str, Any]],
    planned: Optional[dict[str, Any]],
    action_permitted: Optional[bool],
    action_justified_na: Optional[str],
    result_verified: Optional[dict[str, Any]] = None,
    regression_evidence: Optional[dict[str, Any]] = None,
) -> MechanicStatus:
    """
    Compute the current status of a mechanic based on its coverage data.
    
    Status precedence (highest to lowest):
    1. action_justified_na -> "action-justified-na"
    2. result_verified with success=True -> "verified"
    3. regression_evidence with passed=True -> "regression-passed"
    4. action_permitted=True -> "action-permitted"
    5. observed -> "observed"
    6. planned -> "planned"
    7. Default -> "unobserved" (no evidence exists)
    
    Evidence dimensions are tracked independently. A single summary status does not
    erase information about unsuccessful or incomplete steps. All dimensions remain
    available for inspection.
    
    Critical: Missing evidence must never imply success. Failed verification must
    never produce "verified". Failed regression must never produce "regression-passed".
    
    Args:
        observed: Observation data (or None if not observed)
        planned: Planned action data (or None if not planned)
        action_permitted: Whether action is permitted (or None if not applicable)
        action_justified_na: Justification for N/A status (or None if not N/A)
        result_verified: Result verification data (or None)
        regression_evidence: Regression test evidence (or None)
        
    Returns:
        The computed MechanicStatus
    """
    if action_justified_na is not None and action_justified_na.strip():
        return "action-justified-na"
    
    # Actual verification and passed regression rank above mere permission.
    if isinstance(result_verified, dict) and result_verified.get("success") is True:
        return "verified"

    if isinstance(regression_evidence, dict) and regression_evidence.get("passed") is True:
        return "regression-passed"

    if action_permitted is True:
        return "action-permitted"
    
    if observed is not None:
        return "observed"
    
    if planned is not None:
        return "planned"
    
    return "unobserved"  # Default: no evidence exists


def create_mechanics_ledger(
    profile_version: str,
    mechanics: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Create a complete mechanics coverage ledger.
    
    Args:
        profile_version: The profile/version string for the ledger
        mechanics: List of mechanic entries (or None to create empty ledger)
        
    Returns:
        A complete ledger dict with all mechanics
    """
    if mechanics is None:
        mechanics = []
    
    # Create entries for all categories if not provided
    if len(mechanics) < len(MECHANIC_CATEGORIES):
        for category in MECHANIC_CATEGORIES:
            if not any(m.get("category") == category for m in mechanics):
                entry = create_mechanic_entry(
                    category=category,
                    profile_version=profile_version,
                    observed=None,
                    planned=None,
                    action_permitted=None,
                    action_justified_na=None,
                    mode=None,
                    result_verified=None,
                    regression_evidence=None,
                )
                mechanics.append(entry)
    
    # Sort by category for consistent ordering
    mechanics = sorted(mechanics, key=lambda m: m["category"])
    
    return {
        "profile_version": profile_version,
        "mechanics": mechanics,
        "total_categories": len(MECHANIC_CATEGORIES),
        "covered_categories": len(mechanics),
    }


def validate_mechanic_entry(entry: dict[str, Any]) -> list[str]:
    """
    Validate a mechanic entry for completeness and correctness.
    
    Empty entries (no evidence) are valid and represent "unobserved" state.
    Each dimension is tracked independently; one dimension does not imply others.
    
    Args:
        entry: A mechanic entry dict
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []
    
    # Check category
    if entry.get("category") not in MECHANIC_CATEGORIES:
        errors.append(f"Invalid category: {entry.get('category')}")
    
    # Check profile_version
    profile_version = entry.get("profile_version")
    if not isinstance(profile_version, str) or len(profile_version) > 128 or len(profile_version) == 0:
        errors.append("profile_version must be a nonempty string <=128 chars")
    
    # Empty entries are valid (represent "unobserved" state)
    # Each dimension is tracked independently
    return errors


def compute_ledger_summary(ledger: dict[str, Any]) -> dict[str, Any]:
    """
    Compute a summary of the mechanics coverage ledger.
    
    Evidence-based coverage is calculated separately from category count.
    A category is "covered" if it has at least one evidence dimension set.
    A category is "verified" only if it has successful verification evidence.
    
    Args:
        ledger: A complete ledger dict
        
    Returns:
        Summary dict with coverage statistics
    """
    mechanics = ledger.get("mechanics", [])
    
    status_counts: dict[str, int] = {
        "unobserved": 0,
        "action-justified-na": 0,
        "action-permitted": 0,
        "observed": 0,
        "planned": 0,
        "verified": 0,
        "regression-passed": 0,
    }
    
    for entry in mechanics:
        status = compute_mechanic_status(
            observed=entry.get("observed"),
            planned=entry.get("planned"),
            action_permitted=entry.get("action_permitted"),
            action_justified_na=entry.get("action_justified_na"),
            result_verified=entry.get("result_verified"),
            regression_evidence=entry.get("regression_evidence"),
        )
        status_counts[status] = status_counts.get(status, 0) + 1
    
    # Calculate evidence-based coverage: categories with at least one evidence dimension
    categories_with_evidence = sum(
        1 for e in mechanics
        if e.get("observed") is not None
        or e.get("planned") is not None
        or e.get("action_permitted") is not None
        or e.get("action_justified_na") is not None
        or e.get("result_verified") is not None
        or e.get("regression_evidence") is not None
    )
    
    # Independent dimensions: permission does not erase evidence or failed tests.
    categories_with_successful_verification = sum(
        isinstance(e.get("result_verified"), dict)
        and e["result_verified"].get("success") is True for e in mechanics
    )
    categories_with_passed_regression = sum(
        isinstance(e.get("regression_evidence"), dict)
        and e["regression_evidence"].get("passed") is True for e in mechanics
    )
    dimension_counts = {
        "observed": sum(e.get("observed") is not None for e in mechanics),
        "planned": sum(e.get("planned") is not None for e in mechanics),
        "action_permitted": sum(e.get("action_permitted") is True for e in mechanics),
        "verified": categories_with_successful_verification,
        "regression_passed": categories_with_passed_regression,
        "verification_failed": sum(
            isinstance(e.get("result_verified"), dict)
            and e["result_verified"].get("success") is False for e in mechanics
        ),
        "regression_failed": sum(
            isinstance(e.get("regression_evidence"), dict)
            and e["regression_evidence"].get("passed") is False for e in mechanics
        ),
    }

    return {
        "profile_version": ledger.get("profile_version"),
        "total_categories": len(mechanics),
        "categories_with_evidence": categories_with_evidence,
        "evidence_based_coverage_percentage": round(categories_with_evidence / len(MECHANIC_CATEGORIES) * 100, 1),
        "categories_with_successful_verification": categories_with_successful_verification,
        "successful_verification_percentage": round(categories_with_successful_verification / len(MECHANIC_CATEGORIES) * 100, 1),
        "categories_with_passed_regression": categories_with_passed_regression,
        "dimension_counts": dimension_counts,
        "status_counts": status_counts,
    }


def add_observation(
    ledger: dict[str, Any],
    category: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    """
    Add observation data to a mechanic entry in the ledger.
    
    Each dimension is tracked independently. Status is computed separately.
    
    Args:
        ledger: The ledger dict
        category: The mechanic category
        observation: The observation data to add
        
    Returns:
        Updated ledger dict
        
    Raises:
        ValueError: If category not found or invalid
    """
    if category not in MECHANIC_CATEGORIES:
        raise ValueError(f"Unknown mechanic category: {category}")
    
    for entry in ledger["mechanics"]:
        if entry["category"] == category:
            entry["observed"] = observation
            return ledger
    
    raise ValueError(f"Mechanic category not found: {category}")


def add_action_permission(
    ledger: dict[str, Any],
    category: str,
    permitted: bool,
) -> dict[str, Any]:
    """
    Add action permission status to a mechanic entry.
    
    Each dimension is tracked independently. Status is computed separately.
    
    Args:
        ledger: The ledger dict
        category: The mechanic category
        permitted: Whether action is permitted
        
    Returns:
        Updated ledger dict
        
    Raises:
        ValueError: If category not found or invalid
    """
    if category not in MECHANIC_CATEGORIES:
        raise ValueError(f"Unknown mechanic category: {category}")
    
    for entry in ledger["mechanics"]:
        if entry["category"] == category:
            entry["action_permitted"] = permitted
            return ledger
    
    raise ValueError(f"Mechanic category not found: {category}")


def add_justification_na(
    ledger: dict[str, Any],
    category: str,
    justification: str,
) -> dict[str, Any]:
    """
    Add N/A justification to a mechanic entry.
    
    Each dimension is tracked independently. Status is computed separately.
    
    Args:
        ledger: The ledger dict
        category: The mechanic category
        justification: The justification for N/A status
        
    Returns:
        Updated ledger dict
        
    Raises:
        ValueError: If category not found or invalid
    """
    if category not in MECHANIC_CATEGORIES:
        raise ValueError(f"Unknown mechanic category: {category}")
    
    for entry in ledger["mechanics"]:
        if entry["category"] == category:
            entry["action_justified_na"] = justification
            return ledger
    
    raise ValueError(f"Mechanic category not found: {category}")


def add_mode(
    ledger: dict[str, Any],
    category: str,
    mode: Mode,
) -> dict[str, Any]:
    """
    Add operating mode to a mechanic entry.
    
    Args:
        ledger: The ledger dict
        category: The mechanic category
        mode: The operating mode
        
    Returns:
        Updated ledger dict
        
    Raises:
        ValueError: If category not found or invalid mode
    """
    if category not in MECHANIC_CATEGORIES:
        raise ValueError(f"Unknown mechanic category: {category}")
    
    if mode not in ["AI Helper", "Semi-Autonomous", "Fully Autonomous"]:
        raise ValueError(f"Invalid mode: {mode}. Must be one of AI Helper, Semi-Autonomous, Fully Autonomous")
    
    for entry in ledger["mechanics"]:
        if entry["category"] == category:
            entry["mode"] = mode
            return ledger
    
    raise ValueError(f"Mechanic category not found: {category}")


def add_result_verification(
    ledger: dict[str, Any],
    category: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Add result verification data to a mechanic entry.
    
    Args:
        ledger: The ledger dict
        category: The mechanic category
        result: The result verification data
        
    Returns:
        Updated ledger dict
        
    Raises:
        ValueError: If category not found or invalid
    """
    if category not in MECHANIC_CATEGORIES:
        raise ValueError(f"Unknown mechanic category: {category}")
    
    for entry in ledger["mechanics"]:
        if entry["category"] == category:
            entry["result_verified"] = result
            return ledger
    
    raise ValueError(f"Mechanic category not found: {category}")


def add_regression_evidence(
    ledger: dict[str, Any],
    category: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """
    Add regression test evidence to a mechanic entry.
    
    Args:
        ledger: The ledger dict
        category: The mechanic category
        evidence: The regression test evidence
        
    Returns:
        Updated ledger dict
        
    Raises:
        ValueError: If category not found or invalid
    """
    if category not in MECHANIC_CATEGORIES:
        raise ValueError(f"Unknown mechanic category: {category}")
    
    for entry in ledger["mechanics"]:
        if entry["category"] == category:
            entry["regression_evidence"] = evidence
            return ledger
    
    raise ValueError(f"Mechanic category not found: {category}")
