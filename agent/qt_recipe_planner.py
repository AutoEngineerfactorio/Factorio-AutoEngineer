"""Helmod-like observed production planning workspace.

The existing R10-A CatalogWidget remains the live paged recipe browser. A
selected recipe and observed compatible crafting machine are passed to the R06
production solver. No machine, recipe, speed or research unlock is fabricated.
"""
from __future__ import annotations

import math
from importlib import import_module
from typing import Any, Mapping

from production_solver import compute_target_production
from qt_catalog import CatalogSnapshot
from qt_catalog_widget import CatalogWidget
from qt_flow_planner import FlowPlannerWidget

qtw = import_module("PySide6.QtWidgets")
qtc = import_module("PySide6.QtCore")
Qt = qtc.Qt
Signal = qtc.Signal


def finite_number(value: Any, *, positive: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and (not positive or number > 0) else None


def compatible_machines(recipe: Mapping[str, Any],
                        machines: tuple[Mapping[str, Any], ...]) -> list[Mapping[str, Any]]:
    """Only machines observed to support one of the recipe's categories."""
    categories = recipe.get("categories") or (
        [recipe["category"]] if isinstance(recipe.get("category"), str) else [])
    if not isinstance(categories, (list, tuple)):
        return []
    wanted = set(category for category in categories if isinstance(category, str))
    return [machine for machine in machines
            if isinstance(machine.get("name"), str)
            and isinstance(machine.get("crafting_categories"), (list, tuple))
            and wanted.intersection(machine["crafting_categories"])]


def product_targets(recipe: Mapping[str, Any]) -> list[tuple[str, str]]:
    parts = recipe.get("products")
    if not isinstance(parts, (list, tuple)):
        return []
    return [(str(part.get("type", "item")), str(part["name"]))
            for part in parts
            if isinstance(part, Mapping) and isinstance(part.get("name"), str)]


class RecipePlannerWidget(qtw.QWidget):
    """Live catalog browser plus actionable production-rate calculator."""

    planReady = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = CatalogWidget()
        self.catalog.research_table.hide()
        self.selected: Mapping[str, Any] | None = None
        self.last_plan: dict[str, Any] | None = None
        self._machines: list[Mapping[str, Any]] = []

        root = qtw.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.banner = qtw.QLabel(
            "PRODUCTION PLANNER  •  Helmod-style targets, machine counts, inputs and byproducts "
            "from the active observed catalog. Estimates, not measured throughput.")
        self.banner.setWordWrap(True)
        self.banner.setObjectName("muted")
        root.addWidget(self.banner)
        split = qtw.QSplitter(Qt.Horizontal)
        split.addWidget(self.catalog)

        panel = qtw.QWidget()
        side = qtw.QVBoxLayout(panel)
        side.setContentsMargins(8, 0, 0, 0)
        side.addWidget(qtw.QLabel("PRODUCTION LINE"))
        self.recipe_name = qtw.QLabel("Select a recipe in the catalog.")
        self.recipe_name.setWordWrap(True)
        side.addWidget(self.recipe_name)
        form = qtw.QFormLayout()
        self.target = qtw.QComboBox()
        form.addRow("Output", self.target)
        self.rate = qtw.QDoubleSpinBox()
        self.rate.setDecimals(2)
        self.rate.setRange(0.01, 100000000)
        self.rate.setValue(60)
        self.rate.setSuffix(" / min")
        form.addRow("Target", self.rate)
        self.machine = qtw.QComboBox()
        form.addRow("Machine", self.machine)
        side.addLayout(form)
        self.calculate_button = qtw.QPushButton("Calculate production line")
        self.calculate_button.clicked.connect(self.calculate)
        side.addWidget(self.calculate_button)
        self.summary = qtw.QLabel("Choose a recipe to calculate expected production.")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        side.addWidget(self.summary)
        self.flow = qtw.QTableWidget(0, 3)
        self.flow.setHorizontalHeaderLabels(["Material", "Direction", "Units/min"])
        self.flow.setEditTriggers(qtw.QAbstractItemView.NoEditTriggers)
        self.flow.horizontalHeader().setStretchLastSection(True)
        side.addWidget(qtw.QLabel("OBSERVED MATERIAL FLOW"))
        side.addWidget(self.flow, 1)
        self.limitations = qtw.QLabel(
            "Select a recipe. Unknown input amounts and unsupported mechanics are shown explicitly.")
        self.limitations.setWordWrap(True)
        self.limitations.setObjectName("muted")
        side.addWidget(self.limitations)
        self.create_blueprint_button = qtw.QPushButton("Send plan to Blueprint Studio")
        self.create_blueprint_button.setEnabled(False)
        self.create_blueprint_button.clicked.connect(self.send_plan)
        side.addWidget(self.create_blueprint_button)
        tabs = qtw.QTabWidget()
        tabs.addTab(panel, "Single recipe")
        self.chain = FlowPlannerWidget()
        tabs.addTab(self.chain, "Production chain")
        split.addWidget(tabs)
        split.setSizes([910, 430])
        root.addWidget(split, 1)
        self.catalog.recipe_table.itemSelectionChanged.connect(self._recipe_selected)

    def set_snapshot(self, snapshot: CatalogSnapshot) -> None:
        self.catalog.set_snapshot(snapshot)
        self.chain.set_catalog(snapshot)
        self.selected = None
        self.recipe_name.setText("Select a recipe in the catalog.")
        self.create_blueprint_button.setEnabled(False)

    def _recipe_selected(self) -> None:
        row = self.catalog.recipe_table.currentRow()
        name_item = self.catalog.recipe_table.item(row, 0) if row >= 0 else None
        snapshot = self.catalog.snapshot
        if name_item is None or snapshot is None:
            return
        name = name_item.text()
        self.selected = next((r for r in snapshot.recipes if r.get("name") == name), None)
        if self.selected is None:
            return
        self.recipe_name.setText(name)
        self.target.clear()
        for kind, product in product_targets(self.selected):
            self.target.addItem(f"{kind}:{product}", (kind, product))
        if self.target.count():
            kind, product = self.target.currentData()
            self.chain.output.setText(f"{kind}:{product}")
        self.machine.clear()
        self._machines = compatible_machines(self.selected, snapshot.machines)
        for machine in self._machines:
            speed = machine.get("crafting_speed")
            self.machine.addItem(f"{machine['name']}  (speed {speed if speed is not None else '?'})")
        if not self._machines:
            self.machine.addItem("No compatible observed machine — rate unavailable")
        self.calculate()

    def calculate(self) -> dict[str, Any] | None:
        recipe = self.selected
        snapshot = self.catalog.snapshot
        if recipe is None or snapshot is None or self.target.count() == 0:
            return None
        if not snapshot.complete or recipe not in snapshot.recipes:
            self.last_plan = None
            self.create_blueprint_button.setEnabled(False)
            self.summary.setText("Complete, current observed catalog required before planning")
            return None
        kind, product = self.target.currentData()
        rate = float(self.rate.value())
        machine = self._machines[self.machine.currentIndex()] if self._machines else None
        speed = machine.get("crafting_speed") if machine is not None else None
        speed = finite_number(speed, positive=True)
        power_value = machine.get("energy_usage") if machine is not None else None
        power = finite_number(power_value)
        power = power / 1000 if power is not None else None
        try:
            result = compute_target_production(
                [dict(recipe)], kind, product, per_minute=rate,
                machine_speed=speed,
                machine_name=str(machine["name"]) if machine is not None else None,
                machine_energy_kw=power)
        except (ValueError, TypeError) as exc:
            self.summary.setText("Cannot calculate: " + str(exc))
            self.create_blueprint_button.setEnabled(False)
            return None
        result_data = result.__dict__
        count = finite_number(result_data.get("machine_count"), positive=True)
        crafts = finite_number(result_data.get("crafts_per_second"))
        power_total = result_data.get("power_kw")
        self.summary.setText(
            f"Status: {result.status} • Target: {rate:g} {product}/min\n"
            f"Machines: {math.ceil(count) if isinstance(count, (float, int)) and count > 0 else 'unknown'}"
            f" • per-machine speed: {speed if speed is not None else 'unknown'}\n"
            f"Power estimate: {power_total:.2f} kW" if power_total is not None else
            f"Status: {result.status} • Target: {rate:g} {product}/min\n"
            f"Machines: {math.ceil(count) if isinstance(count, (float, int)) and count > 0 else 'unknown'}"
            f" • Power: unknown")
        material_rows: list[tuple[str, str, str]] = []
        for direction, key in (("Input", "ingredients"), ("Output", "products")):
            for part in recipe.get(key) or []:
                name = part.get("name")
                amt = part.get("amount")
                if (type(amt) in (int, float) and math.isfinite(float(amt))
                        and crafts is not None and speed is not None):
                    # Per requested throughput, not just one machine.
                    qty = float(amt) * crafts * (count if count is not None else 0) * 60
                    text = f"{qty:,.2f}"
                else:
                    text = "unknown / stochastic" if amt is None else "unverified"
                material_rows.append((str(name), direction, text))
        self.flow.setRowCount(min(len(material_rows), 64))
        for index, values in enumerate(material_rows[:64]):
            for column, value in enumerate(values):
                self.flow.setItem(index, column, qtw.QTableWidgetItem(value))
        limitations = list(result_data.get("unsupported") or [])
        if snapshot is not None and not snapshot.complete:
            limitations.append(
                f"Catalog incomplete: {len(snapshot.recipes)} of "
                f"{snapshot.total_count if snapshot.total_count is not None else '?'} recipes loaded.")
        limitations.append("No belts, inserters, logistics or buildability verified.")
        self.limitations.setText(" • ".join(limitations[:8]))
        self.last_plan = {
            "recipe": dict(recipe),
            "machine": dict(machine) if machine is not None else None,
            "target": {"type": kind, "name": product, "per_minute": rate},
            "machine_count": math.ceil(count) if count is not None else None,
            "status": result.status,
            "source_fingerprint": snapshot.source_fingerprint,
            "game_version": snapshot.game_version,
            "limitations": limitations,
        }
        self.create_blueprint_button.setEnabled(
            self.last_plan["machine"] is not None
            and self.last_plan["machine_count"] is not None
            and self.last_plan["machine_count"] <= 256
            and result.status == "estimated")
        return self.last_plan

    def send_plan(self) -> None:
        self.calculate()
        if self.last_plan and self.create_blueprint_button.isEnabled():
            self.planReady.emit(dict(self.last_plan))
