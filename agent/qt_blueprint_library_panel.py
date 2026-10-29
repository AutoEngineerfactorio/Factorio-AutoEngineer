"""Factorio-style local blueprint/book navigator: folders, nested books, actions.

Never claims to synchronize with Factorio's cloud blueprint library.
"""
from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

from blueprint_encoder import encode_document
from blueprint_library_store import DEFAULT_ROOT, BlueprintLibraryStore

qtw = import_module("PySide6.QtWidgets")
qtc = import_module("PySide6.QtCore")
Qt = qtc.Qt
Signal = qtc.Signal


def nested_document(document: dict[str, Any],
                    path: tuple[int, ...]) -> dict[str, Any]:
    current = document
    for index in path:
        if "blueprint_book" not in current:
            raise ValueError("Selected entry is not in a book")
        entries = current["blueprint_book"].get("blueprints", [])
        entry = next((one for one in entries if one.get("index") == index), None)
        if entry is None:
            raise KeyError("Book entry was not found")
        key = "blueprint" if "blueprint" in entry else "blueprint_book"
        current = {key: entry[key]}
    return current


class BlueprintLibraryPanel(qtw.QWidget):
    """Persist and browse standalone prints and nested book entries."""

    openDocument = Signal(object)

    def __init__(self, parent=None, *, root: Path = DEFAULT_ROOT):
        super().__init__(parent)
        self.store = BlueprintLibraryStore(root)
        layout = qtw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.heading = qtw.QLabel(
            "MY BLUEPRINTS  •  Local library / books / imported designs  •  Not cloud synced")
        self.heading.setWordWrap(True)
        self.heading.setObjectName("muted")
        layout.addWidget(self.heading)

        toolbar = qtw.QHBoxLayout()
        self.new_book_button = qtw.QPushButton("New book")
        self.open_button = qtw.QPushButton("Open selected")
        self.copy_button = qtw.QPushButton("Copy selected")
        self.add_button = qtw.QPushButton("Add to book")
        self.remove_button = qtw.QPushButton("Remove book entry")
        self.rename_button = qtw.QPushButton("Rename")
        self.reload_button = qtw.QPushButton("Refresh")
        for button in (self.new_book_button, self.open_button, self.copy_button,
                       self.add_button, self.remove_button, self.rename_button,
                       self.reload_button):
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.search = qtw.QLineEdit()
        self.search.setPlaceholderText("Filter folders, prints, and books")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        self.tree = qtw.QTreeWidget()
        self.tree.setObjectName("localBlueprintLibrary")
        self.tree.setHeaderLabels(["Print / book", "Kind", "Contents"])
        self.tree.setColumnWidth(0, 355)
        self.tree.setColumnWidth(1, 105)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_selected())
        layout.addWidget(self.tree, 1)
        self.status = qtw.QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.new_book_button.clicked.connect(self.create_book_dialog)
        self.open_button.clicked.connect(self.open_selected)
        self.copy_button.clicked.connect(self.copy_selected)
        self.add_button.clicked.connect(self.add_selected_to_book)
        self.remove_button.clicked.connect(self.remove_selected_entry)
        self.rename_button.clicked.connect(self.rename_selected)
        self.reload_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        self.tree.clear()
        groups: dict[str, Any] = {}
        filter_text = self.search.text().casefold()
        for item in self.store.list_items():
            if filter_text and filter_text not in (
                    item["label"] + " " + item["folder"]).casefold():
                continue
            folder = item["folder"]
            if folder not in groups:
                group = qtw.QTreeWidgetItem([folder, "Folder", ""])
                groups[folder] = group
                self.tree.addTopLevelItem(group)
            count = item.get("entity_count") or item.get("book_count") or 0
            entry = qtw.QTreeWidgetItem(
                [item["label"], "Book" if item["kind"] == "blueprint_book" else "Blueprint",
                 str(count) + (" entries" if item["kind"] == "blueprint_book" else " entities")])
            entry.setData(0, Qt.UserRole, (item["id"], ()))
            groups[folder].addChild(entry)
            if item["kind"] == "blueprint_book":
                try:
                    document = self.store.get(item["id"])
                    self._book_children(entry, document, item["id"], (), 0)
                except (ValueError, OSError):
                    entry.addChild(qtw.QTreeWidgetItem(["Unreadable book", "Error", ""]))
        self.tree.expandToDepth(1)
        self.status.setText(
            f"{len(self.store.entries)} stored prints/books • Stored locally in {self.store.root}")

    def _book_children(self, parent, document, identifier, path, depth):
        if depth >= 8 or "blueprint_book" not in document:
            return
        for entry in document["blueprint_book"]["blueprints"][:512]:
            key = "blueprint" if "blueprint" in entry else "blueprint_book"
            source = entry[key]
            label = str(source.get("label") or
                        ("Nested book" if key == "blueprint_book" else "Unnamed print"))
            subpath = path + (entry["index"],)
            item = qtw.QTreeWidgetItem([
                f"{entry['index']}. {label}",
                "Book" if key == "blueprint_book" else "Blueprint",
                str(len(source.get("blueprints" if key == "blueprint_book" else "entities", []))),
            ])
            item.setData(0, Qt.UserRole, (identifier, subpath))
            parent.addChild(item)
            if key == "blueprint_book":
                self._book_children(item, {key: source}, identifier, subpath, depth + 1)

    def selection(self) -> tuple[str, tuple[int, ...]] | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        value = item.data(0, Qt.UserRole)
        if (not isinstance(value, tuple) or len(value) != 2
                or not isinstance(value[0], str)
                or not isinstance(value[1], tuple)):
            return None
        return value

    def selected_document(self) -> dict[str, Any] | None:
        selected = self.selection()
        if selected is None:
            return None
        identifier, path = selected
        return nested_document(self.store.get(identifier), path)

    def open_selected(self) -> None:
        try:
            document = self.selected_document()
            if document is None:
                self.status.setText("Select a print, book, or an entry inside a book.")
            else:
                self.openDocument.emit(document)
                self.status.setText("Opened selected print/book in Preview & Export.")
        except (ValueError, KeyError, OSError) as exc:
            self.status.setText("Open failed: " + str(exc)[:150])

    def copy_selected(self) -> None:
        doc = self.selected_document()
        if doc is not None:
            qtw.QApplication.clipboard().setText(encode_document(doc))
            self.status.setText("Validated blueprint exchange copied to clipboard.")

    def store_document(self, document: dict[str, Any], *,
                       folder: str = "My Blueprints") -> str:
        identifier = self.store.save(document, folder=folder)
        self.refresh()
        self.status.setText("Saved validated blueprint/book to the local library.")
        return identifier

    def create_book(self, label: str) -> str:
        identifier = self.store.create_book(label)
        self.refresh()
        return identifier

    def create_book_dialog(self) -> None:
        label, okay = qtw.QInputDialog.getText(self, "New blueprint book", "Book name:")
        if okay and label.strip():
            try:
                self.create_book(label)
            except ValueError as exc:
                self.status.setText(str(exc))

    def add_selected_to_book(self) -> None:
        selected = self.selection()
        if selected is None:
            return
        source_id, path = selected
        if path:
            self.status.setText(
                "Select a top-level stored print/book before adding to another book.")
            return
        books = [(item["label"], item["id"]) for item in self.store.list_items()
                 if item["kind"] == "blueprint_book" and item["id"] != source_id]
        if not books:
            self.status.setText("Create a destination book first.")
            return
        labels = [f"{label} [{identifier[:8]}]" for label, identifier in books]
        chosen, okay = qtw.QInputDialog.getItem(
            self, "Add blueprint to book", "Destination", labels, 0, False)
        if okay and chosen in labels:
            target_id = books[labels.index(chosen)][1]
            try:
                self.store.add_to_book(target_id, source_id)
                self.refresh()
                self.status.setText("Added print/book to the selected book.")
            except (ValueError, KeyError) as exc:
                self.status.setText("Cannot add: " + str(exc))

    def remove_selected_entry(self) -> None:
        selected = self.selection()
        if selected is None:
            return
        identifier, path = selected
        if len(path) != 1:
            self.status.setText("Select a direct entry inside a book to remove it.")
            return
        confirmed = qtw.QMessageBox.question(
            self, "Remove book entry", "Remove this entry from its book? "
            "The independently stored source blueprint remains saved.")
        if confirmed == qtw.QMessageBox.Yes:
            if self.store.remove_book_item(identifier, path[0]):
                self.refresh()

    def rename_selected(self) -> None:
        selected = self.selection()
        if selected is None or selected[1]:
            self.status.setText("Select a top-level saved blueprint/book to rename.")
            return
        identifier = selected[0]
        existing = self.store.entries[identifier]["label"]
        title, okay = qtw.QInputDialog.getText(
            self, "Rename print/book", "New name:", text=existing)
        if okay and title.strip():
            try:
                self.store.rename(identifier, title)
                self.refresh()
            except ValueError as exc:
                self.status.setText(str(exc))
