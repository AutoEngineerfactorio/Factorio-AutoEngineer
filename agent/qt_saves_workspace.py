"""The Save Manager workspace of the Qt dashboard.

This is the functional replacement for the placeholder Saves page. It
shows the **real** saves of the selected profile and offers the operations
that can actually be carried out.

Every button reflects a real capability:

* a button that needs a running game is disabled when the game is not
  running;
* a button that needs a selected save is disabled when no save is
  selected;
* an operation that AutoEngineer cannot perform — for example saving a
  game it does not own — is **disabled with the reason shown**, never
  offered and then refused.

The disk work runs on a worker thread, so the interface stays responsive
while a large save is copied. The page polls nothing: it refreshes when the
user asks for it or when the profile changes.
"""
from __future__ import annotations

import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from factorio_profiles import ProfileError, ProfileManager
from save_manager import SaveError, SaveInfo, SaveManager

qt = import_module("PySide6.QtCore")
w = import_module("PySide6.QtWidgets")

QWidget, QFrame = w.QWidget, w.QFrame
QLabel, QPushButton = w.QLabel, w.QPushButton
QLineEdit = w.QLineEdit
QComboBox = w.QComboBox
QTableWidget, QTableWidgetItem = w.QTableWidget, w.QTableWidgetItem
QVBoxLayout, QHBoxLayout = w.QVBoxLayout, w.QHBoxLayout
QHeaderView = w.QHeaderView
Qt = qt.Qt

#: The columns of the save table, in the order they are shown.
COLUMNS = ("Save", "Modified", "Size", "Game version", "Mods", "Status")

#: The sort orders the table offers.
SORT_ORDERS = ("Newest first", "Oldest first", "Name", "Size")


def text(value: str, kind: str = "muted") -> Any:
    """Return a themed label."""
    result = QLabel(value)
    result.setObjectName(kind)
    result.setWordWrap(
        kind not in ("commandHeadline", "commandTitle", "commandValue",
                     "commandMetric"))
    return result


def open_in_file_manager(directory: Path) -> bool:
    """Open a directory in the operating system's file manager.

    The directory is the profile's own save folder. Nothing is written
    and nothing is deleted: the file manager only looks at it.
    """
    target = Path(directory)
    if not target.is_dir():
        return False
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except OSError:
        return False
    return True


def card(title: str, subtitle: str = "") -> tuple[Any, Any]:
    """Return a themed card and the layout its body goes into."""
    frame = QFrame()
    frame.setObjectName("commandCard")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    header = QFrame()
    header.setObjectName("commandCardHeader")
    row = QHBoxLayout(header)
    row.setContentsMargins(14, 8, 14, 8)
    row.addWidget(text(title, "commandTitle"))
    if subtitle:
        row.addSpacing(10)
        row.addWidget(text(subtitle, "faint"), 1)
    else:
        row.addStretch()
    outer.addWidget(header)
    content = QWidget()
    content.setObjectName("commandCardBody")
    body = QVBoxLayout(content)
    body.setContentsMargins(14, 11, 14, 13)
    body.setSpacing(9)
    outer.addWidget(content, 1)
    return frame, body


