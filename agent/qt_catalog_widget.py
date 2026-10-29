"""Qt widget for the observed recipe and research catalog.

This widget is presentation-only. It consumes the immutable shared snapshot
from :mod:`qt_catalog`, so the Qt dashboard and the AI Helper consume the
same observed rows, research names and completeness state.

Large catalogs are rendered through a bounded model and a search field. The
search runs over the complete observed catalog, while the table itself is
capped to keep the UI responsive.

The widget never fetches anything itself. It **asks** for the catalog:

* :attr:`CatalogWidget.refreshRequested` is emitted when the user wants the
  authoritative catalog re-read from the game.
* :attr:`CatalogWidget.loadMoreRequested` is emitted when the user wants the
  next page of the catalog added.

The shell owns the transport and performs the request on its worker thread,
so the interface never waits for the game and never issues two requests for
the same page.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

from qt_catalog import CatalogSnapshot, catalog_snapshot, catalog_status_text
from qt_catalog_pages import CatalogAssembly, CatalogPager, page_from_frame

qt_core = import_module("PySide6.QtCore")
qt_widgets = import_module("PySide6.QtWidgets")

QAbstractItemView = qt_widgets.QAbstractItemView
QHBoxLayout = qt_widgets.QHBoxLayout
QHeaderView = qt_widgets.QHeaderView
QLabel = qt_widgets.QLabel
QLineEdit = qt_widgets.QLineEdit
QPushButton = qt_widgets.QPushButton
QSignalBlocker = qt_core.QSignalBlocker
QSplitter = qt_widgets.QSplitter
QTableWidget = qt_widgets.QTableWidget
QTableWidgetItem = qt_widgets.QTableWidgetItem
QVBoxLayout = qt_widgets.QVBoxLayout
QWidget = qt_widgets.QWidget

Signal = qt_core.Signal

#: The maximum number of recipe rows rendered at once.
MAX_VISIBLE_ROWS = 500

#: The maximum number of machine rows rendered at once.
MAX_VISIBLE_MACHINES = 500

#: The maximum number of researched-technology rows rendered at once.
MAX_VISIBLE_RESEARCH = 500

#: The columns rendered for each recipe.
COLUMNS = (
    "Recipe",
    "Availability",
    "Category",
    "Crafting time",
    "Ingredients",
    "Products",
)

#: The columns rendered for each observed machine prototype.
MACHINE_COLUMNS = ("Machine", "Crafting speed", "Energy usage", "Fluid boxes")

#: The columns rendered for each researched technology.
RESEARCH_COLUMNS = ("Researched technology",)

#: The availability text of a recipe the game reported as enabled.
AVAILABILITY_ENABLED = "Enabled"

#: The availability text of a recipe the game reported as disabled.
AVAILABILITY_DISABLED = "Disabled"

#: The availability text of a recipe the game reported as hidden.
AVAILABILITY_HIDDEN = "Hidden"


def _text(value: Any, limit: int = 1000) -> str:
    """Return bounded display text."""
    if value is None:
        return "—"
    if isinstance(value, (dict, list, tuple)):
        import json

        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)[:limit]


def _part_text(part: Mapping[str, Any]) -> str:
    """Return the display text of one observed ingredient or product."""
    kind = str(part.get("type") or "item")
    name = str(part.get("name") or "—")
    amount = part.get("amount")
    if amount is None:
        return f"{kind}:{name}"
    return f"{kind}:{name} x{amount}"


def _parts_text(parts: Any) -> str:
    """Return the display text of an observed ingredient or product list."""
    if not isinstance(parts, (list, tuple)):
        return "—"
    rendered = [
        _part_text(part) for part in parts if isinstance(part, Mapping)
    ]
    return ", ".join(rendered) if rendered else "—"


def _recipe_search_text(recipe: Mapping[str, Any]) -> str:
    """Return the searchable text of one observed recipe row."""
    parts = [recipe.get("name"), recipe.get("category")]
    parts.extend(recipe.get("categories") or ())
    for key in ("ingredients", "products"):
        value = recipe.get(key)
        if isinstance(value, (list, tuple)):
            for part in value:
                if isinstance(part, Mapping):
                    parts.extend((part.get("type"), part.get("name")))
    return " ".join(str(part) for part in parts if part is not None).casefold()


def _availability(recipe: Mapping[str, Any]) -> str:
    """Return the observed availability state of one recipe.

    The game reports ``enabled`` and ``hidden`` separately. A recipe that
    was never observed keeps the unknown state; it is never presented as
    enabled by default.
    """
    hidden = recipe.get("hidden")
    enabled = recipe.get("enabled")
    if hidden is True:
        return AVAILABILITY_HIDDEN
    if enabled is False:
        return AVAILABILITY_DISABLED
    if enabled is True:
        return AVAILABILITY_ENABLED
    return "Unknown"


def _recipe_row(recipe: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the display row of one observed recipe."""
    return (
        str(recipe.get("name") or "—"),
        _availability(recipe),
        str(recipe.get("category") or "—"),
        str(recipe.get("crafting_time") or "—"),
        _parts_text(recipe.get("ingredients")),
        _parts_text(recipe.get("products")),
    )


