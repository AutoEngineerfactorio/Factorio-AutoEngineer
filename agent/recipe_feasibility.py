"""Recipe feasibility over an observed Factorio 2.1.23 catalog.

A recipe can exist, be enabled, be unlocked, and still not be craftable
right now. This module separates those questions and reports what the
observed catalog can actually establish.

The statuses are deliberately coarse and never optimistic:

* ``available`` - the observed data shows the recipe can be used now.
* ``locked`` - the recipe exists but a known prerequisite is missing.
* ``unavailable`` - the recipe itself is disabled or hidden.
* ``unknown`` - a requirement could not be verified from the observed data.

A requirement that cannot be checked is reported as ``unknown``. It is never
reported as satisfied and never as impossible.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

# The observed recipe catalog carries the crafting categories a recipe
# belongs to, and the technologies that unlock it. It does not carry the
# machine prototypes, so the machine availability cannot be verified from
# the catalog alone.
FeasibilityStatus = str

STATUS_AVAILABLE = "available"
STATUS_LOCKED = "locked"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Feasibility:
    """The feasibility of one observed recipe."""

    status: FeasibilityStatus
    reasons: tuple[str, ...] = field(default_factory=tuple)
    blocked_by: tuple[str, ...] = field(default_factory=tuple)
    categories: tuple[str, ...] = field(default_factory=tuple)
    unlock_technologies: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def is_usable(self) -> bool:
        """True only when the recipe can be used now."""
        return self.status == STATUS_AVAILABLE

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe description of the feasibility."""
        return {
            "status": self.status,
            "is_usable": self.is_usable,
            "reasons": list(self.reasons),
            "blocked_by": list(self.blocked_by),
            "categories": list(self.categories),
            "unlock_technologies": [dict(row) for row in self.unlock_technologies],
        }


def assess_recipe(
    recipe: dict[str, Any],
    observed_research: Optional[set[str]] = None,
) -> Feasibility:
    """Return the feasibility of one observed recipe.

    ``observed_research`` is the set of technologies the backend reported as
    researched. When it is None the research state is unknown and an
    unlocked recipe is reported as unknown rather than available.
    """
    reasons: list[str] = []
    blocked_by: list[str] = []

    if not recipe.get("enabled", False):
        reasons.append("the recipe is disabled in the observed game data")
    if recipe.get("hidden", False):
        reasons.append("the recipe is hidden in the observed game data")

    raw_unlocks = recipe.get("unlock_technologies") or []
    unlocks: tuple[dict[str, Any], ...] = tuple(
        dict(row) for row in raw_unlocks if isinstance(row, dict)
    )
    raw_categories = recipe.get("categories") or []
    categories: tuple[str, ...] = tuple(
        value for value in raw_categories if isinstance(value, str)
    )
    if not categories and recipe.get("category"):
        categories = (recipe["category"],)

    if recipe.get("enabled", False) and recipe.get("hidden", False) is False:
        # The recipe itself is usable. The unlock technologies decide
        # whether it is unlocked yet.
        if not unlocks:
            status = STATUS_AVAILABLE
        elif observed_research is None:
            status = STATUS_UNKNOWN
            reasons.append(
                "the unlock technologies were observed but the researched "
                "technology set was not, so the unlock state is unknown"
            )
        else:
            missing = sorted(
                unlock["name"] for unlock in unlocks
                if not unlock.get("researched", False)
            )
            disabled = sorted(
                unlock["name"] for unlock in unlocks
                if not unlock.get("enabled", True)
            )
            blocked_by.extend(missing)
            blocked_by.extend(disabled)
            if disabled:
                status = STATUS_LOCKED
                reasons.append(
                    "an unlock technology is disabled: " + ", ".join(disabled)
                )
            elif missing:
                status = STATUS_LOCKED
                reasons.append(
                    "the unlock technology is not researched: "
                    + ", ".join(missing)
                )
            else:
                status = STATUS_AVAILABLE
    else:
        status = STATUS_UNAVAILABLE

    # A compatible crafting machine cannot be established from the recipe
    # catalog, so it is reported as unknown rather than assumed.
    if status == STATUS_AVAILABLE:
        reasons.append(
            "a compatible crafting machine for category "
            f"{categories[0] if categories else 'unknown'} was not verified "
            "from the observed catalog"
        )

    return Feasibility(
        status=status,
        reasons=tuple(reasons),
        blocked_by=tuple(sorted(set(blocked_by))),
        categories=categories,
        unlock_technologies=unlocks,
    )


def assess_recipes(
    recipes: list[dict[str, Any]],
    observed_research: Optional[set[str]] = None,
) -> dict[str, Feasibility]:
    """Return the feasibility of every observed recipe, keyed by name."""
    return {
        recipe["name"]: assess_recipe(recipe, observed_research)
        for recipe in recipes
    }


def usable_recipe_names(
    recipes: list[dict[str, Any]],
    observed_research: Optional[set[str]] = None,
) -> set[str]:
    """Return the names of the recipes that are usable right now."""
    return {
        name for name, entry in assess_recipes(recipes, observed_research).items()
        if entry.is_usable
    }
