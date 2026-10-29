"""The observed machine, logistics, robot and transport snapshot.

This module turns the ``autoengineer_inventory`` frame into one immutable
snapshot that the Qt workspaces and the AI Helper both read. It is the
**same** snapshot for both, so the dashboard and the planner can never
disagree about what the game reported.

Three rules govern the snapshot.

**Unknown is not zero.** Every field carries an explicit state. A field
the game did not report is *unavailable* with its reason, never a zero
that would read as "there is nothing there".

**Bounded.** Every collection has a cap. A frame that carries more than
the cap is truncated and says so.

**Honest.** A shortage is only reported when the game itself answered the
request question. The logistic network API reports the *available* counts
and the provider, requester and storage membership; it does not expose a
per-request shortage number, so no shortage is derived from it.

The module contains no Qt, Factorio or transport import, so the whole
snapshot path is verifiable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from qt_observation import OBSERVED, STALE, UNAVAILABLE

#: The maximum number of machine rows the snapshot keeps.
MAX_MACHINE_ROWS = 128

#: The maximum number of inventory rows one machine keeps.
MAX_INVENTORY_ROWS = 32

#: The maximum number of fluid rows one machine keeps.
MAX_FLUID_ROWS = 16

#: The maximum number of logistic networks the snapshot keeps.
MAX_NETWORK_ROWS = 32

#: The maximum number of item rows one network keeps.
MAX_NETWORK_ITEM_ROWS = 64

#: The maximum number of member names one network keeps.
MAX_NETWORK_MEMBERS = 32

#: The maximum number of transport rows the snapshot keeps.
MAX_TRANSPORT_ROWS = 64

#: The reason shown when a section was not observed.
UNOBSERVED = "not observed"


def _bounded_int(value: Any) -> int | None:
    """Return a non-negative integer, or ``None``."""
    if type(value) is int and value >= 0:
        return value
    return None


def _bounded_float(value: Any) -> float | None:
    """Return a finite float, or ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number == number and number not in (float("inf"), float("-inf")):
            return number
    return None


