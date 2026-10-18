"""
R04 Capability Snapshot — Read-only bounded game observations with deterministic fingerprints.

This module provides read-only access to game capability data (version, force, research,
recipes, machines, items, fluids, quality, surface) with explicit freshness tracking,
deterministic fingerprinting, and strict contract enforcement. No gameplay actions are
performed; all observations are derived from MCP tool responses.

Acceptance criteria (R04):
- Observations are read-only and bounded
- Fingerprints are deterministic (SHA256 with sorted keys)
- Stale/offline states are explicit (live/stale/unavailable)
Acceptance criteria (R04):
1. Observations are read-only and bounded
2. Fingerprints are deterministic
3. Stale/offline states are explicit
4. Missing recipes are never invented
5. Strict contract is enforced
"""

import hashlib
import json
from typing import Any, Literal

# Status enum for capability snapshots
Status = Literal["live", "stale", "unavailable"]


def _contains_control_characters(s: str) -> bool:
    """Check if string contains control characters (except common whitespace)."""
    for char in s:
        code = ord(char)
        # Allow common whitespace (space, tab, newline, carriage return)
        if code not in (32, 9, 10, 13):
            # Control characters are 0-31 except the allowed ones
            if code < 32:
                return True
    return False


def _create_canonical_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """
    Create a canonical profile representation for deterministic fingerprinting.
    
    Args:
        profile: The capability profile dict with game_version, force, surface, research
        
    Returns:
        A canonical dict with sorted keys and sorted research list
        
    Raises:
        ValueError: If any field is invalid (empty, too long, contains control chars)
    """
    # Sort research list for consistent ordering
    sorted_research = sorted(profile.get("research", []))
    
    # Build canonical structure with sorted keys
    canonical = {
        "game_version": profile["game_version"],
        "force": profile["force"],
        "surface": profile["surface"],
        "research": sorted_research,
    }
    
    # Validate string lengths
    for key in ["game_version", "force", "surface"]:
        value = canonical[key]
        if not isinstance(value, str) or len(value) > 128 or len(value) == 0:
            raise ValueError(f"Invalid {key}: must be nonempty string <=128 chars")
        if _contains_control_characters(value):
            raise ValueError(f"{key} contains control characters")
    
    return canonical


def _compute_fingerprint(canonical: dict[str, Any]) -> str:
    """
    Compute a deterministic SHA256 fingerprint from canonical profile.
    
    Args:
        canonical: The canonical profile dict with sorted keys
        
    Returns:
        Hex digest SHA256 fingerprint string
    """
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    profile_fingerprint = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return profile_fingerprint


def assess_capability_snapshot(
    snapshot: dict[str, Any],
    now: float,
    max_age: float = 5.0,
) -> dict[str, Any]:
    """
    Assess a capability snapshot and compute its status, usability, and fingerprint.
    
    This function is purely read-only and bounded to the snapshot data.
    It does not mutate any game state or write to files.
    
    Args:
        snapshot: A dict containing capability snapshot data with keys:
            - schema: int (must be exactly 1, not bool True)
            - observed_at: float (finite nonnegative timestamp)
            - now: float (current timestamp, must be >= observed_at)
            - snapshot: dict (optional, for fingerprint computation)
            
    Returns:
        dict with keys:
            - status: Literal["live", "stale", "unavailable"]
            - fingerprint: str (SHA256 hex digest, or None if snapshot missing)
            - usable: bool (True if status is "live" and age <= max_age)
            - age: float (snapshot age in seconds)
            - snapshot: dict (original snapshot, unchanged)
            
    Raises:
        ValueError: If snapshot schema is invalid, observed_at is negative,
                   or now < observed_at
    """
    # Validate snapshot schema
    schema = snapshot.get("schema")
    # Explicitly reject bool (bool is subclass of int in Python)
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != 1:
        raise ValueError("snapshot['schema'] must be int 1, not bool True or other")
    
    # Validate timestamps
    observed_at = snapshot.get("observed_at")
    if not isinstance(observed_at, (int, float)) or observed_at < 0:
        raise ValueError("snapshot['observed_at'] must be nonnegative float")
    
    if now < observed_at:
        raise ValueError("now must be >= observed_at")
    
    # Compute age
    age = now - observed_at
    
    # Determine status based on age
    if age > 60.0:
        status = "unavailable"
    elif age > max_age:
        status = "stale"
    else:
        status = "live"
    
    # Compute fingerprint if snapshot provided
    fingerprint = None
    if snapshot is not None:
        canonical = _create_canonical_profile(snapshot)
        fingerprint = _compute_fingerprint(canonical)
    
    # Compute usability
    usable = (status == "live") and (age <= max_age)
    
    return {
        "status": status,
        "fingerprint": fingerprint,
        "usable": usable,
        "age": age,
        "snapshot": snapshot,
    }
