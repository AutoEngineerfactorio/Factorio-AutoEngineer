"""Pure Factorio-style inventory slot layout model; no Tk and no game access.

This module turns validated observer inventory data into an explicit slot
layout: real slot numbers, responsive columns, visible empty slots and a
per-slot signature used to redraw only what changed.

It never touches the Factorio process, the observer feed or the widget tree.
"""
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# Factorio's own inventory grid: slots are square and laid out left to right.
SLOT_SIZE = 40
SLOT_ICON = 32
SLOT_PADDING = 4

# The quality badge sits in the top-left corner of a slot.
QUALITY_BADGE_SIZE = 12

# Quality tiers as observed in Factorio 2.1.23 (Space Age "quality" package).
QUALITY_ORDER = ("normal", "uncommon", "rare", "epic", "legendary")

QUALITY_COLORS = {
    "normal": "#bbb9ae",
    "uncommon": "#68b64b",
    "rare": "#529bea",
    "epic": "#ae61d5",
    "legendary": "#e6a135",
}

# Slot frame colours borrowed from the game's own inventory panel.
SLOT_EMPTY_FILL = "#3a3f36"
SLOT_EMPTY_EDGE = "#1a1e18"
SLOT_FILLED_FILL = "#4a5043"
SLOT_HIGHLIGHT = "#5d6553"
COUNT_TEXT = "#f2f1e4"
COUNT_SHADOW = "#14170f"


def quality_color(quality: str) -> str:
    """Return the Factorio quality colour, or the normal colour if unknown."""
    return QUALITY_COLORS.get(quality, QUALITY_COLORS["normal"])


def quality_rank(quality: str) -> int:
    """Return the ordering index of a quality tier (unknown tiers sort last)."""
    try:
        return QUALITY_ORDER.index(quality)
    except ValueError:
        return len(QUALITY_ORDER)


def inventory_columns(width: int, slot_size: int = SLOT_SIZE) -> int:
    """Fit complete inventory slots into the visible panel, minimum one."""
    return max(1, (max(0, int(width)) - 8) // slot_size)


@dataclass(frozen=True)
class Slot:
    """One inventory slot: its real position and the item it holds."""

    index: int
    """Real 1-based slot number reported by the game."""

    x: int
    y: int
    name: str | None = None
    quality: str | None = None
    count: int | None = None

    @property
    def empty(self) -> bool:
        return self.name is None

    @property
    def signature(self) -> tuple:
        """Everything that affects the rendered appearance of this slot."""
        return (self.index, self.name, self.quality, self.count)


@dataclass(frozen=True)
class InventoryLayout:
    """The full grid: real slot numbers, positions and provenance."""

    slots: tuple[Slot, ...]
    columns: int
    capacity: int
    actual: bool
    """True when the slot numbers come from the game's own inventory."""

    partial: bool = False
    """True when the observation was incomplete or truncated."""

    aggregate: bool = False
    """True when only aggregated item counts are known, not real slots."""

    rows: int = 0
    width: int = 0
    height: int = 0

    def slot_at(self, x: float, y: float) -> Slot | None:
        """Return the slot under canvas coordinates, or None."""
        for slot in self.slots:
            if slot.x <= x < slot.x + SLOT_SIZE and slot.y <= y < slot.y + SLOT_SIZE:
                return slot
        return None


def _normalise_quality(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    return "normal"


def build_layout(
    data: Mapping[str, Any] | None,
    width: int,
    *,
    slot_size: int = SLOT_SIZE,
    max_capacity: int = 200,
) -> InventoryLayout:
    """Build the slot layout for one observation.

    ``slots`` from the observer carries the game's real slot numbers and is
    always preferred. A missing ``slots`` key means only an aggregate item
    list is available; those entries are laid out in order and flagged as
    aggregate so the caller can label them as not being real slot positions.
    """
    if not isinstance(data, Mapping):
        return InventoryLayout((), inventory_columns(width, slot_size), 0, False, True, True, 0, 0)

    raw_slots = data.get("slots")
    actual = isinstance(raw_slots, (list, tuple))
    entries: list[tuple[int, Any]] = []
    capacity: int

    if actual:
        declared = data.get("capacity")
        if not isinstance(declared, int) or declared < 0:
            # Without a declared capacity the real slot numbers are the only
            # authority; never drop a slot because the grid size is unknown.
            capacity = max_capacity
        else:
            capacity = min(declared, max_capacity)
        for entry in raw_slots:
            if not isinstance(entry, Mapping):
                continue
            index = entry.get("slot")
            if not isinstance(index, int) or index < 1 or index > capacity:
                continue
            entries.append((index, entry))
        # Slot order follows the game, never the item name.
        entries.sort(key=lambda item: item[0])
        if not isinstance(declared, int):
            # The grid extent is unknown; report the highest observed slot.
            capacity = max((index for index, _ in entries), default=0)
    else:
        aggregate_items = data.get("inventory")
        if isinstance(aggregate_items, (list, tuple)):
            capacity = len(aggregate_items)
            entries = [(n + 1, item) for n, item in enumerate(aggregate_items)]
        else:
            capacity = 0

    columns = inventory_columns(width, slot_size)
    slots: list[Slot] = []
    for index, entry in entries:
        row = (index - 1) // columns
        column = (index - 1) % columns
        name = entry.get("name") if isinstance(entry, Mapping) else None
        quality = _normalise_quality(entry.get("quality")) if name else None
        count = entry.get("count") if isinstance(entry, Mapping) else None
        if not isinstance(count, int):
            count = None
        slots.append(
            Slot(
                index=index,
                x=column * slot_size + SLOT_PADDING,
                y=row * slot_size + SLOT_PADDING,
                name=name if isinstance(name, str) and name else None,
                quality=quality,
                count=count,
            )
        )

    partial = bool(data.get("slots_truncated")) or bool(data.get("truncated"))
    rows = -(-capacity // columns) if capacity else 0
    return InventoryLayout(
        slots=tuple(slots),
        columns=columns,
        capacity=capacity,
        actual=actual,
        partial=partial,
        aggregate=not actual,
        rows=rows,
        width=columns * slot_size + SLOT_PADDING * 2,
        height=rows * slot_size + SLOT_PADDING * 2,
    )


def changed_slots(
    previous: Sequence[Slot], current: Sequence[Slot]
) -> tuple[set[int], set[int]]:
    """Return the indices whose appearance changed between two layouts.

    The first set holds changed slot numbers; the second holds slot numbers
    that are present in one layout but absent from the other. The caller uses
    this to update only the slots that actually moved.
    """
    old = {slot.index: slot for slot in previous}
    new = {slot.index: slot for slot in current}
    changed = {
        index
        for index, slot in new.items()
        if index not in old or old[index].signature != slot.signature
    }
    removed = set(old) - set(new)
    return changed, removed


def layout_fingerprint(layout: InventoryLayout) -> tuple:
    """A cheap fingerprint of everything that affects the rendered grid."""
    return (
        layout.columns,
        layout.capacity,
        layout.actual,
        layout.partial,
        layout.aggregate,
        tuple(slot.signature for slot in layout.slots),
    )


def tooltip_text(slot: Slot) -> str:
    """Factorio-style tooltip line for one slot."""
    if slot.empty or slot.name is None:
        return f"Slot {slot.index}: empty"
    quality = slot.quality or "normal"
    count = slot.count if slot.count is not None else 0
    return f"Slot {slot.index}: {slot.name} x {count} - {quality}"
