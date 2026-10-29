"""The observed supply facts the AI Helper plans against.

The R10-B observation tells the planner what the factory actually holds
right now: the items in the machines and the chests, the items the
logistic networks can deliver, the recipes the observed machines are
running and the robot capacity that moves the goods.

The module answers the questions the mission lists, using **only** the
observed data:

* which ingredients are currently available;
* which ingredients are observed to be short;
* which machines exist and what they are producing;
* how much logistics capacity is available;
* which observed recipes are running.

Three rules keep the answer honest.

**Nothing is invented.** A quantity that the game did not report is
absent, never zero. An item that was not observed is *unknown*, not
*missing*.

**Theories stay separate.** The theoretical production requirement of a
recipe comes from the R10-A recipe catalog. The observed supply comes
from the R10-B observation. The two are reported side by side and are
never merged into a single number.

**A shortage is only reported when the game can answer it.** The Factorio
2.1.23 logistic network API reports the *available* counts and the
provider, requester and storage membership. It does not expose a
per-request shortage figure, so this module reports the available count
and the observed membership and never derives a shortage from them.

The module has no Qt, Factorio or transport import, so the whole path is
verifiable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from qt_inventory_observations import (
    InventoryObservation,
    ObservedMachine,
    ObservedStack,
    inventory_observation,
)

#: The maximum number of available items the summary keeps.
MAX_AVAILABLE_ITEMS = 256

#: The maximum number of observed machines the summary keeps.
MAX_OBSERVED_MACHINES = 256

#: The maximum number of observed recipes the summary keeps.
MAX_OBSERVED_RECIPES = 128

#: The state shown for a quantity the game did not report.
UNKNOWN = "unknown"


@dataclass(frozen=True)
class AvailableItem:
    """One item the factory currently holds."""

    name: str
    count: int
    quality: str = "normal"
    #: Where the item was observed.
    source: str = "unknown"

    @property
    def key(self) -> str:
        """The stable key of this item."""
        return f"{self.name}:{self.quality}"


@dataclass(frozen=True)
class ObservedSupply:
    """The observed supply and capability facts of one factory.

    ``available`` is the merged view of everything the game reported as
    held. ``sources`` keeps the per-source counts, so a caller can tell
    the logistic availability from the physical inventory.
    """

    state: str = "observed"
    detail: str = "Observed supply"
    available: tuple[AvailableItem, ...] = ()
    #: The per-source counts: ``network:<id>`` or ``entity:<name>``.
    sources: Mapping[str, tuple[AvailableItem, ...]] = field(
        default_factory=dict)
    observed_machines: tuple[ObservedMachine, ...] = ()
    observed_recipes: tuple[str, ...] = ()
    machine_count: int = 0
    network_count: int = 0
    total_logistic_robots: int | None = None
    available_logistic_robots: int | None = None
    total_construction_robots: int | None = None
    available_construction_robots: int | None = None
    robot_limit: int | None = None
    truncated: bool = False
    partial: bool = False

    @property
    def known(self) -> bool:
        """Whether any supply was actually observed."""
        return self.state == "observed" and bool(self.available)

    def available_count(self, name: str, quality: str = "normal") -> int | None:
        """Return the observed count of one item, or ``None``.

        ``None`` means the item was **not observed**, which is different
        from a count of zero.
        """
        for item in self.available:
            if item.name == name and item.quality == quality:
                return item.count
        return None

    def is_observed_available(self, name: str, quality: str = "normal"
                              ) -> bool | None:
        """Whether the item is observed to be available.

        ``True`` means the game reported a positive count, ``False``
        means the game reported the item and the count was zero, and
        ``None`` means the item was not observed at all.
        """
        count = self.available_count(name, quality)
        if count is None:
            return None
        return count > 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe description of the observed supply."""
        return {
            "state": self.state,
            "detail": self.detail,
            "available": [
                {"name": item.name, "count": item.count,
                 "quality": item.quality, "source": item.source}
                for item in self.available
            ],
            "observed_machines": [
                {"name": machine.name, "type": machine.entity_type,
                 "recipe": machine.recipe, "surface": machine.surface,
                 "quality": machine.quality}
                for machine in self.observed_machines
            ],
            "observed_recipes": list(self.observed_recipes),
            "machine_count": self.machine_count,
            "network_count": self.network_count,
            "total_logistic_robots": self.total_logistic_robots,
            "available_logistic_robots": self.available_logistic_robots,
            "total_construction_robots": self.total_construction_robots,
            "available_construction_robots": self.available_construction_robots,
            "robot_limit": self.robot_limit,
            "truncated": self.truncated,
            "partial": self.partial,
        }


