"""Editable observed production chains; optimization stays off the GUI thread."""
from __future__ import annotations

import threading
from importlib import import_module

from observed_flow import solve_observed_flow
from production_flow import FlowRequest

w = import_module("PySide6.QtWidgets")
c = import_module("PySide6.QtCore")


def parse_materials(text: str, divisor: float = 60) -> dict[str, float]:
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name.startswith(("item:", "fluid:")) or name in result:
            raise ValueError("Use one unique item:name = amount or fluid:name = amount per line")
        result[name] = float(value.strip()) / divisor
    return result


class FlowPlannerWidget(w.QWidget):
    finished = c.Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.snapshot = None
        self.last_result = None
        self._generation = 0
        self._busy = False
        root = w.QVBoxLayout(self)
        form = w.QFormLayout()
        self.output = w.QLineEdit()
        self.output.setPlaceholderText("item:prototype-name or fluid:prototype-name")
        self.rate = w.QDoubleSpinBox()
        self.rate.setRange(.01, 100000000)
        self.rate.setValue(60)
        self.rate.setSuffix(" / min")
        form.addRow("Output", self.output)
        form.addRow("Target", self.rate)
        self.objective = w.QComboBox()
        self.objective.addItems(["Fewest machines", "Lowest working energy"])
        form.addRow("Optimize", self.objective)
        root.addLayout(form)
        self.editors = {}
        for key, title in (("supplies", "Sustained inputs / min"),
                           ("surplus", "Allowed surplus removal / min"),
                           ("seeds", "Startup inventory (item counts, not rates)")):
            root.addWidget(w.QLabel(title))
            edit = w.QPlainTextEdit()
            edit.setPlaceholderText("item:prototype-name = amount")
            edit.setMaximumHeight(75)
            self.editors[key] = edit
            root.addWidget(edit)
        self.expected = w.QCheckBox("Allow known expected yields (not guaranteed output)")
        root.addWidget(self.expected)
        self.calculate_button = w.QPushButton("Solve production chain")
        self.calculate_button.clicked.connect(self.calculate)
        self.calculate_button.setEnabled(False)
        root.addWidget(self.calculate_button)
        self.summary = w.QLabel("Load a complete current catalog to plan production chains.")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.table = w.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Process / material", "Machines / flow", "Amount"])
        self.table.setEditTriggers(w.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)
        self.finished.connect(self._finished)

    def set_catalog(self, snapshot):
        self.snapshot = snapshot
        self._generation += 1
        self.last_result = None
        self.table.setRowCount(0)
        valid = bool(snapshot and snapshot.complete)
        self.calculate_button.setEnabled(valid and not self._busy)
        self.summary.setText("Catalog ready. Enter sustained inputs and explicit surplus limits." if valid
                             else "Complete current catalog required; previous results invalidated.")

    def calculate(self):
        snapshot = self.snapshot
        if self._busy or snapshot is None or not snapshot.complete:
            return False
        try:
            request = FlowRequest({self.output.text().strip(): self.rate.value()/60},
                parse_materials(self.editors["supplies"].toPlainText()),
                parse_materials(self.editors["surplus"].toPlainText()),
                parse_materials(self.editors["seeds"].toPlainText(), 1))
        except (ValueError, TypeError) as exc:
            self.summary.setText(str(exc))
            return False
        generation = self._generation
        expected = self.expected.isChecked()
        objective = "machines" if self.objective.currentIndex() == 0 else "power"
        self._busy = True
        self.calculate_button.setEnabled(False)
        self.summary.setText("Solving observed alternatives…")

        def work():
            try:
                result = solve_observed_flow(snapshot, request, allow_expected=expected, objective=objective)
            except Exception as exc:
                result = {"status": "unavailable", "reason": str(exc)}
            try:
                self.finished.emit(generation, result)
            except RuntimeError:
                pass  # Widget closed while the bounded solver was finishing.

        threading.Thread(target=work, name="production-flow", daemon=True).start()
        return True

    def _finished(self, generation, result):
        self._busy = False
        self.calculate_button.setEnabled(bool(self.snapshot and self.snapshot.complete))
        if generation != self._generation:
            return
        self.last_result = result
        rows = []
        for name, count in result.get("machines", {}).items():
            rows.append((name, "machines", str(count)))
        for field, label in (("imports_per_second", "input / min"),
                             ("surplus_per_second", "surplus / min")):
            rows.extend((name, label, f"{amount*60:g}") for name, amount in result.get(field, {}).items())
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                self.table.setItem(row, column, w.QTableWidgetItem(value))
        message = result.get("reason") or result.get("scope", "")
        self.summary.setText(f"{result['status']} • {result.get('basis', 'no accepted solution')}\n{message}\n"
                             + result.get("assumptions", ""))
