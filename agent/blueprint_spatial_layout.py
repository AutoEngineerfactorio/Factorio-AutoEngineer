"""R08-A: observation-driven spatial layout for connected blueprint drafts.

This module turns *observed* machine footprints and *observed* recipe
ingredients/products into a spatially valid machine layout with a delivery
and output plan. It is the R08 spatial half of the connected-blueprint work
that `agent/blueprint_design_engine.py` and `agent/blueprint_generation.py`
explicitly refuse to do: both of those place machines on a uniform grid that
ignores the observed machine size, so their entities can overlap.

Nothing here is invented:

* the machine footprint comes from the **observed** ``size`` (width/height)
  and the **observed** ``direction``; a direction of 2 (south) or 4 (west)
  swaps the two axes, exactly as Factorio rotates an entity footprint;
* ingredient delivery and product output come from the **observed** recipe
  ingredients and products;
* the power demand comes from the **observed** ``energy_usage``.

Every machine that the game did not describe completely is **refused**, not
guessed. A machine without an observed size has no footprint, so it cannot
be placed without overlapping its neighbours; a recipe without observed
ingredients has no delivery plan. Both cases raise :class:`LayoutError`.

The result is a **draft**. This module proves that the entities do not
overlap and that the ingredient/output accounting is internally consistent.
It does not prove that belts, inserters, pipes, poles or the power grid
exist, that the throughput is reachable, or that the blueprint builds in the
game. Those claims need an independent validation, so the status string
never claims buildability.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

#: The maximum number of machines one layout may contain.
MAX_LAYOUT_MACHINES = 256

#: The maximum number of columns one layout may use.
MAX_LAYOUT_COLUMNS = 32

#: The maximum number of ingredient or product rows one layout may plan.
MAX_LAYOUT_ROWS = 64

#: The directions Factorio rotates an entity footprint in.
#: North (0) and east (2) keep the footprint, south (4) and west (6) swap
#: the width and the height of the footprint.
_DIRECTION_SWAPS_FOOTPRINT = frozenset({4, 6})

#: The directions Factorio declares.
VALID_DIRECTIONS = frozenset({0, 1, 2, 3, 4, 5, 6, 7})

#: The largest machine footprint one observed prototype may declare, in
#: tiles. A larger footprint is refused instead of being laid out, because
#: the planner would have to invent a bounding box.
MAX_FOOTPRINT_TILES = 64

#: The label of a layout whose constraints were all satisfied but whose
#: physical routing is still unverified.
DRAFT_STATUS = "draft_spatial_plan_validated"

#: The label of a layout that could not be fully validated.
INCOMPLETE_STATUS = "draft_incomplete"


class LayoutError(ValueError):
    """The observed data did not justify a spatially valid layout."""


@dataclass(frozen=True)
class Footprint:
    """The observed tile footprint of one machine at one orientation."""

    width: int
    height: int
    direction: int

    @property
    def tiles(self) -> int:
        return self.width * self.height


@dataclass(frozen=True)
class Placement:
    """One placed machine and the tiles it occupies."""

    entity_number: int
    name: str
    recipe: str
    direction: int
    position: Mapping[str, int]
    footprint: Footprint

    @property
    def occupied_tiles(self) -> frozenset[tuple[int, int]]:
        """The absolute tiles this placement occupies."""
        left = self.position["x"]
        top = self.position["y"]
        return frozenset(
            (left + column, top + row)
            for column in range(self.footprint.width)
            for row in range(self.footprint.height)
        )


@dataclass(frozen=True)
class Connection:
    """One planned ingredient delivery or product output edge."""

    kind: str
    item: str
    amount_per_minute: float
    machine_name: str
    fluid: bool

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.item}"


@dataclass(frozen=True)
class SpatialLayout:
    """The result of a layout pass."""

    placements: tuple[Placement, ...]
    inputs: tuple[Connection, ...]
    outputs: tuple[Connection, ...]
    power_watts: float
    status: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def machine_count(self) -> int:
        return len(self.placements)

    def document(self, *, label: str, description: str,
                 version: int) -> dict[str, Any]:
        """Return the blueprint document for this layout."""
        return {"blueprint": {
            "version": version,
            "label": label[:100],
            "description": description[:1000],
            "entities": [
                {
                    "entity_number": placement.entity_number,
                    "name": placement.name,
                    "position": dict(placement.position),
                    "recipe": placement.recipe,
                    "direction": placement.direction,
                }
                for placement in self.placements
            ],
        }}


def _positive_number(value: Any, label: str) -> float:
    """Return a finite positive number or refuse."""
    if type(value) not in (int, float):
        raise LayoutError(f"{label} must be an observed number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise LayoutError(f"{label} must be an observed positive number")
    return number


def observed_footprint(machine: Mapping[str, Any]) -> Footprint:
    """Return the observed footprint of one machine prototype.

    The observed ``size`` is ``{"width": w, "height": h}`` in tiles and the
    observed ``direction`` is a Factorio direction. A machine without an
    observed size has **no** footprint, so it is refused: a guessed size
    would make the layout overlap without the caller knowing.
    """
    if not isinstance(machine, Mapping):
        raise LayoutError("An observed machine prototype is required")
    size = machine.get("size")
    if not isinstance(size, Mapping):
        raise LayoutError(
            f"Machine {machine.get('name')!r} has no observed size; "
            "a footprint cannot be derived")
    unknown = set(size) - {"width", "height"}
    if unknown:
        raise LayoutError("Unsupported observed machine size fields")
    width = size.get("width")
    height = size.get("height")
    for value, label in ((width, "width"), (height, "height")):
        if type(value) is not int or value <= 0:
            raise LayoutError(
                f"Observed machine {label} must be a positive whole number "
                "of tiles")
    assert isinstance(width, int) and isinstance(height, int)
    if width * height > MAX_FOOTPRINT_TILES:
        raise LayoutError("Observed machine footprint exceeds the layout limit")
    direction = machine.get("direction", 0)
    if type(direction) is not int or direction not in VALID_DIRECTIONS:
        raise LayoutError("Observed machine direction is invalid")
    if direction in _DIRECTION_SWAPS_FOOTPRINT:
        width, height = height, width
    return Footprint(width=width, height=height, direction=direction)


def _recipe_rows(recipe: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    """Return the observed ingredient or product rows of a recipe."""
    rows = recipe.get(key)
    if not isinstance(rows, list):
        raise LayoutError(
            f"Observed recipe has no {key}; the delivery plan cannot be "
            "derived")
    if len(rows) > MAX_LAYOUT_ROWS:
        raise LayoutError(f"Observed recipe {key} exceeds the layout limit")
    for row in rows:
        if not isinstance(row, Mapping):
            raise LayoutError(f"Observed recipe {key} row is not a mapping")
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise LayoutError(f"Observed recipe {key} row has no name")
        if row.get("type") == "fluid":
            continue
        _positive_number(row.get("amount"), f"Observed recipe {key} amount")
    return rows


def _flow_rate(row: Mapping[str, Any], crafts_per_minute: float) -> float:
    """Return the per-minute flow of one observed recipe row."""
    amount = _positive_number(row.get("amount"), "Observed recipe amount")
    return amount * crafts_per_minute


def plan_layout(
    recipe: Mapping[str, Any],
    machine: Mapping[str, Any],
    *,
    machine_count: int,
    crafting_speed: float | None = None,
    energy_usage: float | None = None,
    crafting_time: float | None = None,
    columns: int = 4,
    gap: int = 1,
) -> SpatialLayout:
    """Lay out ``machine_count`` copies of one observed machine.

    The machines are placed left to right in rows. A row holds as many
    machines as fit into ``columns`` *cells*; a cell is as wide as the
    widest machine in the row plus ``gap`` tiles, so the placement never
    overlaps and never depends on a hardcoded machine size.

    The ingredient and product rows are planned from the observed recipe.
    The power figure is the observed machine energy usage multiplied by the
    machine count, when the game declared it.
    """
    if type(machine_count) is not int or not 1 <= machine_count <= MAX_LAYOUT_MACHINES:
        raise LayoutError("Machine count is outside the layout limits")
    if type(columns) is not int or not 1 <= columns <= MAX_LAYOUT_COLUMNS:
        raise LayoutError("Column count is outside the layout limits")
    if type(gap) is not int or not 0 <= gap <= 16:
        raise LayoutError("Gap is outside the layout limits")

    footprint = observed_footprint(machine)
    machine_name = machine.get("name")
    if not isinstance(machine_name, str) or not machine_name:
        raise LayoutError("The observed machine prototype needs a name")
    recipe_name = recipe.get("name")
    if not isinstance(recipe_name, str) or not recipe_name:
        raise LayoutError("The observed recipe needs a name")

    ingredient_rows = _recipe_rows(recipe, "ingredients")
    product_rows = _recipe_rows(recipe, "products")

    speed = _positive_number(
        crafting_speed if crafting_speed is not None
        else machine.get("crafting_speed"),
        "Observed crafting speed")
    seconds = _positive_number(
        crafting_time if crafting_time is not None
        else recipe.get("crafting_time"),
        "Observed crafting time")
    crafts_per_minute = speed / seconds * 60.0

    placements: list[Placement] = []
    occupied: set[tuple[int, int]] = set()
    origin_x = 0
    origin_y = 0
    cursor_x = 0
    row_height = 0
    cell_width = footprint.width + gap

    for index in range(machine_count):
        if index and index % columns == 0:
            origin_y += row_height + gap
            cursor_x = origin_x
            row_height = 0
        position = {"x": cursor_x, "y": origin_y}
        placement = Placement(
            entity_number=index + 1,
            name=machine_name,
            recipe=recipe_name,
            direction=footprint.direction,
            position=position,
            footprint=footprint,
        )
        tiles = placement.occupied_tiles
        if tiles & occupied:
            raise LayoutError(
                "The planned placement overlaps another machine; the observed "
                "footprint does not fit the requested column count")
        occupied |= tiles
        placements.append(placement)
        cursor_x += cell_width
        row_height = max(row_height, footprint.height)

    # The planned flow is the flow of the whole layout, so it scales with
    # the number of machines that craft in parallel.
    layout_crafts_per_minute = crafts_per_minute * machine_count
    inputs = tuple(
        Connection(
            kind="input",
            item=str(row["name"]),
            amount_per_minute=round(_flow_rate(row, layout_crafts_per_minute), 6),
            machine_name=machine_name,
            fluid=row.get("type") == "fluid",
        )
        for row in ingredient_rows
    )
    outputs = tuple(
        Connection(
            kind="output",
            item=str(row["name"]),
            amount_per_minute=round(_flow_rate(row, layout_crafts_per_minute), 6),
            machine_name=machine_name,
            fluid=row.get("type") == "fluid",
        )
        for row in product_rows
    )

    # The observed energy usage is the machine's own demand, in the unit
    # the observation reported (the game-side observer publishes watts).
    # The layout demand is that demand times the number of machines.
    observed_energy = energy_usage if energy_usage is not None \
        else machine.get("energy_usage")
    watts = 0.0
    if observed_energy is not None:
        watts = round(
            _positive_number(
                observed_energy, "Observed machine energy usage") * machine_count,
            6)

    warnings = [
        "Machines are placed from the observed prototype size and direction.",
        "Ingredient delivery and product output are planned from the observed recipe.",
        "Belts, inserters, pipes, electric poles and the power grid are NOT placed.",
        "Throughput, reach and buildability in the game are NOT verified.",
    ]
    return SpatialLayout(
        placements=tuple(placements),
        inputs=inputs,
        outputs=outputs,
        power_watts=watts,
        status=DRAFT_STATUS,
        warnings=tuple(warnings),
    )


def validate_layout(layout: SpatialLayout) -> list[str]:
    """Return the problems found in a layout; an empty list means valid.

    The check is independent of the planner: it re-derives the occupied
    tiles from the placements and reports an overlap, a duplicate entity
    number or a non-positive flow. It never consults the planner's own
    bookkeeping.
    """
    problems: list[str] = []
    seen_numbers: set[int] = set()
    occupied: dict[tuple[int, int], int] = {}
    for placement in layout.placements:
        if placement.entity_number in seen_numbers:
            problems.append(
                f"Duplicate entity number {placement.entity_number}")
        seen_numbers.add(placement.entity_number)
        for tile in placement.occupied_tiles:
            other = occupied.get(tile)
            if other is not None:
                problems.append(
                    f"Tiles {tile} are occupied by entity {other} and "
                    f"{placement.entity_number}")
            else:
                occupied[tile] = placement.entity_number
    for connection in layout.inputs + layout.outputs:
        if not math.isfinite(connection.amount_per_minute) \
                or connection.amount_per_minute <= 0:
            problems.append(
                f"Connection {connection.label} has no positive flow")
    if layout.power_watts < 0:
        problems.append("The power demand cannot be negative")
    return problems


def assert_layout_valid(layout: SpatialLayout) -> None:
    """Raise :class:`LayoutError` when the layout has a problem."""
    problems = validate_layout(layout)
    if problems:
        raise LayoutError("; ".join(problems))


def layout_is_complete(layout: SpatialLayout) -> bool:
    """Whether the layout carries every planned connection and no problem."""
    return not validate_layout(layout)


def summarize(layout: SpatialLayout) -> dict[str, Any]:
    """Return a compact, JSON-safe summary of a layout."""
    return {
        "status": layout.status,
        "machine_count": layout.machine_count,
        "inputs": [
            {"item": c.item, "per_minute": c.amount_per_minute,
             "fluid": c.fluid}
            for c in layout.inputs
        ],
        "outputs": [
            {"item": c.item, "per_minute": c.amount_per_minute,
             "fluid": c.fluid}
            for c in layout.outputs
        ],
        "power_watts": layout.power_watts,
        "warnings": list(layout.warnings),
        "problems": validate_layout(layout),
    }


def plan_from_observations(
    observations: Mapping[str, Any],
    *,
    recipe_name: str,
    machine_name: str,
    machine_count: int,
    columns: int = 4,
    gap: int = 1,
) -> SpatialLayout:
    """Plan a layout from an observed catalog snapshot.

    The snapshot has to contain the observed recipe and the observed machine
    prototype, including the observed machine size. A snapshot without them
    is refused: the layout would have to invent the footprint.
    """
    recipes = observations.get("recipes")
    machines = observations.get("machines")
    if not isinstance(recipes, Sequence) or isinstance(recipes, (str, bytes)):
        raise LayoutError("The observed catalog has no recipe list")
    if not isinstance(machines, Sequence) or isinstance(machines, (str, bytes)):
        raise LayoutError("The observed catalog has no machine list")

    recipe = next(
        (row for row in recipes
         if isinstance(row, Mapping) and row.get("name") == recipe_name),
        None)
    if recipe is None:
        raise LayoutError(
            f"The observed catalog does not contain the recipe {recipe_name!r}")
    machine = next(
        (row for row in machines
         if isinstance(row, Mapping) and row.get("name") == machine_name),
        None)
    if machine is None:
        raise LayoutError(
            f"The observed catalog does not contain the machine {machine_name!r}")
    return plan_layout(
        recipe, machine,
        machine_count=machine_count,
        columns=columns,
        gap=gap,
    )
