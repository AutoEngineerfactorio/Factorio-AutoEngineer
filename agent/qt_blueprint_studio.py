"""R07-backed, offline-only Blueprint Studio for the universal Qt dashboard.

Imports verified Factorio exchange strings and books, previews a bounded
layout and entity table, and exports the same validated document. No RCON,
gameplay action, network request, research change or guessed blueprint.
"""
from __future__ import annotations

from collections import Counter
from importlib import import_module
from pathlib import Path

from blueprint_codec import MAX_ENCODED_CHARS, BlueprintError
from blueprint_document import decode, describe
from blueprint_encoder import encode_document
from qt_blueprint_designer import BlueprintDesigner
from qt_blueprint_library_panel import BlueprintLibraryPanel
from qt_theme import Palette

qtw = import_module("PySide6.QtWidgets")
qtc = import_module("PySide6.QtCore")
qtg = import_module("PySide6.QtGui")

QWidget = qtw.QWidget
Qt = qtc.Qt
MAX_PREVIEW_ENTITIES = 750
MAX_TABLE_ROWS = 500
MAX_IMPORT_FILE_BYTES = MAX_ENCODED_CHARS + 8


def _entities(document: dict):
    """Iterate verified blueprint/book entities in stored order."""
    stack = [("", document)]
    while stack:
        location, doc = stack.pop()
        if "blueprint" in doc:
            for entity in doc["blueprint"].get("entities", []):
                if isinstance(entity, dict):
                    yield location, entity
        else:
            entries = doc["blueprint_book"].get("blueprints", [])
            for entry in reversed(entries):
                key = "blueprint" if "blueprint" in entry else "blueprint_book"
                stack.append((f"{location}/{entry['index']}", {key: entry[key]}))


def _coordinates(entity: dict):
    position = entity.get("position")
    if not isinstance(position, dict):
        return None
    x, y = position.get("x"), position.get("y")
    if isinstance(x, (int, float)) and not isinstance(x, bool) and isinstance(y, (int, float)) and not isinstance(y, bool):
        if -1e7 <= x <= 1e7 and -1e7 <= y <= 1e7:
            return float(x), float(y)
    return None


