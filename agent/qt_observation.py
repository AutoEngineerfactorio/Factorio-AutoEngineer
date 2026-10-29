"""The observation state model for the read-only Qt dashboard.

This module is deliberately free of any Qt import. It holds the rule that
the whole interface depends on: **an unobserved value is unknown, never
zero**. The dashboard must never show a number the game did not report, and
it must never show a derived number as if the game had reported it.

Every value carries one of four states:

``observed``
    The game reported this value and it is still fresh.

``estimated``
    The value was derived from observed data by a documented rule. The
    derivation is named, because an estimate with no stated derivation is
    indistinguishable from a guess.

``stale``
    The value **was** observed but has aged past its freshness window. The
    last known number survives, but it is never presented as current.

``unavailable``
    The value was not observed. It is unknown. It renders as an em dash and
    never as ``0``.

The model is pure logic, so it is verifiable offline, without a display
server and without a running Factorio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

OBSERVED = "observed"
ESTIMATED = "estimated"
UNAVAILABLE = "unavailable"
STALE = "stale"

OBSERVATION_STATES = (OBSERVED, ESTIMATED, UNAVAILABLE, STALE)
"""Every state an observed value can be in."""


def is_known(state: str) -> bool:
    """Whether a state carries a real number.

    ``unavailable`` is *unknown*. It is never treated as a zero value.
    """
    return state in (OBSERVED, ESTIMATED, STALE)


@dataclass(frozen=True)
class Observation:
    """One dashboard value together with how it was obtained.

    ``value`` is ``None`` when the value is unknown. ``state`` says whether
    the number was observed, estimated, aged out or is unavailable, and
    ``detail`` carries the human-readable reason, the derivation or the
    freshness.
    """

    value: Any = None
    state: str = UNAVAILABLE
    detail: str = "Not observed"
    observed_at: float = 0.0
    age_seconds: float = float("inf")
    source: str = ""

    @property
    def known(self) -> bool:
        """Whether this observation carries a real value."""
        return self.value is not None and is_known(self.state)

    @property
    def fresh(self) -> bool:
        """Whether this observation is current rather than aged out."""
        return self.state == OBSERVED

    @property
    def estimated(self) -> bool:
        """Whether this value was derived rather than read directly."""
        return self.state == ESTIMATED

    def display(self, formatter=None) -> str:
        """Return the text the interface shows for this observation.

        An unknown value renders as an em dash, never as ``0``. That single
        rule is what keeps "not observed" and "observed zero" apart.
        """
        if not self.known:
            return "—"
        if formatter is not None:
            return formatter(self.value)
        if isinstance(self.value, float):
            if not math.isfinite(self.value):
                return "—"
            return f"{self.value:,.2f}"
        return str(self.value)

    def badge(self) -> str:
        """Return the short state badge shown next to the value."""
        return {
            OBSERVED: "observed",
            ESTIMATED: "estimated",
            STALE: "stale",
            UNAVAILABLE: "unavailable",
        }[self.state]

    def badge_object_name(self) -> str:
        """Return the Qt object name of the badge style for this state."""
        return {
            OBSERVED: "badgeObserved",
            ESTIMATED: "badgeEstimated",
            STALE: "badgeStale",
            UNAVAILABLE: "badgeUnavailable",
        }[self.state]


def observed(value: Any, detail: str = "Observed", *, source: str = "",
             observed_at: float = 0.0) -> Observation:
    """Build an observed value."""
    return Observation(value=value, state=OBSERVED, detail=detail,
                       observed_at=observed_at, source=source)


def estimated(value: Any, detail: str, *, source: str = "",
              observed_at: float = 0.0) -> Observation:
    """Build a value derived from observed data.

    The derivation must be named in ``detail``. An estimate with no stated
    derivation is indistinguishable from a guess, so it is not accepted.
    """
    if not detail:
        raise ValueError("An estimated value must name its derivation")
    return Observation(value=value, state=ESTIMATED, detail=detail,
                       observed_at=observed_at, source=source)


def unavailable(detail: str = "Not observed", *, source: str = "") -> Observation:
    """Build an unknown value. The value is ``None``, never zero."""
    return Observation(value=None, state=UNAVAILABLE, detail=detail, source=source)


def stale(last: Observation, age_seconds: float, detail: str = "") -> Observation:
    """Age a previous observation out, keeping its last known number.

    The number survives, but the state says it is stale, so the interface
    can show it greyed out and dated. A stale observation is never silently
    promoted back to observed.
    """
    if not last.known:
        return unavailable(detail or last.detail, source=last.source)
    return Observation(
        value=last.value,
        state=STALE,
        detail=detail or f"Last observed {age_seconds:.0f}s ago",
        observed_at=last.observed_at,
        age_seconds=age_seconds,
        source=last.source,
    )


def optional_number(container: Mapping[str, Any] | None, key: str
                    ) -> float | None:
    """Return a finite number from a mapping, or ``None`` when absent.

    A field that is absent means *unknown*. It never means zero, and a
    boolean is never accepted as a number.
    """
    if not isinstance(container, Mapping):
        return None
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def optional_int(container: Mapping[str, Any] | None, key: str) -> int | None:
    """Return an integer from a mapping, or ``None`` when absent."""
    if not isinstance(container, Mapping):
        return None
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def optional_text(container: Mapping[str, Any] | None, key: str,
                  limit: int = 128) -> str | None:
    """Return a bounded, printable string from a mapping, or ``None``."""
    if not isinstance(container, Mapping):
        return None
    value = container.get(key)
    if not isinstance(value, str) or not value:
        return None
    if len(value) > limit:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    return value


def age_of(last: Observation, now: float) -> float:
    """Return the age of a previous observation in seconds.

    An observation that was never made has no age, so the age is infinite
    rather than zero. A zero age would read as "just observed", which is
    exactly the claim that must never be made about a missing value.
    """
    if not last.known or not last.observed_at:
        return float("inf")
    return max(0.0, now - last.observed_at)


def refresh(last: Observation, now: float, ttl: float,
            replacement: Observation | None = None) -> Observation:
    """Return a fresh observation, or age the previous one out.

    ``replacement`` is the newly observed value. When it is ``None`` the
    previous observation is aged out instead, so a failed refresh produces
    a **stale** value rather than a fresh-looking old one.
    """
    if replacement is not None:
        return replacement
    age = age_of(last, now)
    if age <= ttl:
        return last
    return stale(last, age)


__all__ = [
    "ESTIMATED",
    "OBSERVATION_STATES",
    "OBSERVED",
    "STALE",
    "UNAVAILABLE",
    "Observation",
    "age_of",
    "estimated",
    "is_known",
    "observed",
    "optional_int",
    "optional_number",
    "optional_text",
    "refresh",
    "stale",
    "unavailable",
]
