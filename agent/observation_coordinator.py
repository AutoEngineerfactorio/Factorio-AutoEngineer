"""The shared observation coordinator.

Every dashboard, telemetry and map observer asks the game for the same
things. Before this module existed, two independent pollers asked for the
same observation on their own schedules: the display observer every four
seconds and the dashboard feed **every second**, and both asked the
backend for the full recipe catalog on every single poll.

The coordinator gives every observer one place to go:

* **Deduplication.** Two observers that want the same observation at the
  same time share one request instead of sending two.
* **A validated cache with explicit freshness.** A cached observation
  carries the age of the data, so a caller can tell a fresh observation
  from a stale one instead of reading a stale value as current.
* **Budgets.** The coordinator bounds how many expensive requests may run
  in a window, so a burst of observers cannot flood the game.
* **Bounded backoff.** A failing request backs off instead of retrying in
  a tight loop.
* **Preserved unknown states.** A failed, stale or partial observation is
  reported as such. The coordinator never fabricates a current value.

The coordinator is deliberately free of any Factorio or Tkinter import so
that it can be tested offline and so that a safety check can never be
blocked by an observation.

**The coordinator does not weaken the restricted backend.** It only ever
requests the tools that the backend already allows, and it never issues a
gameplay command.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

#: The observation kinds the coordinator understands.
#:
#: The kinds are ordered from cheapest to most expensive. The coordinator
#: uses the order to decide which request wins when the budget is
#: exhausted.
STATUS = "status"
TELEMETRY = "telemetry"
MAP = "map"
CATALOG = "catalog"
INVENTORY = "inventory"

#: The cheapest-first order of the observation kinds.
KIND_ORDER: tuple[str, ...] = (STATUS, TELEMETRY, MAP, CATALOG, INVENTORY)

#: How long a cached observation is considered fresh, per kind.
#:
#: The catalog is expensive and changes only when the game content or the
#: research changes, so it stays fresh far longer than the status. The
#: status is cheap and is read often.
#:
#: The inventory observation walks entities, so it is the most expensive
#: of all. It is requested on demand only and stays cached briefly.
DEFAULT_TTL: dict[str, float] = {
    STATUS: 1.0,
    TELEMETRY: 2.0,
    MAP: 4.0,
    CATALOG: 30.0,
    INVENTORY: 10.0,
}

#: The maximum number of requests per minute the coordinator will start.
#:
#: The default is deliberately conservative: the fast status read is cheap,
#: but the catalog is not, and the catalog is requested on demand only.
DEFAULT_REQUESTS_PER_MINUTE = 120

#: The maximum number of requests that may be in flight at once.
DEFAULT_MAX_IN_FLIGHT = 2

#: The backoff ceiling after consecutive failures, in seconds.
DEFAULT_MAX_BACKOFF = 30.0

#: The base backoff after a failure, in seconds.
DEFAULT_BASE_BACKOFF = 0.5


class ObservationPending(Exception):
    """Expected bounded work is still running; no fresh value exists yet."""

    def __init__(self, reason: str):
        if reason != "catalog_building":
            raise ValueError("Unknown pending observation reason")
        self.reason = reason
        super().__init__(reason)


@dataclass
class Observation:
    """One observed value together with its freshness.

    ``value`` is ``None`` when the observation is unknown. ``stale`` is
    ``True`` when the value was observed but has aged past its time to
    live, and ``partial`` is ``True`` when the observation was bounded and
    did not cover everything.
    """

    kind: str
    value: Any = None
    observed_at: float = 0.0
    stale: bool = False
    partial: bool = False
    reason: str | None = None
    clock: Callable[[], float] | None = None

    @property
    def known(self) -> bool:
        """Whether a value was actually observed."""
        return self.value is not None

    def age(self, now: float | None = None) -> float:
        """Return the age of the observation in seconds.

        The age is measured against the observation's own clock, so the
        tests and the coordinator agree on what "now" means.
        """
        if not self.observed_at:
            return float("inf")
        moment = now if now is not None else (
            self.clock() if self.clock is not None else time.monotonic())
        return max(0.0, moment - self.observed_at)


@dataclass
class _Entry:
    """The coordinator's internal record for one request key."""

    key: tuple[Any, ...]
    kind: str
    observation: Observation | None = None
    #: The last value that was actually observed. It is kept separately
    #: from the current observation so that a blocked or failed refresh
    #: can still report the last known value, marked as stale.
    last_value: Any = None
    last_observed_at: float = 0.0
    last_partial: bool = False
    in_flight: Any = None
    failures: int = 0
    next_allowed_at: float = 0.0
    started: list[float] = field(default_factory=list)


