"""Qt widget for the observed inventory and logistics state.

The widget renders the shared R10-B snapshot from
:mod:`qt_inventory_observations`. It shows only the fields the game
actually reported, and it shows an explicit *unavailable* row for the
sections the observation protocol did not produce.

Two workspaces use this widget:

* **Inventory** shows the machine, chest, wagon and tank inventories with
  their item quantities, their qualities and their capacities, the
  logistic network contents, the robot availability and the transport and
  storage summaries.
* **Logistics** shows the logistic networks, the robot availability and
  the transport and storage rows.

The widget never fetches anything itself. It is fed by the shell, which
owns the observation transport.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

from qt_inventory_observations import (
    InventoryObservation,
    ObservedInventory,
    ObservedMachine,
    ObservedTransport,
    inventory_observation,
)

qt_core = import_module("PySide6.QtCore")
qt_widgets = import_module("PySide6.QtWidgets")

QAbstractItemView = qt_widgets.QAbstractItemView
QHeaderView = qt_widgets.QHeaderView
QHBoxLayout = qt_widgets.QHBoxLayout
QLabel = qt_widgets.QLabel
QLineEdit = qt_widgets.QLineEdit
QPushButton = qt_widgets.QPushButton
QSignalBlocker = qt_core.QSignalBlocker
QSplitter = qt_widgets.QSplitter
QTabWidget = qt_widgets.QTabWidget
QTableWidget = qt_widgets.QTableWidget
QTableWidgetItem = qt_widgets.QTableWidgetItem
QVBoxLayout = qt_widgets.QVBoxLayout
QWidget = qt_widgets.QWidget

#: The Qt signal class used for the user-driven requests.
Signal = qt_core.Signal

#: The maximum number of rows rendered in one table.
MAX_VISIBLE_ROWS = 500

#: The columns of the player inventory table.
INVENTORY_COLUMNS = ("Item", "Quality", "Count", "Slot")

#: The columns of the production and consumption table.
PRODUCTION_COLUMNS = (
    "Item or fluid",
    "Produced / 5 s",
    "Consumed / 5 s",
    "Produced / s",
    "Consumed / s",
)

#: The columns of the electrical network table.
NETWORK_COLUMNS = (
    "Network",
    "Max production",
    "Max consumption",
    "Consumption satisfied",
    "Production satisfied",
    "Accumulator",
)

#: The columns of the roboport logistic cell table.
LOGISTICS_COLUMNS = (
    "Roboport",
    "Logistic radius",
    "Construction radius",
    "Transmitting",
)

#: The columns of the observed machine inventory table.
MACHINE_COLUMNS = (
    "Entity",
    "Type",
    "Position",
    "Surface",
    "Inventory",
    "Items",
    "Quality",
    "Capacity",
)

#: The columns of the observed logistic network table.
LOGISTIC_NETWORK_COLUMNS = (
    "Network",
    "Surface",
    "Available items",
    "Providers",
    "Requesters",
    "Storages",
)

#: The columns of the observed robot availability table.
ROBOT_COLUMNS = (
    "Metric",
    "Observed",
)

#: The columns of the observed transport and storage table.
TRANSPORT_COLUMNS = (
    "Entity",
    "Type",
    "Position",
    "Surface",
    "Items",
    "Fluids",
)

#: The text shown for a value that was never observed.
UNKNOWN = "—"

#: The text shown for a field the observation protocol does not provide.
UNAVAILABLE = "Unavailable"


def _number(value: Any, digits: int = 2) -> str:
    """Return bounded display text for a number."""
    if value is None:
        return UNKNOWN
    return f"{value:,.{digits}f}"


def _percent(value: Any) -> str:
    """Return bounded display text for a satisfaction ratio."""
    if value is None:
        return UNKNOWN
    return f"{value * 100:.1f}%"


def _integer(value: Any) -> str:
    """Return bounded display text for an integer."""
    if value is None:
        return UNKNOWN
    return str(value)


def _inventory_text(inventory: ObservedInventory) -> str:
    """Return the display text of one observed inventory category."""
    return inventory.category


def _inventory_items(inventory: ObservedInventory) -> str:
    """Return the display text of the items of one observed inventory."""
    if not inventory.items:
        return "empty" if inventory.empty else UNKNOWN
    return ", ".join(item.label for item in inventory.items)


def _inventory_quality(inventory: ObservedInventory) -> str:
    """Return the display text of the qualities of one observed inventory."""
    qualities = sorted({item.quality for item in inventory.items})
    if not qualities:
        return UNKNOWN
    return ", ".join(qualities)


def _machine_text(machine: ObservedMachine) -> str:
    """Return the display text of one observed machine."""
    return machine.name


def _machine_items(machine: ObservedMachine) -> str:
    """Return the display text of the items of one observed machine."""
    parts: list[str] = []
    for inventory in machine.inventories:
        if inventory.items:
            parts.append(f"{inventory.category}: "
                         + ", ".join(item.label for item in inventory.items))
        elif inventory.empty:
            parts.append(f"{inventory.category}: empty")
    for fluid in machine.fluids:
        parts.append(f"{fluid.name}: {_number(fluid.amount, 0)}")
    return "; ".join(parts) if parts else UNKNOWN


def _machine_capacity(machine: ObservedMachine) -> str:
    """Return the display text of the capacity of one observed machine."""
    capacities = [str(inventory.capacity) for inventory in machine.inventories
                  if inventory.capacity is not None]
    return ", ".join(capacities) if capacities else UNKNOWN


def _transport_items(transport: ObservedTransport) -> str:
    """Return the display text of the items of one transport entity."""
    parts: list[str] = []
    for inventory in transport.inventories:
        if inventory.items:
            parts.append(", ".join(item.label for item in inventory.items))
    for item in transport.train_items:
        parts.append(f"{item.label} x{item.count}")
    return "; ".join(parts) if parts else UNKNOWN


def _transport_fluids(transport: ObservedTransport) -> str:
    """Return the display text of the fluids of one transport entity."""
    parts: list[str] = []
    for fluid in transport.fluids:
        parts.append(f"{fluid.name}: {_number(fluid.amount, 0)}")
    for fluid in transport.train_fluids:
        parts.append(f"{fluid.name}: {_number(fluid.amount, 0)}")
    return "; ".join(parts) if parts else UNKNOWN


class InventoryWidget(QWidget):
    """Render one shared observed inventory and logistics snapshot."""

    #: Emitted when the user wants the observation re-read from the game.
    refreshRequested = Signal()

    #: Emitted when the user wants the next page of the observation.
    loadMoreRequested = Signal()

    def __init__(self, parent: QWidget | None = None, *, scope: str = "inventory"):
        """Create the widget.

        ``scope`` is either ``inventory`` or ``logistics``. It selects the
        tables that are shown; both use the same observed snapshot.
        """
        super().__init__(parent)
        if scope not in ("inventory", "logistics"):
            raise ValueError("Unknown inventory widget scope")
        self.scope = scope
        self._snapshot: InventoryObservation | None = None
        self._player_snapshot = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.status = QLabel("Inventory not observed")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip(
            "Re-read the observed inventories and logistics from the game")
        self.refresh_button.clicked.connect(self.refreshRequested)
        controls.addWidget(self.refresh_button)

        self.load_more_button = QPushButton("Load more")
        self.load_more_button.setToolTip(
            "Request the next page of the observed inventories")
        self.load_more_button.clicked.connect(self.loadMoreRequested)
        self.load_more_button.setEnabled(False)
        controls.addWidget(self.load_more_button)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search entities, items, fluids or networks")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        controls.addWidget(self.search, 1)

        layout.addLayout(controls)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.inventory_table = self._make_table(INVENTORY_COLUMNS)
        self.production_table = self._make_table(PRODUCTION_COLUMNS)
        self.network_table = self._make_table(NETWORK_COLUMNS)
        self.logistics_table = self._make_table(LOGISTICS_COLUMNS)
        self.machine_table = self._make_table(MACHINE_COLUMNS)
        self.logistic_network_table = self._make_table(LOGISTIC_NETWORK_COLUMNS)
        self.robot_table = self._make_table(ROBOT_COLUMNS)
        self.transport_table = self._make_table(TRANSPORT_COLUMNS)
        self.unsupported = QLabel("")
        self.unsupported.setObjectName("muted")
        self.unsupported.setWordWrap(True)

        if scope == "inventory":
            self.tabs.addTab(self.machine_table, "Machines")
            self.tabs.addTab(self.inventory_table, "Player inventory")
            self.tabs.addTab(self.production_table, "Production")
            self.tabs.addTab(self.network_table, "Electrical")
        else:
            self.tabs.addTab(self.logistic_network_table, "Networks")
            self.tabs.addTab(self.robot_table, "Robots")
            self.tabs.addTab(self.transport_table, "Transport")
            self.tabs.addTab(self.logistics_table, "Roboports")
        layout.addWidget(self.unsupported)

    @staticmethod
    def _make_table(columns: tuple[str, ...]):
        """Return one bounded read-only table."""
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @property
    def snapshot(self) -> InventoryObservation | None:
        """Return the current immutable snapshot."""
        return self._snapshot

    def set_frame(self, frame: Mapping[str, Any] | None, *,
                  state: str = "observed",
                  detail: str = "Observed inventory") -> None:
        """Show one observed ``autoengineer_view`` frame.

        The R10-A view frame carries the player inventory, the production
        statistics and the electrical networks. Those are still read here,
        so the workspace keeps showing the telemetry it always showed.
        """
        source = frame if isinstance(frame, Mapping) else {}
        self._fill_player_inventory(source)
        self._fill_production(source)
        self._fill_electrical(source)
        self._fill_roboports(source)
        self.set_snapshot(inventory_observation(None, state=state,
                                                detail=detail))

    def set_observation(self, frame: Mapping[str, Any] | None, *,
                        state: str = "observed",
                        detail: str = "Observed inventory and logistics"
                        ) -> None:
        """Show one observed ``autoengineer_inventory`` frame."""
        self.set_snapshot(inventory_observation(frame, state=state,
                                                detail=detail))

    def set_snapshot(self, snapshot: InventoryObservation) -> None:
        """Show one immutable snapshot."""
        self._snapshot = snapshot
        self.status.setText(snapshot.status_text())
        self.load_more_button.setEnabled(snapshot.has_more_machines)
        self._fill_machines(snapshot)
        self._fill_logistic_networks(snapshot)
        self._fill_robots(snapshot)
        self._fill_transport(snapshot)
        self._fill_unsupported(snapshot)
        self._apply_filter()

    # -- the R10-A view frame -------------------------------------------

    def _fill_player_inventory(self, frame: Mapping[str, Any]) -> None:
        """Show the observed player inventory of the view frame."""
        rows = frame.get("inventory")
        entries = rows if isinstance(rows, list) else []
        visible = entries[:MAX_VISIBLE_ROWS]
        self.inventory_table.setRowCount(len(visible))
        for index, entry in enumerate(visible):
            if not isinstance(entry, Mapping):
                continue
            name = entry.get("name")
            count = entry.get("count")
            quality = entry.get("quality") or "normal"
            if not isinstance(name, str) or not isinstance(count, int):
                continue
            slot = entry.get("slot")
            values = (
                name if quality == "normal" else f"{name} ({quality})",
                str(quality),
                str(count),
                str(slot) if isinstance(slot, int) else UNKNOWN,
            )
            for column, value in enumerate(values):
                self.inventory_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_production(self, frame: Mapping[str, Any]) -> None:
        """Show the observed production rows of the view frame."""
        telemetry = frame.get("telemetry")
        telemetry = telemetry if isinstance(telemetry, Mapping) else {}
        production = telemetry.get("production")
        production = production if isinstance(production, Mapping) else {}
        rows: list[Mapping[str, Any]] = []
        for key in ("items", "fluids"):
            group = production.get(key)
            if isinstance(group, list):
                rows.extend(row for row in group if isinstance(row, Mapping))
        visible = rows[:MAX_VISIBLE_ROWS]
        self.production_table.setRowCount(len(visible))
        for index, row in enumerate(visible):
            window = row.get("five_seconds")
            window = window if isinstance(window, Mapping) else {}
            values = (
                str(row.get("name", UNKNOWN)),
                _number(window.get("produced"), 0),
                _number(window.get("consumed"), 0),
                _number(window.get("per_second_produced")),
                _number(window.get("per_second_consumed")),
            )
            for column, value in enumerate(values):
                self.production_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_electrical(self, frame: Mapping[str, Any]) -> None:
        """Show the observed electrical networks of the view frame."""
        telemetry = frame.get("telemetry")
        telemetry = telemetry if isinstance(telemetry, Mapping) else {}
        power = telemetry.get("power")
        power = power if isinstance(power, Mapping) else {}
        rows = power.get("networks")
        rows = rows if isinstance(rows, list) else []
        visible = rows[:MAX_VISIBLE_ROWS]
        self.network_table.setRowCount(len(visible))
        for index, row in enumerate(visible):
            if not isinstance(row, Mapping):
                continue
            values = (
                str(row.get("network_id", UNKNOWN)),
                _number(row.get("maximum_production"), 0),
                _number(row.get("maximum_consumption"), 0),
                _percent(row.get("consumption_satisfaction")),
                _percent(row.get("production_satisfaction")),
                _number(row.get("accumulator_energy"), 0),
            )
            for column, value in enumerate(values):
                self.network_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_roboports(self, frame: Mapping[str, Any]) -> None:
        """Show the observed roboport logistic cells of the view frame."""
        overlays = frame.get("overlays")
        overlays = overlays if isinstance(overlays, Mapping) else {}
        available = overlays.get("available")
        available = available if isinstance(available, Mapping) else {}
        rows = overlays.get("logistics")
        rows = rows if isinstance(rows, list) else []
        visible = rows[:MAX_VISIBLE_ROWS]
        self.logistics_table.setRowCount(len(visible))
        for index, row in enumerate(visible):
            if not isinstance(row, Mapping):
                continue
            x = row.get("x")
            y = row.get("y")
            position = (f"({float(x):.0f}, {float(y):.0f})"
                        if isinstance(x, (int, float))
                        and isinstance(y, (int, float)) else UNKNOWN)
            values = (
                position,
                _number(row.get("logistic"), 0),
                _number(row.get("construction"), 0),
                "Yes" if row.get("active") is True else "No",
            )
            for column, value in enumerate(values):
                self.logistics_table.setItem(
                    index, column, QTableWidgetItem(value))

    # -- the user-driven filter -----------------------------------------

    def _filter_text(self) -> str:
        """Return the current search text, lower-cased."""
        return self.search.text().strip().lower()

    def _apply_filter(self) -> None:
        """Show only the rows that match the search text.

        The filter is applied to the **rendered** rows only. The observed
        snapshot is never modified, so the counts in the status line keep
        reporting the real number of observed rows.
        """
        needle = self._filter_text()
        for table in (self.machine_table, self.logistic_network_table,
                      self.transport_table):
            table.setVisible(True)
        if not needle:
            self._show_all_rows()
            return
        self._hide_unmatched(self.machine_table, needle)
        self._hide_unmatched(self.logistic_network_table, needle)
        self._hide_unmatched(self.transport_table, needle)

    def _show_all_rows(self) -> None:
        """Show every rendered row again."""
        for table in (self.machine_table, self.logistic_network_table,
                      self.transport_table):
            for index in range(table.rowCount()):
                table.setRowHidden(index, False)

    @staticmethod
    def _hide_unmatched(table, needle: str) -> None:
        """Hide the rows of one table that do not match the search text."""
        for index in range(table.rowCount()):
            matched = False
            for column in range(table.columnCount()):
                item = table.item(index, column)
                if item is not None and needle in item.text().lower():
                    matched = True
                    break
            table.setRowHidden(index, not matched)

    @property
    def visible_machine_rows(self) -> int:
        """The number of machine rows the search currently shows."""
        return sum(1 for index in range(self.machine_table.rowCount())
                   if not self.machine_table.isRowHidden(index))

    @property
    def visible_network_rows(self) -> int:
        """The number of logistic network rows the search currently shows."""
        return sum(1 for index in range(self.logistic_network_table.rowCount())
                   if not self.logistic_network_table.isRowHidden(index))

    @property
    def visible_transport_rows(self) -> int:
        """The number of transport rows the search currently shows."""
        return sum(1 for index in range(self.transport_table.rowCount())
                   if not self.transport_table.isRowHidden(index))

    def _fill_machines(self, snapshot: InventoryObservation) -> None:
        rows = snapshot.machines[:MAX_VISIBLE_ROWS]
        self.machine_table.setRowCount(len(rows))
        for index, machine in enumerate(rows):
            categories = ", ".join(
                _inventory_text(inventory) for inventory in machine.inventories)
            qualities = ", ".join(sorted({
                item.quality
                for inventory in machine.inventories
                for item in inventory.items})) or UNKNOWN
            values = (
                _machine_text(machine),
                machine.entity_type,
                machine.position,
                machine.surface,
                categories or UNKNOWN,
                _machine_items(machine),
                qualities,
                _machine_capacity(machine),
            )
            for column, value in enumerate(values):
                self.machine_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_logistic_networks(self, snapshot: InventoryObservation) -> None:
        rows = snapshot.networks[:MAX_VISIBLE_ROWS]
        self.logistic_network_table.setRowCount(len(rows))
        for index, network in enumerate(rows):
            values = (
                network.label,
                network.surface,
                ", ".join(f"{item.label} x{item.count}"
                          for item in network.items) or UNKNOWN,
                ", ".join(network.providers) or UNKNOWN,
                ", ".join(network.requesters) or UNKNOWN,
                ", ".join(network.storages) or UNKNOWN,
            )
            for column, value in enumerate(values):
                self.logistic_network_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_robots(self, snapshot: InventoryObservation) -> None:
        robots = snapshot.robots
        rows = [
            ("Logistic robots available",
             _integer(robots.available_logistic_robots)),
            ("Logistic robots total",
             _integer(robots.total_logistic_robots)),
            ("Logistic robots busy",
             _integer(robots.busy_logistic_robots)),
            ("Construction robots available",
             _integer(robots.available_construction_robots)),
            ("Construction robots total",
             _integer(robots.total_construction_robots)),
            ("Construction robots busy",
             _integer(robots.busy_construction_robots)),
            ("Robot limit", _integer(robots.robot_limit)),
            ("Logistic networks", _integer(robots.networks)),
        ]
        self.robot_table.setRowCount(len(rows))
        for index, (name, value) in enumerate(rows):
            self.robot_table.setItem(index, 0, QTableWidgetItem(name))
            self.robot_table.setItem(index, 1, QTableWidgetItem(value))

    def _fill_transport(self, snapshot: InventoryObservation) -> None:
        rows = snapshot.transport[:MAX_VISIBLE_ROWS]
        self.transport_table.setRowCount(len(rows))
        for index, transport in enumerate(rows):
            values = (
                transport.name,
                transport.entity_type,
                f"({transport.x:.0f}, {transport.y:.0f})"
                if transport.x is not None and transport.y is not None
                else UNKNOWN,
                transport.surface,
                _transport_items(transport),
                _transport_fluids(transport),
            )
            for column, value in enumerate(values):
                self.transport_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_unsupported(self, snapshot: InventoryObservation) -> None:
        """Name every section the observation protocol did not produce."""
        gaps = [
            ("Machine inventories",
             snapshot.machines_state, snapshot.machines_reason),
            ("Logistic networks",
             snapshot.networks_state, snapshot.networks_reason),
            ("Robot counts", snapshot.robots_state, snapshot.robots_reason),
            ("Transport and storage",
             snapshot.transport_state, snapshot.transport_reason),
        ]
        text = " · ".join(
            f"{name}: {UNAVAILABLE} ({reason})"
            for name, state, reason in gaps if state != "observed")
        self.unsupported.setText(text)


__all__ = [
    "INVENTORY_COLUMNS",
    "LOGISTICS_COLUMNS",
    "LOGISTIC_NETWORK_COLUMNS",
    "MACHINE_COLUMNS",
    "MAX_VISIBLE_ROWS",
    "NETWORK_COLUMNS",
    "PRODUCTION_COLUMNS",
    "ROBOT_COLUMNS",
    "TRANSPORT_COLUMNS",
    "UNAVAILABLE",
    "UNKNOWN",
    "InventoryWidget",
]