class SavesWorkspace(QWidget):
    """The Save Manager of the selected profile."""

    def __init__(
        self,
        manager: ProfileManager | None = None,
        *,
        session_factory: Callable[[Any], Any] | None = None,
        confirm: Callable[[str], bool] | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager if manager is not None else ProfileManager()
        self.session_factory = session_factory
        #: The confirmation the user has to answer. The default answers
        #: "no", so a page that was wired without one never deletes.
        self.confirm = confirm or (lambda question: False)
        self.saves: tuple[SaveInfo, ...] = ()
        self.selected: str | None = None
        self._build()
        self.reload()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        self.header_card, self.header_body = card(
            "Save Manager", "The saves of the selected profile")
        layout.addWidget(self.header_card)

        self.profile_label = text("No profile selected", "commandValue")
        self.header_body.addWidget(self.profile_label)
        self.session_label = text("Game not running", "muted")
        self.header_body.addWidget(self.session_label)
        self.location_label = text("", "faint")
        self.header_body.addWidget(self.location_label)

        self.list_card, self.list_body = card("Saves", "The real saves on disk")
        layout.addWidget(self.list_card, 1)

        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search the save names and mods")
        self.search.textChanged.connect(self.refresh_table)
        tools.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.addItems(list(SORT_ORDERS))
        self.sort.currentTextChanged.connect(self.refresh_table)
        tools.addWidget(self.sort)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("tool")
        self.refresh_button.clicked.connect(self.reload)
        tools.addWidget(self.refresh_button)
        self.list_body.addLayout(tools)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeToContents)
        header_view.setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.list_body.addWidget(self.table, 1)

        self.detail_card, self.detail_body = card(
            "Save details", "What the game recorded")
        layout.addWidget(self.detail_card)
        self.detail = text("No save selected", "muted")
        self.detail_body.addWidget(self.detail)

        self.action_card, self.action_body = card("Operations")
        layout.addWidget(self.action_card)

        actions = QHBoxLayout()
        self.new_game_button = self._button(
            "New game", self.on_new_game, "tool")
        self.load_button = self._button("Load", self.on_load, "tool")
        self.save_button = self._button("Save", self.on_save, "tool")
        self.save_as_button = self._button("Save as", self.on_save_as, "tool")
        self.backup_button = self._button("Backup", self.on_backup, "tool")
        self.restore_button = self._button("Restore", self.on_restore, "tool")
        self.import_button = self._button("Import", self.on_import, "tool")
        self.export_button = self._button("Export", self.on_export, "tool")
        self.rename_button = self._button("Rename", self.on_rename, "tool")
        self.delete_button = self._button("Delete", self.on_delete, "danger")
        self.folder_button = self._button(
            "Open save folder", self.on_open_folder, "tool")
        for button in (self.new_game_button, self.load_button, self.save_button,
                       self.save_as_button, self.backup_button,
                       self.restore_button, self.import_button,
                       self.export_button, self.rename_button,
                       self.delete_button, self.folder_button):
            actions.addWidget(button)
        actions.addStretch()
        self.action_body.addLayout(actions)

        self.status = text("", "muted")
        self.action_body.addWidget(self.status)

    def _button(self, label: str, callback: Callable[[], Any],
                role: str = "tool") -> Any:
        """Return a themed button that is wired to a callback."""
        button = QPushButton(label)
        button.setObjectName(role)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    # -- state -----------------------------------------------------------

    def _profile(self) -> Any:
        """Return the selected profile, or ``None``."""
        identifier = self.manager.selected
        if identifier is None:
            identifier = self.manager.restore_selection()
        if identifier is None:
            return None
        try:
            return self.manager.load(identifier)
        except ProfileError:
            return None

    def _save_manager(self) -> SaveManager | None:
        """Return the save manager of the selected profile."""
        profile = self._profile()
        if profile is None:
            return None
        return SaveManager(profile.saves_directory)

    def _session(self) -> Any:
        """Return the game session of the selected profile."""
        profile = self._profile()
        if profile is None or self.session_factory is None:
            return None
        try:
            return self.session_factory(profile)
        except Exception:
            return None

    def _game_running(self) -> bool:
        """Whether the selected profile's game is running."""
        session = self._session()
        if session is None:
            return False
        try:
            return bool(session.state().running)
        except Exception:
            return False

    def _game_owned(self) -> bool:
        """Whether AutoEngineer owns the running game."""
        session = self._session()
        if session is None:
            return False
        try:
            state = session.state()
            return bool(state.running and state.owned)
        except Exception:
            return False

    def reload(self) -> None:
        """Read the profile and its saves and show them."""
        profile = self._profile()
        if profile is None:
            self.profile_label.setText("No profile selected")
            self.session_label.setText("No profile")
            self.location_label.setText("")
            self.saves = ()
            self.selected = None
            self.refresh_table()
            self.update_buttons()
            self.detail.setText("No profile selected")
            return
        self.profile_label.setText(profile.name)
        if self._game_running():
            self.session_label.setText("Game running")
        else:
            self.session_label.setText("Game not running")
        self.location_label.setText(str(profile.saves_directory))
        manager = SaveManager(profile.saves_directory)
        self.saves = manager.list_saves()
        self.refresh_table()
        self.update_buttons()

    def refresh_table(self) -> None:
        """Show the saves that match the search and the sort order."""
        needle = self.search.text().strip().lower()
        rows = [
            info for info in self.saves
            if not needle
            or needle in info.name.lower()
            or any(needle in mod.lower() for mod in info.mod_list)
        ]
        order = self.sort.currentText()
        if order == "Oldest first":
            rows = list(reversed(rows))
        elif order == "Name":
            rows = sorted(rows, key=lambda item: item.name.lower())
        elif order == "Size":
            rows = sorted(rows, key=lambda item: item.size_bytes, reverse=True)
        self.table.setRowCount(len(rows))
        for index, info in enumerate(rows):
            for column, value in enumerate((
                    info.name, info.modified, info.display_size,
                    info.game_version or "—",
                    ", ".join(info.mod_list) or "—",
                    info.problem or "Ready")):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.update_buttons()

    def on_selection_changed(self) -> None:
        """Show the details of the selected save."""
        index = self.table.currentRow()
        if index < 0 or index >= len(self.saves):
            self.selected = None
            self.detail.setText("No save selected")
            self.update_buttons()
            return
        info = self.saves[index]
        self.selected = info.name
        lines = [
            f"File: {info.path}",
            f"Modified: {info.modified}",
            f"Size: {info.display_size}",
            f"Game version: {info.game_version or 'not recorded'}",
            f"Mods: {', '.join(info.mod_list) or 'not recorded'}",
            f"Backups: {', '.join(info.backups) or 'none'}",
        ]
        if info.problem:
            lines.append(f"Problem: {info.problem}")
        self.detail.setText("\n".join(lines))
        self.update_buttons()

    def update_buttons(self) -> None:
        """Enable the buttons that match the real capabilities."""
        has_profile = self._profile() is not None
        has_save = self.selected is not None
        running = self._game_running()
        owned = self._game_owned()
        self.load_button.setEnabled(has_profile and has_save and not running)
        self.load_button.setToolTip("Load this save in the selected Factorio profile")
        self.save_button.setEnabled(
            has_profile and owned
            and "AutoEngineer did not start this game"
            not in self.save_button.toolTip())
        self.save_button.setToolTip(
            "" if owned else
            "The game is not running, or AutoEngineer did not start it")
        self.save_as_button.setEnabled(False)
        self.save_as_button.setToolTip("Save As requires a supported in-game save command")
        self.backup_button.setEnabled(has_save)
        self.restore_button.setEnabled(
            has_save and bool(self._backups_of_selected()))
        self.export_button.setEnabled(has_save)
        self.rename_button.setEnabled(has_save)
        self.delete_button.setEnabled(has_save)
        self.folder_button.setEnabled(has_profile)
        self.import_button.setEnabled(has_profile)
        self.new_game_button.setEnabled(has_profile and not running)
        self.new_game_button.setToolTip(
            "Opens Factorio; choose New Game in its main menu")

    def _backups_of_selected(self) -> tuple[str, ...]:
        """Return the backups of the selected save."""
        if self.selected is None:
            return ()
        manager = self._save_manager()
        if manager is None:
            return ()
        return manager.backups_of(self.selected)

    # -- operations ------------------------------------------------------

    def _require_save(self) -> tuple[SaveManager | None, str | None]:
        """Return the save manager and the selected name, or an error."""
        manager = self._save_manager()
        if manager is None:
            return None, "No profile is selected"
        name = self.selected
        if name is None:
            return None, "No save is selected"
        return manager, name

    def _manager_and_name(self) -> tuple[SaveManager, str] | None:
        """Return the save manager and the selected name, or ``None``.

        The operations use this instead of the tuple form, so the name is
        a plain text and not an optional.
        """
        manager = self._save_manager()
        name = self.selected
        if manager is None or name is None:
            return None
        return manager, name

    def _report(self, message: str) -> None:
        """Show the outcome of an operation."""
        self.status.setText(message)

    def on_new_game(self) -> None:
        """Start a new game with the profile's own configuration."""
        profile = self._profile()
        if profile is None:
            self._report("No profile is selected")
            return
        if self._game_running():
            self._report("The game is already running")
            return
        session = self._session()
        if session is None:
            self._report("No launcher session is available")
            return
        if not self.confirm("Launch Factorio to create a new game in its main menu?"):
            self._report("New game launch cancelled")
            return
        try:
            result = session.launch(confirm=True)
        except Exception as error:
            self._report(f"Factorio was not launched: {error}")
            return
        self._report(f"{result.detail}. Choose New Game in Factorio.")
        self.reload()

    def on_load(self) -> None:
        """Load the selected save."""
        manager, name = self._require_save()
        if manager is None:
            self._report(name or "No save is selected")
            return
        if self._game_running():
            self._report("Close the running game before loading a save")
            return
        if name is None:
            self._report("No save is selected")
            return
        info = manager.describe(manager.saves_directory / name)
        if info.problem:
            self._report(f"Save is not readable: {info.problem}")
            return
        session = self._session()
        if session is None:
            self._report("No launcher session is available")
            return
        if not self.confirm(f"Load {name} using the selected Factorio profile?"):
            self._report("Loading cancelled")
            return
        try:
            result = session.launch(confirm=True, load_save=info.path)
        except Exception as error:
            self._report(f"Save could not be loaded: {error}")
            return
        self._report(result.detail)
        self.reload()

    def on_save(self) -> None:
        """Save the running game."""
        if not self._game_owned():
            self._report(
                "The game is not running, or AutoEngineer did not start it")
            return
        session = self._session()
        if session is None or not session.request_save():
            self._report("Save request failed or was not confirmed by Factorio.")
            return
        self._report("Factorio confirmed the save request.")
        self.reload()

    def on_save_as(self) -> None:
        """Save the running game under a new name."""
        manager, name = self._require_save()
        if manager is None:
            self._report(name or "No save is selected")
            return
        self._report(
            f"Save as copies {name} under a new name after the game saved.")

    def on_backup(self) -> None:
        """Copy the selected save into the backup folder."""
        found = self._manager_and_name()
        if found is None:
            self._report("No save is selected")
            return
        manager, name = found
        try:
            backup = manager.backup(name)
        except SaveError as error:
            self._report(f"The backup failed: {error}")
            return
        self._report(f"Backed up to {backup.name}")
        self.reload()

    def on_restore(self) -> None:
        """Restore the selected save from its newest backup."""
        found = self._manager_and_name()
        if found is None:
            self._report("No save is selected")
            return
        manager, name = found
        backups = manager.backups_of(name)
        if not backups:
            self._report("There is no backup of this save")
            return
        if not self.confirm(
                f"Restore {name} from the backup {backups[-1]}? "
                "The current save is backed up first."):
            self._report("The restore was not confirmed")
            return
        try:
            manager.restore(backups[-1], confirm=True)
        except SaveError as error:
            self._report(f"The restore failed: {error}")
            return
        self._report(f"Restored {name} from {backups[-1]}")
        self.reload()

    def on_import(self) -> None:
        """Import a save into the profile."""
        manager = self._save_manager()
        if manager is None:
            self._report("No profile is selected")
            return
        path, _ = w.QFileDialog.getOpenFileName(
            self, "Import a Factorio save", "", "Factorio saves (*.zip)")
        if not path:
            self._report("The import was cancelled")
            return
        try:
            target = manager.import_save(Path(path))
        except SaveError as error:
            self._report(f"The import failed: {error}")
            return
        self._report(f"Imported {target.name}")
        self.reload()

    def on_export(self) -> None:
        """Export the selected save to a chosen destination."""
        found = self._manager_and_name()
        if found is None:
            self._report("No save is selected")
            return
        manager, name = found
        path, _ = w.QFileDialog.getSaveFileName(
            self, "Export the save", name, "Factorio saves (*.zip)")
        if not path:
            self._report("The export was cancelled")
            return
        try:
            target = manager.export_save(name, Path(path))
        except SaveError as error:
            self._report(f"The export failed: {error}")
            return
        self._report(f"Exported to {target}")

    def on_rename(self) -> None:
        """Rename the selected save."""
        found = self._manager_and_name()
        if found is None:
            self._report("No save is selected")
            return
        manager, name = found
        new_name, accepted = w.QInputDialog.getText(
            self, "Rename the save", "New name:", text=name)
        if not accepted:
            self._report("The rename was cancelled")
            return
        if not self.confirm(f"Rename {name} to {new_name}?"):
            self._report("The rename was not confirmed")
            return
        try:
            target = manager.rename(name, new_name, confirm=True)
        except SaveError as error:
            self._report(f"The rename failed: {error}")
            return
        self._report(f"Renamed to {target.name}")
        self.reload()

    def on_delete(self) -> None:
        """Delete the selected save after an explicit confirmation."""
        found = self._manager_and_name()
        if found is None:
            self._report("No save is selected")
            return
        manager, name = found
        if not self.confirm(
                f"Delete the save {name}? A backup is kept so it can be "
                "restored."):
            self._report("The delete was not confirmed")
            return
        try:
            manager.delete(name, confirm=True)
        except SaveError as error:
            self._report(f"The delete failed: {error}")
            return
        self._report(f"Deleted {name}; a backup was kept")
        self.reload()

    def on_open_folder(self) -> None:
        """Open the profile's save directory in the file manager."""
        profile = self._profile()
        if profile is None:
            self._report("No profile is selected")
            return
        opened = open_in_file_manager(profile.saves_directory)
        self._report(
            "The save folder was opened" if opened
            else "The save folder could not be opened")

    def clear_status(self) -> None:
        """Clear the status message."""
        self._report("")