def _bounded_text(value: Any, limit: int = 256) -> str | None:
    """Return bounded single-line text, or ``None``."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit:
        return None
    return text


def _section(frame: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """Return one section of the inventory frame."""
    value = frame.get(name)
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class ObservedStack:
    """One observed item stack."""

    name: str
    count: int
    quality: str = "normal"

    @property
    def label(self) -> str:
        """Return the display label of this stack."""
        if self.quality and self.quality != "normal":
            return f"{self.name} ({self.quality})"
        return self.name


@dataclass(frozen=True)
class ObservedFluid:
    """One observed fluid container."""

    name: str
    amount: float
    temperature: float | None = None


@dataclass(frozen=True)
class ObservedInventory:
    """One observed entity inventory."""

    category: str
    identifier: str
    capacity: int | None
    items: tuple[ObservedStack, ...]
    empty: bool
    truncated: bool

    @property
    def item_count(self) -> int:
        """The number of distinct stacks in this inventory."""
        return len(self.items)


@dataclass(frozen=True)
class ObservedMachine:
    """One observed machine, chest, wagon or tank."""

    name: str
    entity_type: str
    surface: str
    quality: str = "normal"
    x: float | None = None
    y: float | None = None
    recipe: str | None = None
    active: bool | None = None
    inventories: tuple[ObservedInventory, ...] = ()
    fluids: tuple[ObservedFluid, ...] = ()

    @property
    def position(self) -> str:
        """The display position of this entity."""
        if self.x is None or self.y is None:
            return "—"
        return f"({self.x:.0f}, {self.y:.0f})"


@dataclass(frozen=True)
class ObservedNetwork:
    """One observed logistic network."""

    network_id: int
    surface: str
    force: str = ""
    custom_name: str = ""
    available_logistic_robots: int | None = None
    all_logistic_robots: int | None = None
    available_construction_robots: int | None = None
    all_construction_robots: int | None = None
    robot_limit: int | None = None
    items: tuple[ObservedStack, ...] = ()
    providers: tuple[str, ...] = ()
    requesters: tuple[str, ...] = ()
    storages: tuple[str, ...] = ()
    items_truncated: bool = False

    @property
    def label(self) -> str:
        """The display label of this network."""
        if self.custom_name:
            return f"{self.custom_name} (#{self.network_id})"
        return f"Network #{self.network_id}"


@dataclass(frozen=True)
class ObservedRobots:
    """The observed robot availability of the force."""

    networks: int | None = None
    total_logistic_robots: int | None = None
    available_logistic_robots: int | None = None
    total_construction_robots: int | None = None
    available_construction_robots: int | None = None
    robot_limit: int | None = None
    partial: bool = False

    @property
    def busy_logistic_robots(self) -> int | None:
        """The logistic robots that are not available."""
        if (self.total_logistic_robots is None
                or self.available_logistic_robots is None):
            return None
        return self.total_logistic_robots - self.available_logistic_robots

    @property
    def busy_construction_robots(self) -> int | None:
        """The construction robots that are not available."""
        if (self.total_construction_robots is None
                or self.available_construction_robots is None):
            return None
        return self.total_construction_robots - self.available_construction_robots


@dataclass(frozen=True)
class ObservedTransport:
    """One observed transport or storage entity."""

    name: str
    entity_type: str
    surface: str
    quality: str = "normal"
    x: float | None = None
    y: float | None = None
    inventories: tuple[ObservedInventory, ...] = ()
    fluids: tuple[ObservedFluid, ...] = ()
    train_items: tuple[ObservedStack, ...] = ()
    train_fluids: tuple[ObservedFluid, ...] = ()


@dataclass(frozen=True)
class InventoryObservation:
    """The immutable R10-B inventory and logistics snapshot.

    Every section carries its own state so the workspace can tell
    *observed* from *unavailable* without inspecting the whole snapshot.
    """

    state: str = OBSERVED
    detail: str = "Observed inventory and logistics"
    machines: tuple[ObservedMachine, ...] = ()
    networks: tuple[ObservedNetwork, ...] = ()
    robots: ObservedRobots = field(default_factory=ObservedRobots)
    transport: tuple[ObservedTransport, ...] = ()
    machine_page: int | None = None
    machine_page_size: int | None = None
    machine_total: int | None = None
    machine_page_count: int | None = None
    machine_matched: int | None = None
    machine_partial: bool = False
    machine_truncated: bool = False
    machine_snapshot: str | None = None
    logistics_page: int | None = None
    logistics_page_size: int | None = None
    logistics_total: int | None = None
    logistics_page_count: int | None = None
    logistics_snapshot: str | None = None
    machines_state: str = UNAVAILABLE
    machines_reason: str = UNOBSERVED
    networks_state: str = UNAVAILABLE
    networks_reason: str = UNOBSERVED
    robots_state: str = UNAVAILABLE
    robots_reason: str = UNOBSERVED
    transport_state: str = UNAVAILABLE
    transport_reason: str = UNOBSERVED
    tick: int | None = None
    surface: str | None = None

    @property
    def known(self) -> bool:
        """Whether anything at all was observed."""
        return (self.machines_state == OBSERVED
                or self.networks_state == OBSERVED
                or self.robots_state == OBSERVED
                or self.transport_state == OBSERVED)

    @property
    def has_more_machines(self) -> bool:
        """Whether another machine page exists."""
        if self.machine_page_count is None or self.machine_page is None:
            return False
        return self.machine_page < self.machine_page_count

    @property
    def has_more_networks(self) -> bool:
        """Whether another logistic network page exists."""
        if self.logistics_page_count is None or self.logistics_page is None:
            return False
        return self.logistics_page < self.logistics_page_count

    def status_text(self) -> str:
        """Return a concise, truthful status for the workspace."""
        if self.state == UNAVAILABLE:
            return self.detail
        if self.state == STALE:
            return f"Stale: {self.detail}"
        parts: list[str] = []
        if self.machines_state == OBSERVED:
            parts.append(
                f"{len(self.machines)} machine rows"
                + (" (truncated)" if self.machine_truncated else ""))
        if self.networks_state == OBSERVED:
            parts.append(f"{len(self.networks)} logistic networks")
        if self.robots_state == OBSERVED:
            parts.append(
                f"{self.robots.available_logistic_robots or 0} robots available")
        if self.transport_state == OBSERVED:
            parts.append(f"{len(self.transport)} transport rows")
        if not parts:
            return self.detail
        return " · ".join(parts)


def _stacks(raw: Any, limit: int) -> tuple[ObservedStack, ...]:
    """Return the bounded observed item stacks of one list."""
    if not isinstance(raw, (list, tuple)) or len(raw) > limit * 4:
        return ()
    rows: list[ObservedStack] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _bounded_text(item.get("name"))
        count = _bounded_int(item.get("count"))
        if name is None or count is None:
            continue
        rows.append(ObservedStack(
            name=name, count=count,
            quality=_bounded_text(item.get("quality"), 64) or "normal"))
        if len(rows) >= limit:
            break
    return tuple(rows)


def _fluids(raw: Any, limit: int) -> tuple[ObservedFluid, ...]:
    """Return the bounded observed fluids of one list."""
    if not isinstance(raw, (list, tuple)) or len(raw) > limit * 4:
        return ()
    rows: list[ObservedFluid] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _bounded_text(item.get("name"))
        amount = _bounded_float(item.get("amount"))
        if name is None or amount is None:
            continue
        rows.append(ObservedFluid(
            name=name, amount=amount,
            temperature=_bounded_float(item.get("temperature"))))
        if len(rows) >= limit:
            break
    return tuple(rows)


def _inventories(raw: Any, limit: int) -> tuple[ObservedInventory, ...]:
    """Return the bounded observed inventories of one entity."""
    if not isinstance(raw, (list, tuple)) or len(raw) > limit * 4:
        return ()
    rows: list[ObservedInventory] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        category = _bounded_text(item.get("category"), 64)
        identifier = _bounded_text(item.get("identifier"), 64)
        if category is None or identifier is None:
            continue
        rows.append(ObservedInventory(
            category=category,
            identifier=identifier,
            capacity=_bounded_int(item.get("capacity")),
            items=_stacks(item.get("items"), MAX_INVENTORY_ROWS),
            empty=item.get("empty") is True,
            truncated=item.get("truncated") is True,
        ))
        if len(rows) >= limit:
            break
    return tuple(rows)


def _members(raw: Any, limit: int) -> tuple[str, ...]:
    """Return the bounded member names of one network."""
    if not isinstance(raw, (list, tuple)) or len(raw) > limit * 4:
        return ()
    names: list[str] = []
    for item in raw:
        name = _bounded_text(item, 128)
        if name is None:
            continue
        names.append(name)
        if len(names) >= limit:
            break
    return tuple(names)


def _machines(section: Mapping[str, Any]) -> tuple[ObservedMachine, ...]:
    """Return the bounded observed machines of one section."""
    raw = section.get("rows")
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_MACHINE_ROWS * 4:
        return ()
    rows: list[ObservedMachine] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _bounded_text(item.get("name"))
        entity_type = _bounded_text(item.get("type"), 64)
        surface = _bounded_text(item.get("surface"), 128)
        if name is None or entity_type is None or surface is None:
            continue
        rows.append(ObservedMachine(
            name=name,
            entity_type=entity_type,
            surface=surface,
            quality=_bounded_text(item.get("quality"), 64) or "normal",
            x=_bounded_float(item.get("x")),
            y=_bounded_float(item.get("y")),
            recipe=_bounded_text(item.get("recipe"), 128),
            active=item.get("active") if isinstance(
                item.get("active"), bool) else None,
            inventories=_inventories(item.get("inventories"),
                                    MAX_INVENTORY_ROWS),
            fluids=_fluids(item.get("fluids"), MAX_FLUID_ROWS),
        ))
        if len(rows) >= MAX_MACHINE_ROWS:
            break
    return tuple(rows)


def _networks(section: Mapping[str, Any]) -> tuple[ObservedNetwork, ...]:
    """Return the bounded observed logistic networks of one section."""
    raw = section.get("rows")
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_NETWORK_ROWS * 4:
        return ()
    rows: list[ObservedNetwork] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        network_id = _bounded_int(item.get("network_id"))
        surface = _bounded_text(item.get("surface"), 128)
        if network_id is None or surface is None:
            continue
        rows.append(ObservedNetwork(
            network_id=network_id,
            surface=surface,
            force=_bounded_text(item.get("force"), 128) or "",
            custom_name=_bounded_text(item.get("custom_name"), 128) or "",
            available_logistic_robots=_bounded_int(
                item.get("available_logistic_robots")),
            all_logistic_robots=_bounded_int(item.get("all_logistic_robots")),
            available_construction_robots=_bounded_int(
                item.get("available_construction_robots")),
            all_construction_robots=_bounded_int(
                item.get("all_construction_robots")),
            robot_limit=_bounded_int(item.get("robot_limit")),
            items=_stacks(item.get("items"), MAX_NETWORK_ITEM_ROWS),
            providers=_members(item.get("providers"), MAX_NETWORK_MEMBERS),
            requesters=_members(item.get("requesters"), MAX_NETWORK_MEMBERS),
            storages=_members(item.get("storages"), MAX_NETWORK_MEMBERS),
            items_truncated=item.get("items_truncated") is True,
        ))
        if len(rows) >= MAX_NETWORK_ROWS:
            break
    return tuple(rows)


def _transport(section: Mapping[str, Any]) -> tuple[ObservedTransport, ...]:
    """Return the bounded observed transport entities of one section."""
    raw = section.get("rows")
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_TRANSPORT_ROWS * 4:
        return ()
    rows: list[ObservedTransport] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _bounded_text(item.get("name"))
        entity_type = _bounded_text(item.get("type"), 64)
        surface = _bounded_text(item.get("surface"), 128)
        if name is None or entity_type is None or surface is None:
            continue
        train = item.get("train")
        train = train if isinstance(train, Mapping) else {}
        rows.append(ObservedTransport(
            name=name,
            entity_type=entity_type,
            surface=surface,
            quality=_bounded_text(item.get("quality"), 64) or "normal",
            x=_bounded_float(item.get("x")),
            y=_bounded_float(item.get("y")),
            inventories=_inventories(item.get("inventories"),
                                    MAX_INVENTORY_ROWS),
            fluids=_fluids(item.get("fluids"), MAX_FLUID_ROWS),
            train_items=_stacks(train.get("items"), MAX_NETWORK_ITEM_ROWS),
            train_fluids=_fluids(train.get("fluids"), MAX_FLUID_ROWS),
        ))
        if len(rows) >= MAX_TRANSPORT_ROWS:
            break
    return tuple(rows)


def _section_state(section: Mapping[str, Any]) -> tuple[str, str]:
    """Return the state and the reason of one section."""
    if section.get("available") is True:
        return OBSERVED, "Observed"
    reason = _bounded_text(section.get("reason"), 128)
    return UNAVAILABLE, reason or UNOBSERVED


def inventory_observation(frame: Mapping[str, Any] | None, *,
                          state: str = OBSERVED,
                          detail: str = "Observed inventory and logistics"
                          ) -> InventoryObservation:
    """Build the immutable R10-B inventory and logistics snapshot.

    The frame is the validated ``autoengineer_inventory`` payload. A
    frame that is absent produces an unavailable snapshot; a frame whose
    section is unavailable produces an unavailable **section**, so the
    workspace can show exactly which part of the observation is missing.
    """
    source = frame if isinstance(frame, Mapping) else {}
    machines_section = _section(source, "machine_inventories")
    networks_section = _section(source, "logistics")
    robots_section = _section(source, "robots")
    transport_section = _section(source, "transport")

    machines_state, machines_reason = _section_state(machines_section)
    networks_state, networks_reason = _section_state(networks_section)
    robots_state, robots_reason = _section_state(robots_section)
    transport_state, transport_reason = _section_state(transport_section)

    robots = ObservedRobots()
    if robots_state == OBSERVED:
        robots = ObservedRobots(
            networks=_bounded_int(robots_section.get("networks")),
            total_logistic_robots=_bounded_int(
                robots_section.get("total_logistic_robots")),
            available_logistic_robots=_bounded_int(
                robots_section.get("available_logistic_robots")),
            total_construction_robots=_bounded_int(
                robots_section.get("total_construction_robots")),
            available_construction_robots=_bounded_int(
                robots_section.get("available_construction_robots")),
            robot_limit=_bounded_int(robots_section.get("robot_limit")),
            partial=robots_section.get("partial") is True,
        )

    snapshot = InventoryObservation(
        state=state,
        detail=detail,
        machines=_machines(machines_section) if machines_state == OBSERVED
        else (),
        networks=_networks(networks_section) if networks_state == OBSERVED
        else (),
        robots=robots,
        transport=_transport(transport_section) if transport_state == OBSERVED
        else (),
        machine_page=_bounded_int(machines_section.get("page")),
        machine_page_size=_bounded_int(machines_section.get("page_size")),
        machine_total=_bounded_int(machines_section.get("total")),
        machine_page_count=_bounded_int(machines_section.get("page_count")),
        machine_matched=_bounded_int(machines_section.get("matched")),
        machine_partial=machines_section.get("partial") is True,
        machine_truncated=machines_section.get("truncated") is True,
        machine_snapshot=_bounded_text(machines_section.get("snapshot"), 128),
        logistics_page=_bounded_int(networks_section.get("page")),
        logistics_page_size=_bounded_int(networks_section.get("page_size")),
        logistics_total=_bounded_int(networks_section.get("total")),
        logistics_page_count=_bounded_int(networks_section.get("page_count")),
        logistics_snapshot=_bounded_text(
            networks_section.get("snapshot"), 128),
        machines_state=machines_state,
        machines_reason=machines_reason,
        networks_state=networks_state,
        networks_reason=networks_reason,
        robots_state=robots_state,
        robots_reason=robots_reason,
        transport_state=transport_state,
        transport_reason=transport_reason,
        tick=_bounded_int(source.get("tick")),
        surface=_bounded_text(source.get("surface"), 128),
    )
    if state == OBSERVED and not snapshot.known:
        return InventoryObservation(
            state=UNAVAILABLE,
            detail="Inventory and logistics unavailable: no observation received",
            tick=snapshot.tick,
        )
    return snapshot


__all__ = [
    "MAX_FLUID_ROWS",
    "MAX_INVENTORY_ROWS",
    "MAX_MACHINE_ROWS",
    "MAX_NETWORK_ITEM_ROWS",
    "MAX_NETWORK_MEMBERS",
    "MAX_NETWORK_ROWS",
    "MAX_TRANSPORT_ROWS",
    "UNOBSERVED",
    "InventoryObservation",
    "ObservedFluid",
    "ObservedInventory",
    "ObservedMachine",
    "ObservedNetwork",
    "ObservedRobots",
    "ObservedStack",
    "ObservedTransport",
    "inventory_observation",
]
