"""Shared inventory and logistics snapshot from the observed game data.

The Inventory & Logistics workspace must show what the game actually
reported, and nothing else. This module turns the observed frames into one
immutable snapshot with an explicit state for every field.

The important rule is that **unknown is not zero**. The observation
protocol does not yet provide every field that the workspace could show:

* the player inventory is observed, but only the player's own main
  inventory, not the inventories of individual machines;
* the production statistics are observed, but only for the prototypes the
  game sampled, and the game says so explicitly;
* the logistic network contents, the logistic and construction robot
  counts and the transport and storage inventories are **not** part of the
  observation protocol.

Every one of those gaps is reported as *unavailable* with the reason, so the
workspace can say "not observed" instead of showing a zero that would read
as "there is nothing there".

The module contains no Qt, Factorio or transport import, so the whole
snapshot path is verifiable offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from qt_observation import OBSERVED, STALE, UNAVAILABLE

#: The maximum number of inventory entries the snapshot keeps.
MAX_INVENTORY_ITEMS = 64

#: The maximum number of production rows the snapshot keeps.
MAX_PRODUCTION_ROWS = 64

#: The maximum number of machine rows the snapshot keeps.
MAX_MACHINE_ROWS = 64

#: The maximum number of logistics rows the snapshot keeps.
MAX_LOGISTICS_ROWS = 64

#: The reason shown when the observation protocol has no such field.
UNSUPPORTED = "unsupported by the current observation protocol"


@dataclass(frozen=True)
class InventoryEntry:
    """One observed inventory stack."""

    name: str
    count: int
    quality: str
    slot: int | None = None

    @property
    def label(self) -> str:
        """Return the display label of this stack."""
        if self.quality and self.quality != "normal":
            return f"{self.name} ({self.quality})"
        return self.name


@dataclass(frozen=True)
class ProductionRow:
    """One observed production or consumption row.

    The rates come from the game's own production statistics. The
    ``partial`` flag says the row was sampled, not measured for the whole
    force.
    """

    name: str
    produced: float | None
    consumed: float | None
    produced_per_second: float | None
    consumed_per_second: float | None
    partial: bool = False


@dataclass(frozen=True)
class MachineRow:
    """One observed electrical network."""

    network_id: int
    maximum_production: float | None
    maximum_consumption: float | None
    consumption_satisfaction: float | None
    production_satisfaction: float | None
    accumulator_energy: float | None
    accumulator_capacity: float | None


@dataclass(frozen=True)
class LogisticsRow:
    """One observed roboport logistic cell."""

    x: float
    y: float
    logistic_radius: float
    construction_radius: float
    active: bool


@dataclass(frozen=True)
class InventorySnapshot:
    """One immutable view of the observed inventory and logistics state."""

    state: str
    detail: str
    player_name: str | None
    items: tuple[InventoryEntry, ...]
    inventory_available: bool
    inventory_capacity: int | None
    inventory_truncated: bool
    slots_truncated: bool
    item_production: tuple[ProductionRow, ...]
    item_production_status: str
    item_production_partial: bool
    fluid_production: tuple[ProductionRow, ...]
    fluid_production_status: str
    fluid_production_partial: bool
    networks: tuple[MachineRow, ...]
    power_status: str
    logistics: tuple[LogisticsRow, ...]
    logistics_available: bool
    tick: int | None

    # -- explicit unavailable states -------------------------------------

    @property
    def machine_inventories_supported(self) -> bool:
        """Whether per-machine inventories are part of the observation."""
        return False

    @property
    def machine_inventories_reason(self) -> str:
        """Why the per-machine inventories cannot be shown."""
        return UNSUPPORTED

    @property
    def logistic_network_contents_supported(self) -> bool:
        """Whether logistic network contents are part of the observation."""
        return False

    @property
    def logistic_network_contents_reason(self) -> str:
        """Why the logistic network contents cannot be shown."""
        return UNSUPPORTED

    @property
    def robot_counts_supported(self) -> bool:
        """Whether robot counts are part of the observation."""
        return False

    @property
    def robot_counts_reason(self) -> str:
        """Why the robot counts cannot be shown."""
        return UNSUPPORTED

    @property
    def transport_storage_supported(self) -> bool:
        """Whether transport and storage inventories are observed."""
        return False

    @property
    def transport_storage_reason(self) -> str:
        """Why the transport and storage inventories cannot be shown."""
        return UNSUPPORTED

    @property
    def known(self) -> bool:
        """Whether anything at all was observed."""
        return self.state != UNAVAILABLE


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


def _inventory_entries(raw: Any) -> tuple[InventoryEntry, ...]:
    """Return the bounded observed player inventory stacks."""
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_INVENTORY_ITEMS:
        return ()
    entries: list[InventoryEntry] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        name = _bounded_text(item.get("name"))
        count = _bounded_int(item.get("count"))
        if name is None or count is None:
            continue
        quality = _bounded_text(item.get("quality"), 64) or "normal"
        entries.append(InventoryEntry(
            name=name, count=count, quality=quality,
            slot=_bounded_int(item.get("slot"))))
    return tuple(entries)


def _window_values(row: Mapping[str, Any]) -> tuple[float | None, ...]:
    """Return the produced, consumed and per-second values of one row."""
    window = row.get("five_seconds")
    if not isinstance(window, Mapping):
        window = row.get("one_minute")
    if not isinstance(window, Mapping):
        return (None, None, None, None)
    return (
        _bounded_float(window.get("produced")),
        _bounded_float(window.get("consumed")),
        _bounded_float(window.get("per_second_produced")),
        _bounded_float(window.get("per_second_consumed")),
    )


def _production_rows(raw: Any, limit: int) -> tuple[ProductionRow, ...]:
    """Return the bounded observed production rows."""
    if not isinstance(raw, (list, tuple)) or len(raw) > limit:
        return ()
    rows: list[ProductionRow] = []
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        name = _bounded_text(row.get("name"))
        if name is None:
            continue
        produced, consumed, per_second, consumed_per_second = _window_values(row)
        rows.append(ProductionRow(
            name=name, produced=produced, consumed=consumed,
            produced_per_second=per_second,
            consumed_per_second=consumed_per_second))
    return tuple(rows)


def _network_rows(raw: Any) -> tuple[MachineRow, ...]:
    """Return the bounded observed electrical networks."""
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_MACHINE_ROWS:
        return ()
    rows: list[MachineRow] = []
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        network_id = _bounded_int(row.get("network_id"))
        if network_id is None:
            continue
        rows.append(MachineRow(
            network_id=network_id,
            maximum_production=_bounded_float(row.get("maximum_production")),
            maximum_consumption=_bounded_float(row.get("maximum_consumption")),
            consumption_satisfaction=_bounded_float(
                row.get("consumption_satisfaction")),
            production_satisfaction=_bounded_float(
                row.get("production_satisfaction")),
            accumulator_energy=_bounded_float(row.get("accumulator_energy")),
            accumulator_capacity=_bounded_float(
                row.get("accumulator_capacity"))))
    return tuple(rows)


def _logistics_rows(raw: Any) -> tuple[LogisticsRow, ...]:
    """Return the bounded observed roboport logistic cells."""
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_LOGISTICS_ROWS:
        return ()
    rows: list[LogisticsRow] = []
    for row in raw:
        if not isinstance(row, Mapping):
            continue
        x = _bounded_float(row.get("x"))
        y = _bounded_float(row.get("y"))
        logistic = _bounded_float(row.get("logistic"))
        construction = _bounded_float(row.get("construction"))
        active = row.get("active")
        if x is None or y is None or logistic is None or construction is None:
            continue
        rows.append(LogisticsRow(
            x=x, y=y, logistic_radius=logistic,
            construction_radius=construction, active=active is True))
    return tuple(rows)


def inventory_snapshot(frame: Mapping[str, Any] | None, *,
                       state: str = OBSERVED,
                       detail: str = "Observed inventory"
                       ) -> InventorySnapshot:
    """Build an immutable inventory and logistics snapshot.

    The frame is the validated ``autoengineer_view`` payload. It carries the
    player's inventory and, when the telemetry was also observed, the
    production statistics and the electrical networks.
    """
    source = frame if isinstance(frame, Mapping) else {}
    inventory = source.get("inventory")
    telemetry = source.get("telemetry")
    telemetry = telemetry if isinstance(telemetry, Mapping) else {}

    inventory_available = source.get("inventory_available") is True
    items = _inventory_entries(inventory) if inventory_available else ()
    capacity = _bounded_int(source.get("capacity"))
    truncated = source.get("truncated") is True
    slots_truncated = source.get("slots_truncated") is True

    production = telemetry.get("production")
    production = production if isinstance(production, Mapping) else {}
    item_status = _bounded_text(production.get("status"), 64) or "unavailable"
    item_partial = production.get("partial") is True
    item_rows = _production_rows(production.get("items"), MAX_PRODUCTION_ROWS)

    fluid_status = _bounded_text(production.get("fluid_status"), 64)
    if fluid_status is None:
        fluid_status = "unavailable"
    fluid_partial = item_partial
    fluid_rows = _production_rows(production.get("fluids"), MAX_PRODUCTION_ROWS)

    power = telemetry.get("power")
    power = power if isinstance(power, Mapping) else {}
    power_status = _bounded_text(power.get("status"), 64) or "unavailable"
    networks = _network_rows(power.get("networks"))

    overlays = source.get("overlays")
    overlays = overlays if isinstance(overlays, Mapping) else {}
    available = overlays.get("available")
    available = available if isinstance(available, Mapping) else {}
    logistics_available = available.get("logistics") is True
    logistics = _logistics_rows(overlays.get("logistics"))

    if state == OBSERVED and not (items or item_rows or fluid_rows
                                  or networks or logistics):
        state = UNAVAILABLE
        detail = ("Inventory and logistics unavailable: no observation "
                  "received")

    tick = _bounded_int(source.get("tick"))
    if tick is None:
        tick = _bounded_int(telemetry.get("tick"))

    return InventorySnapshot(
        state=state,
        detail=detail,
        player_name=_bounded_text(source.get("player_name"), 128),
        items=items,
        inventory_available=inventory_available,
        inventory_capacity=capacity,
        inventory_truncated=truncated,
        slots_truncated=slots_truncated,
        item_production=item_rows,
        item_production_status=item_status,
        item_production_partial=item_partial,
        fluid_production=fluid_rows,
        fluid_production_status=fluid_status,
        fluid_production_partial=fluid_partial,
        networks=networks,
        power_status=power_status,
        logistics=logistics,
        logistics_available=logistics_available,
        tick=tick,
    )


def inventory_status_text(snapshot: InventorySnapshot) -> str:
    """Return a concise, truthful status for the inventory workspace."""
    if snapshot.state == UNAVAILABLE:
        return snapshot.detail
    if snapshot.state == STALE:
        return f"Stale: {snapshot.detail}"
    if snapshot.inventory_available and snapshot.inventory_truncated:
        return (f"Player inventory ({len(snapshot.items)} aggregated entries, "
                "truncated)")
    if snapshot.inventory_available:
        return f"Player inventory: {len(snapshot.items)} entries"
    return snapshot.detail or "Inventory not observed"


__all__ = [
    "MAX_INVENTORY_ITEMS",
    "MAX_LOGISTICS_ROWS",
    "MAX_MACHINE_ROWS",
    "MAX_PRODUCTION_ROWS",
    "UNSUPPORTED",
    "InventoryEntry",
    "InventorySnapshot",
    "LogisticsRow",
    "MachineRow",
    "ProductionRow",
    "inventory_snapshot",
    "inventory_status_text",
]
