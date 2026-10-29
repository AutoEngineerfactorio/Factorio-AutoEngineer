"""Conservative UPS admission policy for a *single graphical Factorio host*.

Pure logic: no game I/O, process changes or autonomous permissions. Consume
verified game ticks and monotonic timestamps, then use the returned budget
before scheduling OPTIONAL AI/catalog/map work. Unknown UPS means no heavy AI.
This is not an UPS guarantee and never authorizes game actions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

MIN_SAMPLE_SECONDS = 4.0
DEGRADE_UPS = 58.0
RECOVER_UPS = 59.5
CRITICAL_UPS = 52.0

#: The lowest UPS target a threshold set may be built around. A target
#: below this would mean the game is not being asked to run at 60 UPS
#: and the protective thresholds would lose their meaning.
MIN_UPS_TARGET = 30.0

#: The smallest gap the thresholds must keep between each other. The
#: hysteresis needs a band, otherwise the guard would flap between two
#: states on every sample.
MIN_THRESHOLD_GAP = 0.5


@dataclass(frozen=True)
class UPSThresholds:
    """The UPS levels at which the guard changes its behaviour.

    The three levels are ordered and they must all sit below the target.
    A configuration that violates either rule is **refused**: the guard
    falls back to the protective defaults instead of running with a
    threshold that could disable the protection.
    """

    target: float
    degrade: float
    recover: float
    critical: float

    @classmethod
    def validated(
        cls,
        target: Any,
        degrade: Any,
        recover: Any,
        critical: Any,
    ) -> "UPSThresholds":
        """Return the thresholds, or the protective defaults when unsafe."""
        default = cls(
            target=60.0, degrade=DEGRADE_UPS, recover=RECOVER_UPS,
            critical=CRITICAL_UPS)
        try:
            values = (float(target), float(degrade), float(recover),
                      float(critical))
        except (TypeError, ValueError):
            return default
        if any(not math.isfinite(value) for value in values):
            return default
        target_value, degrade_value, recover_value, critical_value = values
        if target_value < MIN_UPS_TARGET:
            return default
        if not (critical_value < degrade_value < recover_value):
            return default
        if recover_value - degrade_value < MIN_THRESHOLD_GAP:
            return default
        if recover_value > target_value:
            return default
        return cls(
            target=target_value, degrade=degrade_value,
            recover=recover_value, critical=critical_value)

    @classmethod
    def from_settings(cls, settings: Any) -> "UPSThresholds":
        """Return the thresholds the stored settings describe.

        A settings file that is missing, broken or unsafe yields the
        protective defaults. The guard is never left without a
        protection because a setting was wrong.
        """
        try:
            return cls.validated(
                settings.get("ups_target"),
                settings.get("ups_degrade_threshold"),
                settings.get("ups_recover_threshold"),
                settings.get("ups_critical_threshold"),
            )
        except Exception:
            return cls.validated(60.0, DEGRADE_UPS, RECOVER_UPS, CRITICAL_UPS)

    def as_dict(self) -> dict[str, float]:
        """Return the thresholds as a plain dictionary."""
        return {
            "target": self.target,
            "degrade": self.degrade,
            "recover": self.recover,
            "critical": self.critical,
        }


@dataclass(frozen=True)
class WorkBudget:
    state: str
    estimated_ups: float | None
    ai_allowed: bool
    catalog_allowed: bool
    telemetry_seconds: float
    map_seconds: float
    min_ai_seconds: float
    reason: str


_BUDGETS = {
    "unknown": (False, False, 4.0, 12.0, 30.0),
    "healthy": (True, True, 2.0, 4.0, 8.0),
    "degraded": (False, False, 5.0, 12.0, 30.0),
    "critical": (False, False, 10.0, 30.0, 60.0),
}


class UPSGuard:
    """Hysteresis prevents rapid AI stop/start at the 60 UPS boundary.

    Derived tick rate is an *estimate*, not the graphical client's FPS.
    A paused game, a TimeTools speed change, or a loading screen can make
    the rate unlike normal UPS. Any uncertainty favors reduced background
    work, without stopping the Factorio process.
    """

    def __init__(self, *, window_seconds: float = MIN_SAMPLE_SECONDS,
                 degrade_after: int = 2, recover_after: int = 3,
                 thresholds: UPSThresholds | None = None):
        if not math.isfinite(window_seconds) or window_seconds < 2:
            raise ValueError("Sample window must be at least two seconds")
        if degrade_after < 1 or recover_after < 1:
            raise ValueError("Hysteresis counts must be positive")
        self.window_seconds = window_seconds
        self.degrade_after = degrade_after
        self.recover_after = recover_after
        #: The levels at which the guard changes its behaviour. The
        #: defaults are the protective ones; a configuration is only used
        #: when it is safe, and an unsafe one is refused by
        #: :meth:`UPSThresholds.validated`.
        self.thresholds = thresholds if thresholds is not None \
            else UPSThresholds.validated(
                60.0, DEGRADE_UPS, RECOVER_UPS, CRITICAL_UPS)
        self._tick: int | None = None
        self._at: float | None = None
        self._bad = 0
        self._good = 0
        self._rate: float | None = None
        self._state = "unknown"

    @property
    def state(self) -> str:
        return self._state

    def reset(self) -> None:
        """Invalidate measurements on disconnect, save switch or reconnect."""
        self._tick = None
        self._at = None
        self._bad = 0
        self._good = 0
        self._rate = None
        self._state = "unknown"

    def observe(self, tick: int, at: float) -> WorkBudget:
        """Accept one genuine game tick and local monotonic clock reading.

        Repeated, out-of-order or too-close samples do not improve the
        health state. A backwards tick resets rather than mixing worlds.
        """
        if type(tick) is not int or tick < 0:
            raise ValueError("Tick must be a nonnegative integer")
        if not isinstance(at, (float, int)) or not math.isfinite(at):
            raise ValueError("Clock must be finite")
        now = float(at)
        if self._tick is None:
            self._tick, self._at = tick, now
            return self.budget()
        assert self._at is not None
        if now <= self._at:
            return self.budget()
        if tick < self._tick:
            self.reset()
            self._tick, self._at = tick, now
            return self.budget()
        seconds = now - self._at
        if seconds < self.window_seconds:
            return self.budget()
        ups = (tick - self._tick) / seconds
        self._tick, self._at = tick, now
        # Implausible large leaps may indicate a different game or time warp.
        if ups > 180.0:
            self.reset()
            self._tick, self._at = tick, now
            return self.budget()
        self._rate = ups
        if ups < self.thresholds.critical:
            self._state = "critical"
            self._good = 0
            self._bad = 0
        elif ups < self.thresholds.degrade:
            self._bad += 1
            self._good = 0
            if self._bad >= self.degrade_after:
                self._state = "degraded"
        elif ups >= self.thresholds.recover:
            self._good += 1
            self._bad = 0
            if self._good >= self.recover_after:
                self._state = "healthy"
        else:
            self._good = 0
            self._bad = 0
        return self.budget()

    def budget(self) -> WorkBudget:
        ai, catalog, telemetry, map_period, min_ai = _BUDGETS[self._state]
        return WorkBudget(
            state=self._state, estimated_ups=self._rate,
            ai_allowed=ai, catalog_allowed=catalog,
            telemetry_seconds=telemetry, map_seconds=map_period,
            min_ai_seconds=min_ai,
            reason={
                "unknown": "Insufficient trustworthy tick samples",
                "healthy": "Game tick rate stable; optional work admitted",
                "degraded": "Game is behind target; optional work paused",
                "critical": "Severe tick deficit or game paused; optional work paused",
            }[self._state],
        )


def owned_process_creationflags(name: str, *, windows: bool,
                                no_window: int = 0,
                                below_normal: int = 0) -> int:
    """Lower *new launcher-owned* inference process priority only.

    The graphical Factorio process, interactive dashboard, attached models,
    arbitrary PIDs and system-wide scheduling are never changed.
    """
    if not windows:
        return 0
    return no_window | (below_normal if name == "llama" else 0)


def guard_from_settings(settings: Any = None) -> UPSGuard:
    """Return a guard that uses the thresholds the settings describe.

    The settings are read from the store when none are given. A missing,
    broken or unsafe configuration yields the protective defaults, so the
    guard always keeps its protection.
    """
    if settings is None:
        try:
            from settings_store import effective_settings

            settings = effective_settings()
        except Exception:
            settings = None
    thresholds = UPSThresholds.from_settings(settings)
    return UPSGuard(thresholds=thresholds)
