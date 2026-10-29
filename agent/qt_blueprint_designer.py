"""AI Helper blueprint draft designer backed by the observed R06 calculator.

This is the first physically explicit creator: user target, observed recipe,
observed machine, bounded throughput arithmetic and valid Factorio export.
A separate LLM layout-planning/transport validation pipeline is NOT present.
"""
from __future__ import annotations

import math
from importlib import import_module
from typing import Any

from blueprint_design_engine import generate_draft
from production_solver import compute_target_production
from qt_catalog import CatalogSnapshot
from qt_recipe_planner import compatible_machines, product_targets

qtw = import_module("PySide6.QtWidgets")
qtc = import_module("PySide6.QtCore")
Signal = qtc.Signal


class BlueprintDesigner(qtw.QWidget):
    generated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot: CatalogSnapshot | None = None
        self._recipes: list[dict[str, Any]] = []
        self._machines: list[dict[str, Any]] = []
        self.last_generated: dict[str, Any] | None = None

        layout = qtw.QVBoxLayout(self)
        layout.setSpacing(10)
        heading = qtw.QLabel("CUSTOM BLUEPRINT CREATOR")
        heading.setObjectName("heading")
        layout.addWidget(heading)
        intro = qtw.QLabel(
            "Design from observed recipes, research availability and compatible machines. "
            "Exports editable Factorio blueprint DRAFTS. Full belt/fluid/power routing "
            "and actual LLM-generated layouts are not implemented.")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = qtw.QFormLayout()
        self.search = qtw.QLineEdit()
        self.search.setObjectName("designerRecipeSearch")
        self.search.setPlaceholderText("What should the factory produce? Search any observed mod recipe")
        self.search.textChanged.connect(self.filter_recipes)
        form.addRow("Goal / search", self.search)

        self.recipe = qtw.QComboBox()
        self.recipe.setObjectName("designerRecipe")
        self.recipe.currentIndexChanged.connect(self._update_machines)
        form.addRow("Recipe", self.recipe)
        self.machine = qtw.QComboBox()
        self.machine.setObjectName("designerMachine")
        form.addRow("Machine", self.machine)
        self.target = qtw.QComboBox()
        form.addRow("Product", self.target)
        self.rate = qtw.QDoubleSpinBox()
        self.rate.setRange(0.01, 1e8)
        self.rate.setValue(120)
        self.rate.setSuffix(" / min")
        form.addRow("Target rate", self.rate)
        self.spacing = qtw.QSpinBox()
        self.spacing.setRange(4, 32)
        self.spacing.setValue(8)
        form.addRow("Draft spacing", self.spacing)
        self.columns = qtw.QSpinBox()
        self.columns.setRange(1, 12)
        self.columns.setValue(8)
        form.addRow("Machines / row", self.columns)
        layout.addLayout(form)

        self.generate_button = qtw.QPushButton("Generate blueprint from observed plan")
        self.generate_button.setObjectName("tool")
        self.generate_button.clicked.connect(self.generate)
        layout.addWidget(self.generate_button)
        self.status = qtw.QLabel("No observed recipe catalog loaded.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.preview = qtw.QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Calculated machine count, factory draft and limitations appear here")
        layout.addWidget(self.preview, 1)
        layout.addStretch(0)
        self.generate_button.setEnabled(False)

    def set_snapshot(self, snapshot: CatalogSnapshot) -> None:
        self.snapshot = snapshot
        self.filter_recipes()

    def filter_recipes(self) -> None:
        source = self.snapshot.recipes if self.snapshot else ()
        query = self.search.text().strip().casefold().replace(" ", "-")
        result = [dict(recipe) for recipe in source
                  if isinstance(recipe.get("name"), str)
                  and query in recipe["name"].casefold()][:500]
        self._recipes = result
        self.recipe.blockSignals(True)
        self.recipe.clear()
        for recipe in result:
            label = recipe["name"]
            if recipe.get("enabled") is False:
                label += " [locked]"
            self.recipe.addItem(label)
        self.recipe.blockSignals(False)
        self._update_machines()
        self.status.setText(
            f"{len(result)} matching observed recipes shown "
            f"of {len(source)} loaded • "
            f"catalog: {self.snapshot.status if self.snapshot else 'unavailable'}.")

    def _update_machines(self, *_args) -> None:
        row = self.recipe.currentIndex()
        self.machine.clear()
        self.target.clear()
        self._machines = []
        if not 0 <= row < len(self._recipes):
            self.generate_button.setEnabled(False)
            return
        recipe = self._recipes[row]
        self._machines = [dict(m) for m in compatible_machines(
            recipe, self.snapshot.machines if self.snapshot else ())]
        for item in self._machines:
            self.machine.addItem(
                f"{item['name']} • speed {item.get('crafting_speed', 'unknown')}")
        for kind, name in product_targets(recipe):
            self.target.addItem(f"{kind}:{name}", (kind, name))
        self.generate_button.setEnabled(
            bool(self._machines and self.target.count())
            and recipe.get("enabled") is True
            and recipe.get("hidden") is not True
            and self.snapshot is not None
            and bool(self.snapshot.source_fingerprint))

    def load_plan(self, plan: dict[str, Any]) -> None:
        """Accept a calculated Recipes-page plan without inventing its inputs."""
        if not isinstance(plan, dict):
            return
        name = str((plan.get("recipe") or {}).get("name") or "")
        self.search.setText(name)
        for i, recipe in enumerate(self._recipes):
            if recipe["name"] == name:
                self.recipe.setCurrentIndex(i)
                break
        machine_name = (plan.get("machine") or {}).get("name")
        for i, machine in enumerate(self._machines):
            if machine.get("name") == machine_name:
                self.machine.setCurrentIndex(i)
                break
        target = plan.get("target") or {}
        per_minute = target.get("per_minute")
        if isinstance(per_minute, (float, int)) and 0 < per_minute < 1e8:
            self.rate.setValue(float(per_minute))
        self.status.setText(f"Plan received for {name}. Review and generate a draft.")

    def generate(self) -> dict[str, Any] | None:
        if not self.generate_button.isEnabled() or self.snapshot is None:
            self.status.setText("Cannot generate: an observed unlocked recipe and machine are required.")
            return None
        recipe = self._recipes[self.recipe.currentIndex()]
        machine = self._machines[self.machine.currentIndex()]
        kind, product = self.target.currentData()
        speed = machine.get("crafting_speed")
        if (not isinstance(speed, (float, int)) or isinstance(speed, bool)
                or not math.isfinite(float(speed)) or speed <= 0):
            self.status.setText("Cannot calculate: observed machine speed unavailable.")
            return None
        power = machine.get("energy_usage")
        power_kw = (float(power) / 1000 if isinstance(power, (float, int))
                    and not isinstance(power, bool) and math.isfinite(float(power))
                    else None)
        try:
            estimate = compute_target_production(
                [recipe], kind, product, per_minute=self.rate.value(),
                machine_speed=float(speed), machine_name=machine["name"],
                machine_energy_kw=power_kw)
            machine_count = (
                math.ceil(estimate.machine_count)
                if isinstance(estimate.machine_count, (int, float))
                and estimate.machine_count > 0 else None)
            plan = {
                "recipe": recipe, "machine": machine,
                "target": {"type": kind, "name": product, "per_minute": self.rate.value()},
                "machine_count": machine_count,
                "status": estimate.status,
                "source_fingerprint": self.snapshot.source_fingerprint,
                "game_version": self.snapshot.game_version,
            }
            result = generate_draft(
                plan, spacing=self.spacing.value(), columns=self.columns.value())
        except (ValueError, TypeError, OverflowError) as exc:
            self.status.setText(f"Cannot generate a qualified draft: {str(exc)[:180]}")
            return None
        self.last_generated = result
        self.status.setText(
            f"Draft generated: {result['machine_count']} observed "
            "machines. Exchange validated. NOT buildability verified.")
        self.preview.setPlainText(
            "\n".join([f"Recipe: {recipe['name']}",
                       f"Machines: {machine_count} × {machine['name']}",
                       f"Target: {self.rate.value():g} {product}/min",
                       f"Source fingerprint: {self.snapshot.source_fingerprint}",
                       "", *result["warnings"]]))
        self.generated.emit(result)
        return result