class BlueprintStudio(QWidget):
    """Import, inspect, draw and faithfully export a *local* blueprint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document: dict | None = None
        self.export_text = ""
        self.last_error = ""
        root = qtw.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self.tabs = qtw.QTabWidget()
        self.tabs.setObjectName("blueprintStudioTabs")
        root.addWidget(self.tabs, 1)
        self.inspector = qtw.QWidget()
        layout = qtw.QVBoxLayout(self.inspector)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.notice = qtw.QLabel(
            "Offline Blueprint Studio • import, inspect and export only. "
            "Nothing is placed in the game.")
        self.notice.setObjectName("muted")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)

        self.input = qtw.QPlainTextEdit()
        self.input.setObjectName("blueprintExchangeInput")
        self.input.setPlaceholderText("Paste a Factorio 0... blueprint or blueprint-book exchange string here")
        self.input.setMaximumHeight(100)
        self.input.setLineWrapMode(qtw.QPlainTextEdit.NoWrap)
        layout.addWidget(self.input)

        actions = qtw.QHBoxLayout()
        self.paste_button = qtw.QPushButton("Paste")
        self.open_button = qtw.QPushButton("Open .txt")
        self.inspect_button = qtw.QPushButton("Inspect blueprint")
        self.copy_button = qtw.QPushButton("Copy exchange")
        self.save_button = qtw.QPushButton("Save .txt")
        self.clear_button = qtw.QPushButton("Clear")
        self.library_save_button = qtw.QPushButton("Save to Library")
        for button in (self.paste_button, self.open_button, self.inspect_button,
                       self.copy_button, self.save_button, self.library_save_button,
                       self.clear_button):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self.status = qtw.QLabel("No blueprint imported")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.summary = qtw.QLabel("Entity, tile and book counts appear after validation.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        splitter = qtw.QSplitter(Qt.Horizontal)
        self.scene = qtw.QGraphicsScene(self)
        self.preview = qtw.QGraphicsView(self.scene)
        self.preview.setObjectName("blueprintLayoutPreview")
        self.preview.setRenderHint(qtg.QPainter.Antialiasing, False)
        self.preview.setDragMode(qtw.QGraphicsView.ScrollHandDrag)
        self.preview.setBackgroundBrush(qtg.QBrush(qtg.QColor(Palette.CARD)))
        self.entities = qtw.QTableWidget(0, 5)
        self.entities.setObjectName("blueprintEntityTable")
        self.entities.setHorizontalHeaderLabels(
            ["Prototype", "X", "Y", "Direction", "Book path"])
        self.entities.setEditTriggers(qtw.QAbstractItemView.NoEditTriggers)
        self.entities.setSelectionBehavior(qtw.QAbstractItemView.SelectRows)
        self.entities.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.preview)
        splitter.addWidget(self.entities)
        splitter.setSizes([620, 520])
        layout.addWidget(splitter, 1)

        self.details = qtw.QLabel("Zoom with the mouse wheel; drag to pan the blueprint.")
        self.details.setObjectName("muted")
        layout.addWidget(self.details)

        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.library_save_button.setEnabled(False)
        self.paste_button.clicked.connect(self.paste_from_clipboard)
        self.open_button.clicked.connect(self.open_file)
        self.inspect_button.clicked.connect(self.inspect_input)
        self.copy_button.clicked.connect(self.copy_exchange)
        self.save_button.clicked.connect(self.save_file)
        self.clear_button.clicked.connect(self.clear)
        self.library_save_button.clicked.connect(self.save_to_library)

        self.library_panel = BlueprintLibraryPanel()
        self.designer = BlueprintDesigner()
        self.tabs.addTab(self.library_panel, "My Library & Books")
        self.tabs.addTab(self.designer, "Create Blueprint")
        self.tabs.addTab(self.inspector, "Preview & Export")
        self.library_panel.openDocument.connect(self.open_document)
        self.designer.generated.connect(self.show_generated)

    def set_catalog_snapshot(self, snapshot):
        """Pass the authoritative observed catalog into the creator."""
        self.designer.set_snapshot(snapshot)

    def open_document(self, document: dict):
        """Open one stored book entry in the verified local inspector."""
        self.load_exchange(encode_document(document))
        self.tabs.setCurrentWidget(self.inspector)

    def show_generated(self, result: dict):
        """Inspect the real generated exchange without claiming in-game construction."""
        self.load_exchange(result["exchange"])
        self.tabs.setCurrentWidget(self.inspector)
        self.status.setText(
            f"Generated {result['machine_count']} observed machines. "
            "VALID DRAFT only; power and material routing not verified.")

    def save_to_library(self):
        if self.document is None:
            return
        try:
            self.library_panel.store_document(self.document)
            self.status.setText("Saved to My Library (local). No game changes made.")
        except (OSError, ValueError) as exc:
            self.status.setText(f"Library save failed: {exc}")

    def clear(self):
        self.document = None
        self.export_text = ""
        self.last_error = ""
        self.input.clear()
        self.scene.clear()
        self.entities.setRowCount(0)
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.library_save_button.setEnabled(False)
        self.status.setText("No blueprint imported")
        self.summary.setText("Entity, tile and book counts appear after validation.")
        self.details.setText("Zoom with the mouse wheel; drag to pan the blueprint.")

    def paste_from_clipboard(self):
        self.input.setPlainText(qtw.QApplication.clipboard().text())
        self.inspect_input()

    def inspect_input(self):
        self.load_exchange(self.input.toPlainText().strip())

    def load_exchange(self, value: str) -> bool:
        """Accept only an R07-validated, round-trip-equivalent document."""
        self.document = None
        self.export_text = ""
        self.scene.clear()
        self.entities.setRowCount(0)
        self.copy_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.library_save_button.setEnabled(False)
        try:
            if len(value) > MAX_ENCODED_CHARS:
                raise BlueprintError("Blueprint exceeds the encoded length limit")
            document = decode(value)
            encoded = encode_document(document)
            if decode(encoded) != document:
                raise BlueprintError("Export round trip changed the blueprint")
            metadata = describe(document)
        except (BlueprintError, ValueError, TypeError, RecursionError) as exc:
            self.last_error = str(exc)[:250]
            self.status.setText("Import refused: " + self.last_error)
            self.summary.setText("No blueprint loaded. Previous preview cleared.")
            return False

        self.last_error = ""
        self.document = document
        self.export_text = encoded
        self.copy_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.library_save_button.setEnabled(True)
        rows = list(_entities(document))
        counts = Counter(str(e.get("name", "unknown")) for _, e in rows)
        examples = ", ".join(f"{name} ×{count}" for name, count in counts.most_common(7))
        metadata_counts = (
            f"{metadata['entity_count']} entities • {metadata['tile_count']} tiles"
            if metadata["kind"] == "blueprint"
            else f"{metadata['blueprint_count']} direct book entries • {len(rows)} entities across entries"
        )
        self.status.setText(
            f"VALIDATED • {metadata['kind']} • game version code {metadata['version']} "
            "• document-equivalent exchange export confirmed")
        self.summary.setText(f"{metadata_counts} • {examples}")
        self._populate(rows)
        return True

    def _populate(self, rows: list):
        scene = self.scene
        table = self.entities
        colors = {}
        shown = 0
        for book_path, entity in rows:
            if shown >= max(MAX_PREVIEW_ENTITIES, MAX_TABLE_ROWS):
                break
            xy = _coordinates(entity)
            if xy is None:
                continue
            name = str(entity.get("name", "unknown"))[:100]
            if name not in colors:
                hue = (len(colors) * 47 + 32) % 360
                colors[name] = qtg.QColor.fromHsv(hue, 135, 215)
            x, y = xy
            if shown < MAX_PREVIEW_ENTITIES:
                scene.addRect(x * 6, y * 6, 5.6, 5.6,
                              qtg.QPen(qtg.QColor(Palette.BORDER), 0.1),
                              qtg.QBrush(colors[name]))
            if shown < MAX_TABLE_ROWS:
                index = table.rowCount()
                table.insertRow(index)
                for column, value in enumerate(
                        (name, f"{x:g}", f"{y:g}",
                         str(entity.get("direction", 0)), book_path or "root")):
                    table.setItem(index, column, qtw.QTableWidgetItem(value))
            shown += 1
        if shown:
            bounds = scene.itemsBoundingRect()
            scene.setSceneRect(bounds.adjusted(-12, -12, 12, 12))
            self.preview.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)
        self.details.setText(
            f"Preview drawn: {min(shown, MAX_PREVIEW_ENTITIES)} / {len(rows)} entities "
            f"(hard cap {MAX_PREVIEW_ENTITIES}); table rows: {table.rowCount()} "
            f"(hard cap {MAX_TABLE_ROWS}). Layout uses stored entity coordinates.")

    def load_path(self, path: Path) -> bool:
        """Open a bounded local exchange-text file (no network/game access)."""
        try:
            path = Path(path)
            if path.stat().st_size > MAX_IMPORT_FILE_BYTES:
                raise BlueprintError("Blueprint text file is too large")
            content = path.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError, BlueprintError) as exc:
            self.status.setText(f"File could not be opened: {type(exc).__name__}: {exc}")
            return False
        self.input.setPlainText(content)
        return self.load_exchange(content)

    def open_file(self):
        name, _ = qtw.QFileDialog.getOpenFileName(
            self, "Open Factorio blueprint exchange string", "", "Text files (*.txt);;All files (*)")
        if name:
            self.load_path(Path(name))

    def copy_exchange(self):
        if self.document is not None and self.export_text:
            qtw.QApplication.clipboard().setText(self.export_text)
            self.status.setText("Validated exchange copied to clipboard (game unchanged).")

    def save_file(self):
        if self.document is None or not self.export_text:
            return
        name, _ = qtw.QFileDialog.getSaveFileName(
            self, "Export Factorio blueprint string", "blueprint.txt", "Text files (*.txt)")
        if name:
            try:
                Path(name).write_text(self.export_text + "\n", encoding="utf-8")
                self.status.setText("Validated exchange saved locally (game unchanged).")
            except OSError as exc:
                self.status.setText(f"Export failed: {type(exc).__name__}: {exc}")