def _fluid_boxes_text(machine: Mapping[str, Any]) -> str:
    """Return the display text of a machine's observed fluid boxes."""
    boxes = machine.get("fluid_boxes")
    if not isinstance(boxes, (list, tuple)):
        return "—"
    rendered = []
    for box in boxes:
        if not isinstance(box, Mapping):
            continue
        kind = str(box.get("production_type") or "—")
        fluid = str(box.get("filter") or "any")
        rendered.append(f"{kind}:{fluid}")
    return ", ".join(rendered) if rendered else "—"


def _machine_row(machine: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the display row of one observed machine prototype."""
    return (
        str(machine.get("name") or "—"),
        str(machine.get("crafting_speed") or "—"),
        str(machine.get("energy_usage") or "—"),
        _fluid_boxes_text(machine),
    )


class CatalogWidget(QWidget):
    """Render one shared observed catalog snapshot."""

    #: Emitted when the user wants the authoritative catalog re-read.
    refreshRequested = Signal()

    #: Emitted when the user wants the next catalog page added.
    loadMoreRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._snapshot: CatalogSnapshot | None = None
        self._filtered_recipes: tuple[Mapping[str, Any], ...] = ()
        self._assembly: CatalogAssembly | None = None
        self._pager: CatalogPager | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.status = QLabel("Catalog not observed")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip(
            "Re-read the authoritative catalog from the running game")
        self.refresh_button.clicked.connect(self.refreshRequested)
        controls.addWidget(self.refresh_button)

        self.load_more_button = QPushButton("Load more")
        self.load_more_button.setToolTip(
            "Request the next page of the observed catalog")
        self.load_more_button.clicked.connect(self.loadMoreRequested)
        self.load_more_button.setEnabled(False)
        controls.addWidget(self.load_more_button)

        self.counts = QLabel("")
        self.counts.setObjectName("muted")
        controls.addWidget(self.counts)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search observed recipes, categories, ingredients or products")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh_recipes)
        layout.addWidget(self.search)

        splitter = QSplitter()
        self.recipe_table = QTableWidget(0, len(COLUMNS))
        self.recipe_table.setHorizontalHeaderLabels(COLUMNS)
        self.recipe_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.recipe_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.recipe_table.setAlternatingRowColors(True)
        self.recipe_table.verticalHeader().setVisible(False)
        self.recipe_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.recipe_table.horizontalHeader().setStretchLastSection(True)

        self.machine_table = QTableWidget(0, len(MACHINE_COLUMNS))
        self.machine_table.setHorizontalHeaderLabels(MACHINE_COLUMNS)
        self.machine_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.machine_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.machine_table.setAlternatingRowColors(True)
        self.machine_table.verticalHeader().setVisible(False)
        self.machine_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.machine_table.horizontalHeader().setStretchLastSection(True)

        self.research_table = QTableWidget(0, len(RESEARCH_COLUMNS))
        self.research_table.setHorizontalHeaderLabels(RESEARCH_COLUMNS)
        self.research_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.research_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.research_table.setAlternatingRowColors(True)
        self.research_table.verticalHeader().setVisible(False)
        self.research_table.horizontalHeader().setStretchLastSection(True)

        splitter.addWidget(self.recipe_table)
        splitter.addWidget(self.machine_table)
        splitter.addWidget(self.research_table)
        layout.addWidget(splitter, 1)

    # -- reading ---------------------------------------------------------

    @property
    def snapshot(self) -> CatalogSnapshot | None:
        """Return the current immutable snapshot."""
        return self._snapshot

    @property
    def assembly(self) -> CatalogAssembly | None:
        """Return the current multi-page assembly, when there is one."""
        return self._assembly

    @property
    def pager(self) -> CatalogPager | None:
        """Return the pager that owns the page cache."""
        return self._pager

    def set_pager(self, pager: CatalogPager | None) -> None:
        """Give the widget the pager that owns the page cache."""
        self._pager = pager

    def more_pages_available(self) -> bool:
        """Whether another catalog page may still be requested.

        The answer is only true when the game itself reported more pages
        than have been loaded. The widget never asks for a page the game
        said does not exist.
        """
        snapshot = self._snapshot
        if snapshot is None:
            return False
        total_pages = snapshot.total_pages
        if total_pages is None or total_pages <= 0:
            return False
        return self._loaded_pages() < total_pages

    def _loaded_pages(self) -> int:
        """Return how many catalog pages are currently loaded."""
        if self._assembly is not None:
            return len(self._assembly.pages_loaded)
        snapshot = self._snapshot
        if snapshot is None or snapshot.page is None:
            return 0
        return max(0, snapshot.page)

    # -- writing ---------------------------------------------------------

    def set_frame(self, frame: Mapping[str, Any] | None, *, state: str = "observed",
                  detail: str = "Observed catalog") -> None:
        """Show one observed catalog frame."""
        self.set_snapshot(catalog_snapshot(frame, state=state, detail=detail))

    def set_snapshot(self, snapshot: CatalogSnapshot) -> None:
        """Show one immutable catalog snapshot."""
        previous = self._snapshot
        self._snapshot = snapshot
        self._refresh_recipes()
        if previous is None or previous.machines != snapshot.machines:
            self._fill_machines(snapshot.machines)
        if previous is None or previous.research != snapshot.research:
            self._fill_research(snapshot.research)

    def set_assembly(self, assembly: CatalogAssembly) -> None:
        """Show the result of one multi-page assembly."""
        self._assembly = assembly
        self.set_snapshot(assembly.snapshot)

    def apply_page(self, frame: Mapping[str, Any] | None) -> CatalogSnapshot:
        """Show one observed catalog page as a single-page snapshot.

        The page is also remembered in the pager, so a later assembly reuses
        it instead of requesting it again.
        """
        page = page_from_frame(frame)
        pager = self._pager
        if pager is None:
            pager = CatalogPager(page_size=page.page_size or 16)
            self._pager = pager
        if page.page == 1:
            pager.clear()
        if frame is not None:
            pager.remember_page(page)
        if isinstance(frame, Mapping) and page.status == "ok":
            assembly = pager.assemble(pages=page.page)
            self.set_assembly(assembly)
            return assembly.snapshot
        snapshot = catalog_snapshot(frame)
        self.set_snapshot(snapshot)
        return snapshot

    # -- rendering -------------------------------------------------------

    def _update_counts(self) -> None:
        """Show the real recipe, research and machine counts.

        A count that was never observed is left out entirely. An unknown
        count is never rendered as a zero, because a zero would claim the
        catalog is empty.
        """
        snapshot = self._snapshot
        if snapshot is None or not snapshot.known:
            self.counts.setText("")
            return
        total_recipes = snapshot.total_count
        if total_recipes is None and self._assembly is not None:
            total_recipes = self._assembly.counts().get("total_recipes")
        pages = snapshot.total_pages
        loaded = self._loaded_pages()
        parts = [
            f"{len(snapshot.recipes)} recipes",
            f"{len(snapshot.research)} researched",
            f"{len(snapshot.machines)} machines",
        ]
        if total_recipes is not None:
            parts.append(f"{total_recipes} recipes reported")
        if pages is not None:
            parts.append(f"page {loaded} of {pages}")
        self.counts.setText(" · ".join(parts))

    def _refresh_recipes(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            self._filtered_recipes = ()
            self.recipe_table.setRowCount(0)
            self._update_counts()
            self.load_more_button.setEnabled(False)
            return
        query = self.search.text().strip().casefold()
        if query:
            rows = tuple(
                recipe for recipe in snapshot.recipes if query in _recipe_search_text(recipe)
            )
        else:
            rows = snapshot.recipes
        self._filtered_recipes = rows
        visible = rows[:MAX_VISIBLE_ROWS]
        if visible != getattr(self, "_rendered_recipes", None):
            blocker = QSignalBlocker(self.recipe_table)
            self.recipe_table.setRowCount(len(visible))
            for row_index, recipe in enumerate(visible):
                for column, value in enumerate(_recipe_row(recipe)):
                    self.recipe_table.setItem(row_index, column, QTableWidgetItem(value))
            self._rendered_recipes = visible
            del blocker
        self._update_counts()
        self.load_more_button.setEnabled(self.more_pages_available())
        if len(rows) > MAX_VISIBLE_ROWS:
            self.status.setText(
                f"{catalog_status_text(snapshot)}; showing {MAX_VISIBLE_ROWS} "
                f"of {len(rows)} matching recipes"
            )
        else:
            self.status.setText(catalog_status_text(snapshot))

    def _fill_machines(self, machines: tuple[Mapping[str, Any], ...]) -> None:
        visible = machines[:MAX_VISIBLE_MACHINES]
        self.machine_table.setRowCount(len(visible))
        for row_index, machine in enumerate(visible):
            for column, value in enumerate(_machine_row(machine)):
                self.machine_table.setItem(
                    row_index, column, QTableWidgetItem(value))

    def _fill_research(self, research: tuple[str, ...]) -> None:
        visible = research[:MAX_VISIBLE_RESEARCH]
        self.research_table.setRowCount(len(visible))
        for row_index, name in enumerate(visible):
            self.research_table.setItem(
                row_index, 0, QTableWidgetItem(str(name)))


__all__ = [
    "AVAILABILITY_DISABLED",
    "AVAILABILITY_ENABLED",
    "AVAILABILITY_HIDDEN",
    "COLUMNS",
    "MACHINE_COLUMNS",
    "MAX_VISIBLE_MACHINES",
    "MAX_VISIBLE_RESEARCH",
    "MAX_VISIBLE_ROWS",
    "RESEARCH_COLUMNS",
    "CatalogWidget",
]
