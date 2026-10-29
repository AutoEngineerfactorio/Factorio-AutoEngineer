"""Factorio-style blueprint workshop with persistent local books and grounded drafts.

Three-pane UI: local library/book tree, visual plan canvas, observed-catalog
custom drafting. Nothing calls RCON or writes to a running game. The generator
explicitly requires a complete, fingerprinted R10-A observed catalog.
"""
from __future__ import annotations

import re
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping

from blueprint_encoder import encode_document
from blueprint_generation import GenerationError, generate_production_blueprint
from blueprint_library import BlueprintLibrary
from qt_blueprint_studio import BlueprintStudio
from qt_catalog import CatalogSnapshot

qtw = import_module("PySide6.QtWidgets")
qtc = import_module("PySide6.QtCore")
Qt = qtc.Qt
QWidget = qtw.QWidget

LIBRARY_HOME = Path(__file__).resolve().parents[1] / ".local" / "blueprint-library"
MAX_BOOK_VIEW_ENTRIES = 500


def _button(label, callback, *, hint=""):
    button = qtw.QPushButton(label)
    button.setObjectName("tool")
    if hint:
        button.setToolTip(hint)
    button.clicked.connect(callback)
    return button


class BlueprintWorkspace(QWidget):
    """Persistent library, nested books and observed-recipe blueprint drafting."""

    def __init__(self, parent=None, *, library_home: Path | None = None):
        super().__init__(parent)
        self.library = BlueprintLibrary(library_home or LIBRARY_HOME)
        self.catalog: CatalogSnapshot | None = None
        self.recipes: dict[str, Mapping[str, Any]] = {}
        self.machines: dict[str, Mapping[str, Any]] = {}
        self.active_uid: str | None = None
        self._tree_loading = False
        self._init_ui()
        self.refresh_library()

    def _init_ui(self):
        root = qtw.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        heading = qtw.QHBoxLayout()
        title = qtw.QLabel("BLUEPRINT STUDIO")
        title.setStyleSheet("font-size:17pt;font-weight:800;color:#f6b34c")
        heading.addWidget(title)
        heading.addStretch()
        self.mode_label = qtw.QLabel("LOCAL LIBRARY  ·  NO GAMEPLAY WRITES")
        self.mode_label.setObjectName("muted")
        heading.addWidget(self.mode_label)
        root.addLayout(heading)

        summary = qtw.QLabel(
            "Organize blueprints and nested books • inspect layouts • "
            "create machine-array drafts using verified recipes")
        summary.setObjectName("muted")
        root.addWidget(summary)

        panes = qtw.QSplitter(Qt.Horizontal)
        root.addWidget(panes, 1)

        # Persistent library navigator.
        lib = qtw.QWidget()
        lib_layout = qtw.QVBoxLayout(lib)
        lib_layout.setContentsMargins(5, 4, 5, 4)
        lib_layout.setSpacing(7)
        section = qtw.QLabel("MY BLUEPRINT LIBRARY")
        section.setStyleSheet("font-weight:700;color:#e7edf3")
        lib_layout.addWidget(section)
        self.search = qtw.QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Find blueprints and books...")
        self.search.textChanged.connect(self.refresh_library)
        lib_layout.addWidget(self.search)
        self.tree = qtw.QTreeWidget()
        self.tree.setObjectName("blueprintLibraryTree")
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        lib_layout.addWidget(self.tree, 1)
        lib_tools = qtw.QGridLayout()
        for column, name, callback in (
            (0, "+ Folder", self.new_folder),
            (1, "+ Book", self.new_book),
            (2, "Import", self.import_file),
            (3, "Save current", self.save_current),
            (4, "Rename", self.rename_selected),
            (5, "Delete", self.delete_selected),
            (6, "Add to book", self.add_to_book),
            (7, "Move", self.move_selected),
            (8, "Entry up", lambda: self.edit_selected_entry("up")),
            (9, "Entry down", lambda: self.edit_selected_entry("down")),
        ):
            lib_tools.addWidget(_button(name, callback), column // 2, column % 2)
        lib_layout.addLayout(lib_tools)
        self.library_count = qtw.QLabel("Library loading...")
        self.library_count.setObjectName("muted")
        lib_layout.addWidget(self.library_count)
        panes.addWidget(lib)

        # Visual layout / entity inspector. Use the proven codec widget as
        # one embedded canvas but expose its controls in a compact toolbar.
        center = qtw.QWidget()
        center_layout = qtw.QVBoxLayout(center)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(6)
        row = qtw.QHBoxLayout()
        row.addWidget(qtw.QLabel("LAYOUT CANVAS"))
        row.addStretch()
        row.addWidget(_button("Paste & inspect", self.paste_current))
        row.addWidget(_button("Fit", self.fit_canvas))
        row.addWidget(_button("−", lambda: self.zoom(0.8)))
        row.addWidget(_button("+", lambda: self.zoom(1.25)))
        center_layout.addLayout(row)
        self.studio = BlueprintStudio()
        # In the three-pane workspace this component is the canvas only.
        # Its standalone Library/Creator tabs remain accessible when launched
        # separately, but must not create nested libraries in this view.
        self.studio.tabs.setCurrentWidget(self.studio.inspector)
        self.studio.tabs.tabBar().hide()
        self.studio.library_save_button.hide()
        self.studio.notice.hide()
        self.studio.input.hide()
        for button in (self.studio.paste_button, self.studio.open_button,
                       self.studio.inspect_button, self.studio.copy_button,
                       self.studio.save_button, self.studio.clear_button):
            button.hide()
        self.studio.preview.setRenderHint(
            import_module("PySide6.QtGui").QPainter.Antialiasing, True)
        center_layout.addWidget(self.studio, 1)
        export_row = qtw.QHBoxLayout()
        export_row.addWidget(_button("Copy blueprint string", self.studio.copy_exchange))
        export_row.addWidget(_button("Export .txt", self.studio.save_file))
        export_row.addWidget(_button("Clear preview", self.clear_preview))
        export_row.addStretch()
        center_layout.addLayout(export_row)
        panes.addWidget(center)

        # Generation workbench (uses actual catalog facts; no invented machines).
        panel = qtw.QWidget()
        controls = qtw.QVBoxLayout(panel)
        controls.setContentsMargins(8, 4, 5, 4)
        controls.setSpacing(9)
        section = qtw.QLabel("AI HELPER  /  CREATE")
        section.setStyleSheet("font-weight:800;color:#f6b34c")
        controls.addWidget(section)
        self.planner_status = qtw.QLabel(
            "No full observed recipe catalog loaded. Connect to Factorio "
            "and use Recipes & Research → Refresh / Load More.")
        self.planner_status.setWordWrap(True)
        self.planner_status.setObjectName("muted")
        controls.addWidget(self.planner_status)
        controls.addWidget(qtw.QLabel("Factory request"))
        self.prompt = qtw.QPlainTextEdit()
        self.prompt.setMaximumHeight(70)
        self.prompt.setPlaceholderText(
            "Example: Build 180 iron-gear-wheel per minute")
        controls.addWidget(self.prompt)
        controls.addWidget(qtw.QLabel("Observed recipe"))
        self.recipe_choice = qtw.QComboBox()
        self.recipe_choice.setEditable(True)
        self.recipe_choice.setInsertPolicy(qtw.QComboBox.NoInsert)
        self.recipe_choice.currentTextChanged.connect(self._recipe_changed)
        controls.addWidget(self.recipe_choice)
        controls.addWidget(qtw.QLabel("Target product"))
        self.product_choice = qtw.QComboBox()
        controls.addWidget(self.product_choice)
        controls.addWidget(qtw.QLabel("Compatible observed machine"))
        self.machine_choice = qtw.QComboBox()
        controls.addWidget(self.machine_choice)
        controls.addWidget(qtw.QLabel("Target items or fluid / minute"))
        self.rate = qtw.QDoubleSpinBox()
        self.rate.setRange(0.001, 1_000_000)
        self.rate.setDecimals(2)
        self.rate.setValue(180)
        controls.addWidget(self.rate)
        controls.addWidget(qtw.QLabel("Machines per row"))
        self.columns = qtw.QSpinBox()
        self.columns.setRange(1, 25)
        self.columns.setValue(6)
        controls.addWidget(self.columns)
        self.generate_button = _button(
            "Generate custom blueprint draft", self.generate)
        controls.addWidget(self.generate_button)
        self.plan = qtw.QPlainTextEdit()
        self.plan.setReadOnly(True)
        self.plan.setPlaceholderText(
            "Generated machine counts, ingredient demand and limitations.")
        controls.addWidget(self.plan, 1)
        warning = qtw.QLabel(
            "Generated machine arrays are drafts. Connections, fluid ports, "
            "power, belts and throughput still require construction validation.")
        warning.setWordWrap(True)
        warning.setObjectName("muted")
        controls.addWidget(warning)
        panes.addWidget(panel)
        panes.setSizes([290, 680, 355])

        self.message = qtw.QLabel(
            "Select a saved blueprint or import one. Library persists locally.")
        self.message.setObjectName("muted")
        self.message.setWordWrap(True)
        root.addWidget(self.message)

    def _message(self, message: str):
        self.message.setText(message)

    def refresh_library(self):
        if self._tree_loading:
            return
        self._tree_loading = True
        try:
            search = self.search.text().casefold().strip()
            self.tree.clear()

            def add(parent_item, parent, depth=0):
                if depth > 20:
                    return
                for record in self.library.children(parent):
                    if search and record["kind"] != "folder" and search not in record["name"].casefold():
                        continue
                    kind = record["kind"]
                    prefix = {"folder": "▸ ", "blueprint": "▦ ",
                              "blueprint_book": "▣ "}[kind]
                    item = qtw.QTreeWidgetItem([prefix + record["name"]])
                    item.setData(0, Qt.UserRole, ("library", record["id"]))
                    if parent_item is None:
                        self.tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    if kind == "folder":
                        add(item, record["id"], depth + 1)
                    if kind == "blueprint_book":
                        try:
                            self._append_book_entries(
                                item, self.library.document(record["id"]),
                                depth, owner=record["id"])
                        except (ValueError, OSError):
                            pass

            add(None, None)
            self.tree.expandToDepth(1)
            self.library_count.setText(
                f"{len(self.library.records)} saved items  ·  local only")
        finally:
            self._tree_loading = False

    def _append_book_entries(self, parent, doc, depth=0, *,
                             owner: str, path: tuple[int, ...] = ()):
        if depth > 9 or "blueprint_book" not in doc:
            return
        entries = doc["blueprint_book"].get("blueprints", [])
        for position, entry in enumerate(entries[:MAX_BOOK_VIEW_ENTRIES]):
            key = "blueprint" if "blueprint" in entry else "blueprint_book"
            one = {key: entry[key]}
            label = entry[key].get("label") or f"Entry {entry['index']}"
            item = qtw.QTreeWidgetItem([f"  {('▦' if key == 'blueprint' else '▣')} {label}"])
            location = path + (position,)
            item.setData(0, Qt.UserRole,
                         ("book-entry", {"document": one, "owner": owner,
                                         "path": location}))
            parent.addChild(item)
            if key == "blueprint_book":
                self._append_book_entries(
                    item, one, depth + 1, owner=owner, path=location)

    def _selected(self):
        items = self.tree.selectedItems()
        return items[0].data(0, Qt.UserRole) if items else None

    def _selected_parent(self) -> str | None:
        selected = self._selected()
        if selected and selected[0] == "library":
            row = self.library.records.get(selected[1])
            if row:
                return row["id"] if row["kind"] == "folder" else row.get("parent")
        return None

    def _selection_changed(self):
        if self._tree_loading:
            return
        selected = self._selected()
        if selected is None:
            return
        try:
            if selected[0] == "book-entry":
                doc = selected[1]["document"]
                self.active_uid = None
            else:
                record = self.library.records[selected[1]]
                if record["kind"] == "folder":
                    return
                doc = self.library.document(selected[1])
                self.active_uid = selected[1]
            self.studio.input.setPlainText(encode_document(doc))
            self.studio.load_exchange(self.studio.input.toPlainText())
            self._message("Opened validated library document; no game state changed.")
        except (OSError, ValueError, KeyError) as exc:
            self._message(f"Library item unavailable: {exc}")

    def new_folder(self):
        name, ok = qtw.QInputDialog.getText(self, "New folder", "Folder name:")
        if ok:
            try:
                self.library.add_folder(name, self._selected_parent())
                self.refresh_library()
                self._message(f"Created local folder: {name}")
            except (OSError, ValueError) as exc:
                self._message(str(exc))

    def new_book(self):
        name, ok = qtw.QInputDialog.getText(self, "New blueprint book", "Book name:")
        if ok:
            try:
                self.library.new_book(name, self._selected_parent())
                self.refresh_library()
                self._message(f"Created editable local book: {name}")
            except (OSError, ValueError) as exc:
                self._message(str(exc))

    def import_file(self):
        name, _ = qtw.QFileDialog.getOpenFileName(
            self, "Import blueprint or book", "", "Exchange strings (*.txt);;All files (*)")
        if not name:
            return
        if self.studio.load_path(Path(name)):
            self.save_current()
        else:
            self._message(self.studio.status.text())

    def paste_current(self):
        self.studio.paste_from_clipboard()
        self._message(self.studio.status.text())

    def save_current(self):
        doc = self.studio.document
        if doc is None:
            self._message("Import or generate a validated blueprint first.")
            return
        payload = doc.get("blueprint", doc.get("blueprint_book", {}))
        suggested = str(payload.get("label") or "Untitled Blueprint")
        name, ok = qtw.QInputDialog.getText(
            self, "Save to blueprint library", "Name:", text=suggested)
        if ok:
            try:
                uid = self.library.add_document(name, doc, self._selected_parent())
                self.active_uid = uid
                self.refresh_library()
                self._message(f"Saved '{name}' in the local library.")
            except (OSError, ValueError) as exc:
                self._message(str(exc))

    def rename_selected(self):
        selected = self._selected()
        if selected and selected[0] == "book-entry":
            name, ok = qtw.QInputDialog.getText(
                self, "Rename book entry", "New entry label:")
            if ok:
                self.edit_selected_entry("rename", label=name)
            return
        if not selected or selected[0] != "library":
            self._message("Select a saved library item to rename.")
            return
        row = self.library.records[selected[1]]
        name, ok = qtw.QInputDialog.getText(
            self, "Rename library item", "New name:", text=row["name"])
        if ok:
            try:
                self.library.rename(row["id"], name)
                self.refresh_library()
                self._message("Library item renamed.")
            except (OSError, ValueError) as exc:
                self._message(str(exc))

    def delete_selected(self):
        selected = self._selected()
        if selected and selected[0] == "book-entry":
            answer = qtw.QMessageBox.question(
                self, "Remove book entry",
                "Remove this entry from its saved book? The source blueprint remains in the library.",
                qtw.QMessageBox.Yes | qtw.QMessageBox.No, qtw.QMessageBox.No)
            if answer == qtw.QMessageBox.Yes:
                self.edit_selected_entry("remove")
            return
        if not selected or selected[0] != "library":
            return
        name = self.library.records[selected[1]]["name"]
        answer = qtw.QMessageBox.question(
            self, "Delete local library entry",
            f"Delete '{name}' from the local library? This cannot be undone.",
            qtw.QMessageBox.Yes | qtw.QMessageBox.No, qtw.QMessageBox.No)
        if answer == qtw.QMessageBox.Yes:
            try:
                self.library.delete(selected[1])
                self.refresh_library()
                self._message(f"Deleted local entry '{name}'.")
            except (OSError, ValueError) as exc:
                self._message(str(exc))

    def edit_selected_entry(self, operation: str, *, label: str = ""):
        selected = self._selected()
        if not selected or selected[0] != "book-entry":
            self._message("Select a blueprint entry inside a saved book.")
            return
        info = selected[1]
        try:
            self.library.edit_book_entry(
                info["owner"], tuple(info["path"]), operation, label=label)
            self.refresh_library()
            self._message(f"Saved book entry {operation} in the local library.")
        except (OSError, ValueError) as exc:
            self._message(str(exc))

    def move_selected(self):
        selected = self._selected()
        if not selected or selected[0] != "library":
            self._message("Select a saved item before moving.")
            return
        folders = [("(Library root)", None)]
        folders += [(r["name"], r["id"]) for r in self.library.records.values()
                    if r["kind"] == "folder"]
        name, ok = qtw.QInputDialog.getItem(
            self, "Move library item", "Destination folder:",
            [x[0] for x in folders], 0, False)
        if ok:
            try:
                dest = next(v for label, v in folders if label == name)
                self.library.move(selected[1], dest)
                self.refresh_library()
                self._message("Item moved to selected folder.")
            except (OSError, ValueError) as exc:
                self._message(str(exc))

    def add_to_book(self):
        doc = self.studio.document
        if doc is None:
            self._message("Select or generate a blueprint to add.")
            return
        books = [(r["name"], r["id"]) for r in self.library.records.values()
                 if r["kind"] == "blueprint_book"]
        if not books:
            self._message("Create a blueprint book first.")
            return
        name, ok = qtw.QInputDialog.getItem(
            self, "Add to book", "Destination book:",
            [label for label, _ in books], 0, False)
        if ok:
            try:
                uid = next(uid for label, uid in books if label == name)
                self.library.append_to_book(uid, doc)
                self.refresh_library()
                self._message(f"Added the current validated document to '{name}'.")
            except (OSError, ValueError) as exc:
                self._message(str(exc))

    def clear_preview(self):
        self.active_uid = None
        self.studio.clear()
        self._message("Preview cleared; saved library items were not changed.")

    def fit_canvas(self):
        self.studio.preview.fitInView(
            self.studio.scene.sceneRect(), Qt.KeepAspectRatio)

    def zoom(self, factor: float):
        self.studio.preview.scale(factor, factor)

    def set_observed_catalog(self, snapshot: CatalogSnapshot | None):
        """Use the same authoritative catalog currently shown in Recipes & Research."""
        self.catalog = snapshot
        self.recipes = {}
        self.machines = {}
        self.recipe_choice.clear()
        if snapshot is None or not snapshot.known or not snapshot.source_fingerprint:
            self.planner_status.setText(
                "Observed catalog required: open Recipes, then Refresh. "
                "Unknown recipes and missing machine categories cannot be generated.")
            self.machine_choice.clear()
            self.product_choice.clear()
            return
        self.recipes = {str(row["name"]): row for row in snapshot.recipes
                        if isinstance(row.get("name"), str)
                        and row.get("enabled") is True and row.get("hidden") is not True}
        self.machines = {str(row["name"]): row for row in snapshot.machines
                         if isinstance(row.get("name"), str)}
        self.recipe_choice.addItems(sorted(self.recipes))
        self.planner_status.setText(
            ("COMPLETE catalog" if snapshot.complete else
             "PARTIAL catalog - only loaded verified recipes can be used")
            + f": {len(self.recipes):,} enabled recipes; "
            f"{len(self.machines):,} machine prototypes • {snapshot.game_version or 'game'} "
            f"• fingerprint {snapshot.source_fingerprint[:18]}")
        self._recipe_changed(self.recipe_choice.currentText())

    def _recipe_changed(self, name: str):
        recipe = self.recipes.get(name)
        self.product_choice.clear()
        self.machine_choice.clear()
        if recipe is None:
            return
        products = recipe.get("products")
        if isinstance(products, list):
            self.product_choice.addItems(
                sorted({str(p["name"]) for p in products
                        if isinstance(p, Mapping) and isinstance(p.get("name"), str)}))
        category = recipe.get("category")
        for machine in sorted(self.machines.values(), key=lambda m: str(m.get("name"))):
            cats = machine.get("crafting_categories", machine.get("categories"))
            if isinstance(cats, Mapping):
                cats = [key for key, val in cats.items() if val]
            if isinstance(cats, (list, tuple)) and category in cats:
                self.machine_choice.addItem(str(machine["name"]))
        if self.machine_choice.count() == 0:
            self.planner_status.setText(
                f"No verified machine category for '{name}'. "
                "Cannot generate a machine arrangement from guessed compatibility.")

    def generate(self) -> bool:
        """Ground a natural factory request against actual observed mechanics."""
        if (self.catalog is None or not self.catalog.known or not self.catalog.complete
                or not self.catalog.source_fingerprint):
            self._message("Load a complete authoritative observed catalog page in Recipes.")
            return False
        query = self.prompt.toPlainText().strip()
        match = re.search(r"\b(\d+(?:\.\d+)?)\b", query)
        if query and match:
            amount = float(match.group(1))
            if 0 < amount <= 1_000_000:
                self.rate.setValue(amount)
        if query:
            lowered = query.casefold()
            matched = [name for name in self.recipes
                       if name.casefold() in lowered]
            if matched:
                self.recipe_choice.setCurrentText(max(matched, key=len))
        recipe = self.recipes.get(self.recipe_choice.currentText())
        machine = self.machines.get(self.machine_choice.currentText())
        if recipe is None or machine is None:
            self._message("Select a verified recipe and compatible observed machine.")
            return False
        try:
            draft = generate_production_blueprint(
                recipe, machine, self.product_choice.currentText(),
                self.rate.value(), source_fingerprint=self.catalog.source_fingerprint,
                grid_columns=self.columns.value())
            self.studio.input.setPlainText(draft.exchange())
            if not self.studio.load_exchange(draft.exchange()):
                raise GenerationError(self.studio.status.text())
            self.plan.setPlainText(
                f"DRAFT: {draft.recipe}\nMachine: {draft.machine}\n"
                f"Machines: {draft.machine_count}\n"
                f"Target: {draft.target_per_minute:g} per minute\n"
                f"Theoretical output: {draft.expected_per_minute:g} per minute\n\n"
                "THEORETICAL INPUTS PER MINUTE\n" +
                "\n".join(f"• {n}: {q:g}" for n, q in draft.inputs_per_minute) +
                "\n\nNOT YET VERIFIED\n" + "\n".join(
                    f"• {note}" for note in draft.notes))
            self._message(
                f"Generated {draft.machine_count} observed machines. "
                "Use Save current to retain the draft in your local library.")
            return True
        except (GenerationError, ValueError) as exc:
            self.plan.setPlainText(f"Cannot generate: {exc}")
            self._message(str(exc))
            return False