def _merge(groups: Iterable[tuple[str, tuple[ObservedStack, ...]]]
           ) -> tuple[AvailableItem, ...]:
    """Merge the observed stacks of every source into one bounded list."""
    totals: dict[str, AvailableItem] = {}
    order: list[str] = []
    for source, stacks in groups:
        for stack in stacks:
            key = f"{stack.name}:{stack.quality}"
            existing = totals.get(key)
            if existing is None:
                if len(totals) >= MAX_AVAILABLE_ITEMS:
                    continue
                totals[key] = AvailableItem(
                    name=stack.name, count=stack.count,
                    quality=stack.quality, source=source)
                order.append(key)
            else:
                totals[key] = AvailableItem(
                    name=existing.name, count=existing.count + stack.count,
                    quality=existing.quality, source=existing.source)
    return tuple(totals[key] for key in order)


def _network_groups(snapshot: InventoryObservation
                    ) -> list[tuple[str, tuple[ObservedStack, ...]]]:
    """Return the per-network observed stacks."""
    groups: list[tuple[str, tuple[ObservedStack, ...]]] = []
    for network in snapshot.networks:
        groups.append((f"network:{network.network_id}", network.items))
    return groups


def _entity_groups(snapshot: InventoryObservation
                    ) -> list[tuple[str, tuple[ObservedStack, ...]]]:
    """Return the per-entity observed stacks of the machines and the
    transport entities."""
    groups: list[tuple[str, tuple[ObservedStack, ...]]] = []
    for machine in snapshot.machines:
        stacks: list[ObservedStack] = []
        for inventory in machine.inventories:
            stacks.extend(inventory.items)
        groups.append((f"entity:{machine.name}", tuple(stacks)))
    for transport in snapshot.transport:
        stacks = list(transport.train_items)
        for inventory in transport.inventories:
            stacks.extend(inventory.items)
        groups.append((f"entity:{transport.name}", tuple(stacks)))
    return groups


def observed_supply(frame: Mapping[str, Any] | None, *,
                     state: str = "observed",
                     detail: str = "Observed supply"
                     ) -> ObservedSupply:
    """Build the observed supply facts of one factory.

    The frame is the validated ``autoengineer_inventory`` payload. The
    same snapshot that the Qt workspaces read is used here, so the
    dashboard and the planner can never disagree.
    """
    snapshot = inventory_observation(frame, state=state, detail=detail)
    if not snapshot.known:
        return ObservedSupply(
            state="unavailable",
            detail="Supply unavailable: no observation received")

    groups = _network_groups(snapshot) + _entity_groups(snapshot)
    sources = {name: tuple(
        AvailableItem(name=stack.name, count=stack.count,
                      quality=stack.quality, source=name)
        for stack in stacks)
        for name, stacks in groups}

    recipes: list[str] = []
    for machine in snapshot.machines:
        if machine.recipe and machine.recipe not in recipes:
            recipes.append(machine.recipe)

    robots = snapshot.robots
    return ObservedSupply(
        state="observed",
        detail=detail,
        available=_merge(groups),
        sources=sources,
        observed_machines=snapshot.machines[:MAX_OBSERVED_MACHINES],
        observed_recipes=tuple(recipes[:MAX_OBSERVED_RECIPES]),
        machine_count=len(snapshot.machines),
        network_count=len(snapshot.networks),
        total_logistic_robots=robots.total_logistic_robots,
        available_logistic_robots=robots.available_logistic_robots,
        total_construction_robots=robots.total_construction_robots,
        available_construction_robots=robots.available_construction_robots,
        robot_limit=robots.robot_limit,
        truncated=snapshot.machine_truncated,
        partial=snapshot.machine_partial,
    )


def supply_evidence(snapshot: ObservedSupply) -> dict[str, Any]:
    """Return the observed supply as a planner evidence payload.

    The payload is deliberately small: it carries the **available**
    quantities and the observed capabilities, not the whole observation.
    A planner that needs more asks the observation again.
    """
    return {
        "available_items": len(snapshot.available),
        "items": [
            {"name": item.name, "count": item.count, "quality": item.quality}
            for item in snapshot.available
        ],
        "observed_machines": snapshot.machine_count,
        "observed_recipes": list(snapshot.observed_recipes),
        "logistic_networks": snapshot.network_count,
        "total_logistic_robots": snapshot.total_logistic_robots,
        "available_logistic_robots": snapshot.available_logistic_robots,
        "total_construction_robots": snapshot.total_construction_robots,
        "available_construction_robots": snapshot.available_construction_robots,
        "partial": snapshot.partial,
        "truncated": snapshot.truncated,
    }


__all__ = [
    "MAX_AVAILABLE_ITEMS",
    "MAX_OBSERVED_MACHINES",
    "MAX_OBSERVED_RECIPES",
    "UNKNOWN",
    "AvailableItem",
    "ObservedSupply",
    "observed_supply",
    "supply_evidence",
]
