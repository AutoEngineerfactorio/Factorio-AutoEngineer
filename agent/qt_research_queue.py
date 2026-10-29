"""Separate research planning workspace; queue never executes game actions.

The observed catalog currently supplies researched names and per-recipe unlock
technology names, NOT the full technology graph or research costs. Queueing is
therefore a persistent LOCAL PLAN, never an in-game research command.
"""
from __future__ import annotations

import json
import os
import tempfile
from importlib import import_module
from pathlib import Path

from qt_catalog import CatalogSnapshot

qtw = import_module("PySide6.QtWidgets")
qt = import_module("PySide6.QtCore").Qt

DEFAULT_QUEUE = Path(__file__).resolve().parents[1] / ".local" / "research-plans" / "queue.json"
MAX_QUEUE = 256


class ResearchPlan:
    def __init__(self, path: Path = DEFAULT_QUEUE):
        self.path = Path(path)
        self.queue: list[str] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            names = data.get("queue") if isinstance(data, dict) else None
            if isinstance(names, list):
                self.queue = [x for x in names[:MAX_QUEUE]
                              if isinstance(x, str) and 0 < len(x) <= 256]
                self.queue = list(dict.fromkeys(self.queue))
        except (OSError, ValueError, TypeError):
            self.queue = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": 1, "queue": self.queue}, indent=2)
        fd, temporary = tempfile.mkstemp(prefix=".research-", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload + "\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def add(self, name: str) -> bool:
        if (not isinstance(name, str) or not name or len(name) > 256
                or name in self.queue or len(self.queue) >= MAX_QUEUE):
            return False
        self.queue.append(name)
        self.save()
        return True

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.queue):
            self.queue.pop(index)
            self.save()

    def move(self, index: int, offset: int) -> None:
        other = index + offset
        if 0 <= index < len(self.queue) and 0 <= other < len(self.queue):
            self.queue[index], self.queue[other] = self.queue[other], self.queue[index]
            self.save()


def observed_technologies(snapshot: CatalogSnapshot | None) -> list[tuple[str, str]]:
    """Find known technology names without inventing prerequisites/unlocks."""
    if snapshot is None or not snapshot.known:
        return []
    researched = set(snapshot.research)
    names = set(researched)
    for recipe in snapshot.recipes:
        unlocks = recipe.get("unlock_technologies")
        if isinstance(unlocks, (list, tuple)):
            for unlock in unlocks:
                if isinstance(unlock, dict):
                    name = unlock.get("name")
                    if isinstance(name, str) and name:
                        names.add(name)
    return [(name, "Researched" if name in researched else "Not confirmed researched")
            for name in sorted(names)]


class ResearchQueueWidget(qtw.QWidget):
    """Search observed technology identifiers and rearrange an offline queue."""

    def __init__(self, parent=None, *, queue_file: Path = DEFAULT_QUEUE):
        super().__init__(parent)
        self.plan = ResearchPlan(queue_file)
        self.snapshot: CatalogSnapshot | None = None
        layout = qtw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.banner = qtw.QLabel(
            "RESEARCH PLANNER  •  Local planning queue only — does not change the in-game research queue.")
        self.banner.setObjectName("muted")
        self.banner.setWordWrap(True)
        layout.addWidget(self.banner)
        self.status = qtw.QLabel("Load the observed catalog to discover technologies.")
        layout.addWidget(self.status)

        splitter = qtw.QSplitter(qt.Horizontal)
        browser = qtw.QWidget()
        left = qtw.QVBoxLayout(browser)
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(qtw.QLabel("OBSERVED TECHNOLOGIES & UNLOCKS"))
        self.search = qtw.QLineEdit()
        self.search.setPlaceholderText("Filter observed technologies")
        self.search.textChanged.connect(self.refresh)
        left.addWidget(self.search)
        self.available = qtw.QTableWidget(0, 2)
        self.available.setHorizontalHeaderLabels(["Technology", "Observed state"])
        self.available.setEditTriggers(qtw.QAbstractItemView.NoEditTriggers)
        self.available.setSelectionBehavior(qtw.QAbstractItemView.SelectRows)
        self.available.horizontalHeader().setStretchLastSection(True)
        left.addWidget(self.available, 1)
        self.add_button = qtw.QPushButton("Add selected to research plan")
        self.add_button.clicked.connect(self.add_selected)
        left.addWidget(self.add_button)
        splitter.addWidget(browser)

        queued = qtw.QWidget()
        right = qtw.QVBoxLayout(queued)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(qtw.QLabel("PLANNED RESEARCH ORDER"))
        self.queue_list = qtw.QListWidget()
        self.queue_list.setObjectName("plannedResearchQueue")
        right.addWidget(self.queue_list, 1)
        buttons = qtw.QHBoxLayout()
        self.up_button = qtw.QPushButton("Move up")
        self.down_button = qtw.QPushButton("Move down")
        self.remove_button = qtw.QPushButton("Remove")
        for button in (self.up_button, self.down_button, self.remove_button):
            buttons.addWidget(button)
        right.addLayout(buttons)
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        self.remove_button.clicked.connect(self.remove_selected)
        self.details = qtw.QLabel(
            "Research cost, prerequisites and the live game queue are not provided "
            "by this observation protocol; they remain unknown.")
        self.details.setWordWrap(True)
        self.details.setObjectName("muted")
        right.addWidget(self.details)
        splitter.addWidget(queued)
        splitter.setSizes([660, 390])
        layout.addWidget(splitter, 1)
        self.refresh()

    def set_snapshot(self, snapshot: CatalogSnapshot) -> None:
        self.snapshot = snapshot
        self.refresh()

    def refresh(self) -> None:
        researched = set(self.snapshot.research) if self.snapshot else set()
        technologies = observed_technologies(self.snapshot)
        filter_text = self.search.text().strip().casefold()
        matches = [(name, state) for name, state in technologies
                   if filter_text in name.casefold()][:500]
        self.available.setRowCount(len(matches))
        for row, (name, state) in enumerate(matches):
            self.available.setItem(row, 0, qtw.QTableWidgetItem(name))
            self.available.setItem(row, 1, qtw.QTableWidgetItem(state))
        self.queue_list.clear()
        for index, name in enumerate(self.plan.queue, 1):
            suffix = "✓" if name in researched else "?"
            self.queue_list.addItem(f"{index:02d}  {name}  [{suffix}]")
        known = len(technologies)
        self.status.setText(
            f"{known} observed technology names • {len(researched)} reported researched • "
            f"{len(self.plan.queue)} locally queued • Catalog: "
            f"{self.snapshot.status if self.snapshot else 'unavailable'}")
        self.add_button.setEnabled(bool(matches))

    def add_selected(self) -> None:
        row = self.available.currentRow()
        item = self.available.item(row, 0) if row >= 0 else None
        if item is None:
            self.details.setText("Select an observed technology first.")
            return
        name = item.text()
        if self.snapshot and name in self.snapshot.research:
            self.details.setText(f"{name} is already reported researched.")
            return
        if self.plan.add(name):
            self.refresh()
            self.details.setText(f"Added {name} to the local plan. No gameplay action sent.")
        else:
            self.details.setText("Already queued or queue limit reached.")

    def move_selected(self, offset: int) -> None:
        row = self.queue_list.currentRow()
        self.plan.move(row, offset)
        self.refresh()
        self.queue_list.setCurrentRow(row + offset)

    def remove_selected(self) -> None:
        self.plan.remove(self.queue_list.currentRow())
        self.refresh()