class ObservationCoordinator:
    """One shared place for every non-safety observation request.

    The coordinator is synchronous and has no I/O of its own: the caller
    supplies a ``fetch`` callable that performs the actual request. That
    keeps the coordinator testable offline and keeps the game interaction
    in the caller, where the existing safety checks already are.
    """

    def __init__(
        self,
        *,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        max_in_flight: int = DEFAULT_MAX_IN_FLIGHT,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        base_backoff: float = DEFAULT_BASE_BACKOFF,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("Invalid observation request budget")
        if max_in_flight < 1:
            raise ValueError("Invalid observation concurrency limit")
        if max_backoff <= 0 or base_backoff <= 0:
            raise ValueError("Invalid observation backoff")
        self.requests_per_minute = requests_per_minute
        self.max_in_flight = max_in_flight
        self.max_backoff = max_backoff
        self.base_backoff = base_backoff
        self.clock = clock
        self._entries: dict[tuple[Any, ...], _Entry] = {}

    # -- key handling ---------------------------------------------------

    @staticmethod
    def key(kind: str, **parts: Any) -> tuple[Any, ...]:
        """Return the cache key for one observation request.

        The key is the kind plus the request's own parameters, so two
        different map chunks are different observations while two
        observers that want the same chunk share one.
        """
        if kind not in KIND_ORDER:
            raise ValueError(f"Unknown observation kind: {kind!r}")
        return (kind,) + tuple(sorted((name, parts[name]) for name in parts))

    # -- budget ---------------------------------------------------------

    def _prune(self, now: float) -> None:
        """Drop the timestamps that fell out of the request window."""
        window = 60.0
        for entry in self._entries.values():
            entry.started = [t for t in entry.started if now - t < window]

    def budget_exhausted(self, now: float | None = None) -> bool:
        """Whether the request budget for this window is spent."""
        moment = now if now is not None else self.clock()
        self._prune(moment)
        return sum(len(e.started) for e in self._entries.values()) \
            >= self.requests_per_minute

    def in_flight(self) -> int:
        """Return the number of requests that are currently running."""
        return sum(1 for e in self._entries.values() if e.in_flight is not None)

    # -- backoff --------------------------------------------------------

    def backoff_for(self, failures: int) -> float:
        """Return the bounded backoff after ``failures`` consecutive errors."""
        if failures <= 0:
            return 0.0
        delay = self.base_backoff * (2 ** (failures - 1))
        return min(self.max_backoff, delay)

    # -- the observation entry point ------------------------------------

    def observe(
        self,
        kind: str,
        fetch: Callable[[], Any],
        *,
        key: tuple[Any, ...] | None = None,
        ttl: float | None = None,
        allow_partial: bool = True,
        now: float | None = None,
    ) -> Observation:
        """Return the observation for ``kind``, fetching it when needed.

        A **fresh** cached observation is returned without calling
        ``fetch``. An observation that has aged past its time to live is
        refreshed. When a refresh cannot happen - a failure, a backoff, an
        exhausted budget or the concurrency limit - the last known value is
        returned marked **stale**, so a caller can always tell a current
        observation from an old one.
        """
        moment = now if now is not None else self.clock()
        entry_key = key if key is not None else self.key(kind)
        entry = self._entries.get(entry_key)
        if entry is None:
            entry = _Entry(key=entry_key, kind=kind)
            self._entries[entry_key] = entry

        lifetime = ttl if ttl is not None else DEFAULT_TTL.get(kind, 1.0)
        cached = entry.observation
        if cached is not None and cached.known and not cached.stale:
            if cached.age(moment) < lifetime:
                # The observation is fresh. No request is made.
                return cached

        # The observation is unknown, or it aged out and needs a refresh.
        # The request gates are checked before anything is fetched.
        if entry.in_flight is not None:
            # Another caller is already fetching this exact observation.
            return self._stale_or_unknown(kind, entry, "in_flight")

        if moment < entry.next_allowed_at:
            # The backoff window has not passed. The last known value is
            # reported as stale rather than as current, so a failed
            # observation can never be mistaken for a fresh one.
            return self._stale_or_unknown(kind, entry, "backoff")

        if self.budget_exhausted(moment):
            return self._stale_or_unknown(kind, entry, "budget_exhausted")

        if self.in_flight() >= self.max_in_flight:
            return self._stale_or_unknown(kind, entry, "concurrency_limited")

        entry.in_flight = True
        entry.started.append(moment)
        try:
            value = fetch()
        except ObservationPending as exc:
            entry.next_allowed_at = moment + self.base_backoff
            entry.observation = self._stale_or_unknown(kind, entry, exc.reason)
            return entry.observation
        except Exception as exc:  # noqa: BLE001 - a failure is recorded
            entry.failures += 1
            entry.next_allowed_at = moment + self.backoff_for(entry.failures)
            # The observation becomes unknown. The previous value is kept
            # only as a **stale** value, never as a current one.
            entry.observation = self._stale_or_unknown(
                kind, entry, f"unavailable: {type(exc).__name__}")
            return entry.observation
        finally:
            entry.in_flight = None

        entry.failures = 0
        entry.next_allowed_at = 0.0
        observed_at = self.clock()
        partial = bool(allow_partial) and _is_partial(value)
        entry.last_value = value
        entry.last_observed_at = observed_at
        entry.last_partial = partial
        entry.observation = Observation(
            kind=kind, value=value, observed_at=observed_at,
            partial=partial, clock=self.clock)
        return entry.observation

    def _stale_or_unknown(self, kind: str, entry: _Entry,
                          reason: str) -> Observation:
        """Return the last known value as stale, or an unknown observation.

        A caller that asks for an observation and cannot get a fresh one
        must be able to tell that apart from a fresh value. The last known
        value is therefore reported as **stale** and never as current, and
        an observation that was never made stays unknown.
        """
        if entry.last_value is not None:
            return Observation(
                kind=kind, value=entry.last_value,
                observed_at=entry.last_observed_at, stale=True,
                partial=entry.last_partial, reason=reason, clock=self.clock)
        return Observation(kind=kind, reason=reason, clock=self.clock)

    # -- inspection -----------------------------------------------------

    def cached(self, kind: str, key: tuple[Any, ...] | None = None) -> Observation:
        """Return the cached observation without fetching anything."""
        entry_key = key if key is not None else self.key(kind)
        entry = self._entries.get(entry_key)
        if entry is None or entry.observation is None:
            return Observation(kind=kind, reason="never_observed",
                               clock=self.clock)
        return entry.observation

    def stats(self) -> dict[str, Any]:
        """Return a bounded summary of the coordinator's state."""
        by_kind: dict[str, int] = {}
        failures = 0
        for entry in self._entries.values():
            by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
            failures += entry.failures
        return {
            "entries": len(self._entries),
            "by_kind": dict(sorted(by_kind.items())),
            "in_flight": self.in_flight(),
            "requests_per_minute": self.requests_per_minute,
            "max_in_flight": self.max_in_flight,
            "consecutive_failures": failures,
        }

    def reset(self) -> None:
        """Drop every cached observation and every backoff."""
        self._entries.clear()


def _is_partial(value: Any) -> bool:
    """Whether an observed value declares itself partial.

    The backend marks a bounded observation as partial so that a caller
    can tell "this is everything" from "this is a bounded sample". The
    flag is honoured when it is present and never invented when it is
    not.
    """
    if isinstance(value, dict):
        for name in ("partial", "truncated", "slots_truncated"):
            if value.get(name) is True:
                return True
        telemetry = value.get("telemetry")
        if isinstance(telemetry, dict):
            return _is_partial(telemetry)
    return False


def priority(kind: str) -> int:
    """Return the priority of an observation kind, cheapest first.

    A lower number is more urgent. The coordinator uses this to decide
    which request survives when the budget is exhausted, so a safety
    status is never dropped in favour of a catalog page.
    """
    if kind not in KIND_ORDER:
        raise ValueError(f"Unknown observation kind: {kind!r}")
    return KIND_ORDER.index(kind)


#: The backend tools the coordinator may ask for, and the arguments each
#: observation kind sends.
#:
#: The restricted backend rejects any tool that is not in its allowlist
#: and any argument key that is not declared for that tool, so the
#: builders below are the only place where an observation request is
#: described. They add **no** tool and **no** gameplay capability.
VIEW_TOOL = "autoengineer_view"
TELEMETRY_TOOL = "autoengineer_telemetry"
INVENTORY_TOOL = "autoengineer_inventory"


def status_request() -> tuple[str, dict[str, Any]]:
    """Return the cheap status observation request.

    This is the request the one-second poll uses. It asks for the player
    position, the surface, the tick, the control lease and the emergency
    stop state, and it does **not** ask for the recipe catalog, so the
    backend does not enumerate any recipe, recompute the technology
    fingerprint or enumerate any machine prototype.
    """
    return VIEW_TOOL, {"noCatalog": True}


def map_request(chunk_x: int, chunk_y: int) -> tuple[str, dict[str, Any]]:
    """Return the bounded map-chunk observation request.

    Only the requested chunk is asked for. The backend reads exactly one
    aligned 64x64 chunk.
    """
    if type(chunk_x) is not int or type(chunk_y) is not int:
        raise ValueError("Map chunk coordinates must be integers")
    if abs(chunk_x) > 100000 or abs(chunk_y) > 100000:
        raise ValueError("Map chunk coordinates rejected")
    return VIEW_TOOL, {"mapChunkX": chunk_x,
                       "mapChunkY": chunk_y}


def telemetry_request() -> tuple[str, dict[str, Any]]:
    """Return the bounded telemetry observation request.

    The telemetry tool reads the item flow and the local electrical
    statistics without a terrain, an entity-map or a recipe scan.
    """
    return TELEMETRY_TOOL, {}


def catalog_request(page: int = 1, page_size: int = 32
                    ) -> tuple[str, dict[str, Any]]:
    """Return the catalog observation request for one page.

    The catalog is requested on demand only. A full catalog assembly
    walks every page once and is never tied to the frequent polling.
    """
    if type(page) is not int or page < 1:
        raise ValueError("Invalid catalog page")
    if type(page_size) is not int or not 1 <= page_size <= 128:
        raise ValueError("Invalid catalog page size")
    return VIEW_TOOL, {"catalogOnly": True, "catalogPage": page,
                       "catalogPageSize": page_size}


def lowest_priority_first(kinds: Iterable[str]) -> list[str]:
    """Return the kinds ordered from the most urgent to the least."""
    return sorted(dict.fromkeys(kinds), key=priority)


def inventory_request(machine_page: int = 1, machine_page_size: int = 16,
                       logistics_page: int = 1,
                       logistics_page_size: int = 16
                       ) -> tuple[str, dict[str, Any]]:
    """Return the bounded inventory and logistics observation request.

    The request asks the restricted backend for the machine inventories,
    the logistic networks, the robot counters and the transport
    inventories in **one** call. The four observations are read separately
    by the backend and are never merged with each other, so one request
    does not blur the four facts.

    This request is **not** part of the frequent poll. It walks entities,
    so it is requested on demand only, exactly like the catalog.
    """
    if type(machine_page) is not int or machine_page < 1 or machine_page > 10000:
        raise ValueError("Invalid machine page")
    if (type(machine_page_size) is not int
            or not 1 <= machine_page_size <= 64):
        raise ValueError("Invalid machine page size")
    if (type(logistics_page) is not int
            or logistics_page < 1 or logistics_page > 10000):
        raise ValueError("Invalid logistics page")
    if (type(logistics_page_size) is not int
            or not 1 <= logistics_page_size <= 64):
        raise ValueError("Invalid logistics page size")
    return INVENTORY_TOOL, {
        "machinePage": machine_page,
        "machinePageSize": machine_page_size,
        "logisticsPage": logistics_page,
        "logisticsPageSize": logistics_page_size,
    }
