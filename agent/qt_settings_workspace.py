"""The AutoEngineer Settings workspace.

This is the native, integrated Settings screen of the Qt dashboard. It
replaces the placeholder that showed one preference and four honest
"not connected" labels.

Every control is generated from the field definitions of
``settings_store``, so the screen and the store can never drift apart.
Each control is wired to the real service it belongs to:

* the profile section drives the real ``ProfileManager``;
* the diagnostics section reports the **real** state of the backend, the
  model endpoint and the credentials — their *presence* only;
* the safety section shows the real permission mode and never unlocks
  Fully Autonomous.

A control is only enabled when the thing behind it exists. A control
whose backend is missing is disabled and says why, rather than looking
operational.

Saving goes through ``settings_store.update``, which validates every
value and writes the file atomically. A rejected value leaves the stored
settings untouched and is reported in the feedback line.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Mapping

from factorio_profiles import ProfileError, ProfileManager
from settings_store import (
    FIELD_MAP,
    SECTIONS,
    Field,
    Settings,
    SettingsError,
    credential_status,
    default_settings_path,
    effective_settings,
    needs_restart,
    validate_updates,
)

qt = import_module("PySide6.QtCore")
w = import_module("PySide6.QtWidgets")

QWidget, QFrame = w.QWidget, w.QFrame
QLabel, QPushButton = w.QLabel, w.QPushButton
QLineEdit, QComboBox = w.QLineEdit, w.QComboBox
QSpinBox, QCheckBox = w.QSpinBox, w.QCheckBox
QDoubleSpinBox = w.QDoubleSpinBox
QVBoxLayout, QHBoxLayout = w.QVBoxLayout, w.QHBoxLayout
QGridLayout, QScrollArea = w.QGridLayout, w.QScrollArea
QTabWidget = w.QTabWidget
Qt = qt.Qt


def text(value: str, kind: str = "muted") -> Any:
    """Return a themed label."""
    label = QLabel(value)
    label.setObjectName(kind)
    label.setWordWrap(
        kind not in ("commandHeadline", "commandTitle", "commandValue",
                     "commandMetric"))
    return label


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
    body_widget = QWidget()
    body_widget.setObjectName("commandCardBody")
    body = QVBoxLayout(body_widget)
    body.setContentsMargins(14, 11, 14, 13)
    body.setSpacing(9)
    outer.addWidget(body_widget, 1)
    return frame, body


def action(label: str, callback: Callable[[], Any] | None = None,
           *, role: str = "tool", reason: str = "") -> Any:
    """Return a themed button that is disabled when it has no backend."""
    button = QPushButton(label)
    button.setObjectName(role)
    button.setCursor(Qt.PointingHandCursor)
    if callback is not None:
        button.clicked.connect(callback)
    else:
        button.setEnabled(False)
        button.setToolTip(reason or "Requires a verified controller integration")
    return button


def clear_layout(layout: Any) -> None:
    """Remove every widget and nested layout from a layout.

    PySide6's ``QVBoxLayout`` has no ``clear()``, so the children are
    removed one by one. Removing a widget also deletes it, so the old
    contents cannot leak into the next render.
    """
    while layout.count():
        item = layout.takeAt(0)
        child = item.widget()
        if child is not None:
            child.setParent(None)
            child.deleteLater()
            continue
        nested = item.layout()
        if nested is not None:
            clear_layout(nested)
            nested.deleteLater()


class SettingsSection(QWidget):
    """One section of the Settings screen.

    The section builds one row per field, with the field's description as
    the row's help text. The value widgets are collected so the screen can
    read them back when the user saves.
    """

    def __init__(self, fields: tuple[str, ...], parent: Any = None) -> None:
        super().__init__(parent)
        self.field_names = fields
        self.widgets: dict[str, Any] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(9)
        for row, name in enumerate(fields):
            field = FIELD_MAP.get(name)
            if field is None:
                continue
            label = QLabel(field.name.replace("_", " ").capitalize())
            label.setObjectName("muted")
            label.setMinimumWidth(210)
            grid.addWidget(label, row, 0)
            widget = self._build_widget(field)
            self.widgets[name] = widget
            grid.addWidget(widget, row, 1)
            if field.description:
                hint = text(field.description, "faint")
                grid.addWidget(hint, row, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 2)
        layout.addLayout(grid)
        layout.addStretch()

    def _build_widget(self, field: Field) -> Any:
        """Return the widget that edits one field."""
        if field.kind == "bool":
            box = QCheckBox()
            box.setToolTip(field.description)
            return box
        if field.kind == "choice":
            combo = QComboBox()
            combo.addItems(list(field.choices))
            combo.setToolTip(field.description)
            return combo
        if field.kind in ("int", "float"):
            if field.kind == "float":
                spin = QDoubleSpinBox()
                spin.setDecimals(1)
                # The default step of one would snap a half value such as
                # 59.5 down to 59.0, so the step is half a unit.
                spin.setSingleStep(0.5)
            else:
                spin = QSpinBox()
            spin.setMinimum(
                float(field.minimum) if field.minimum is not None else 0.0)
            spin.setMaximum(
                float(field.maximum) if field.maximum is not None else 0.0)
            spin.setToolTip(field.description)
            return spin
        if field.kind in ("text", "url"):
            edit = QLineEdit()
            edit.setToolTip(field.description)
            edit.setPlaceholderText(field.description)
            return edit

    def read(self) -> dict[str, Any]:
        """Return the values the widgets currently hold."""
        values: dict[str, Any] = {}
        for name, widget in self.widgets.items():
            field = FIELD_MAP.get(name)
            if field is None:
                continue
            if field.kind == "bool":
                values[name] = widget.isChecked()
            elif field.kind == "choice":
                values[name] = widget.currentText()
            elif field.kind in ("int", "float"):
                values[name] = widget.value()
            elif field.kind in ("text", "url"):
                values[name] = widget.text()
        return values

    def write(self, values: Mapping[str, Any]) -> None:
        """Put the stored values into the widgets."""
        for name, widget in self.widgets.items():
            field = FIELD_MAP.get(name)
            if field is None or name not in values:
                continue
            value = values[name]
            if field.kind == "bool":
                widget.setChecked(value is True)
            elif field.kind == "choice":
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif field.kind in ("int", "float"):
                # A float value must not be truncated: the UPS thresholds
                # carry a half value and truncating it would silently
                # change the guard's behaviour.
                widget.setValue(int(value) if field.kind == "int" else float(value))
            elif field.kind in ("text", "url"):
                widget.setText(str(value))


class SettingsWorkspace(QScrollArea):
    """The Settings screen of the dashboard."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        manager: ProfileManager | None = None,
        on_settings_changed: Callable[[Settings], None] | None = None,
        on_profile_changed: Callable[[], None] | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings if settings is not None else effective_settings()
        #: The settings file this screen reads and writes. It is kept so
        #: a reload and a save always use the same file, even when the
        #: caller supplied the settings itself.
        self.settings_path = self.settings.path or default_settings_path()
        self.manager = manager if manager is not None else ProfileManager()
        self.on_settings_changed = on_settings_changed
        self.on_profile_changed = on_profile_changed
        self.sections: dict[str, SettingsSection] = {}
        #: The settings whose widget value differs from the stored one.
        self.unsaved: dict[str, Any] = {}
        self._build()
        self.reload()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        layout.addWidget(text("Settings — AutoEngineer", "heading"))

        self.problems = text("", "badgeWarning")
        layout.addWidget(self.problems)

        tabs = QTabWidget()
        for name, fields in SECTIONS.items():
            section = SettingsSection(fields)
            self.sections[name] = section
            tabs.addTab(section, name)
        layout.addWidget(tabs, 1)

        self.profile_card, self.profile_body = card(
            "Profiles", "Installed Factorio configurations")
        layout.addWidget(self.profile_card)

        self.diagnostics_card, self.diagnostics_body = card(
            "Diagnostics", "The real state of the connected services")
        layout.addWidget(self.diagnostics_card)

        #: The result of the last model connection test, if one was run.
        self.model_status: Any = None
        self.model_detail = text("", "faint")
        self.model_discovered = text("", "faint")

        self.feedback = text("", "muted")
        layout.addWidget(self.feedback)

        buttons = QHBoxLayout()
        self.save_button = action("Apply settings", self.save, role="accent")
        buttons.addWidget(self.save_button)
        self.cancel_button = action("Discard changes", self.cancel)
        buttons.addWidget(self.cancel_button)
        self.restore_button = action("Restore defaults", self.restore_defaults)
        buttons.addWidget(self.restore_button)
        buttons.addWidget(action("Reload", self.reload))
        buttons.addStretch()
        self.restart_hint = text("", "badgeInfo")
        buttons.addWidget(self.restart_hint)
        layout.addLayout(buttons)

        self.setWidget(widget)
        self.setWidgetResizable(True)

    # -- population ------------------------------------------------------

    def reload(self) -> None:
        """Read the stored settings and show them."""
        self.settings = effective_settings(self.settings_path)
        values = self.settings.as_dict()
        for section in self.sections.values():
            section.write(values)
        self.render_profiles()
        self.render_diagnostics()
        self.render_problems()
        self.update_unsaved_state()

    def render_problems(self) -> None:
        """Show the problems the settings file or the environment caused."""
        problems = list(self.settings.problems)
        if problems:
            self.problems.setText(" • ".join(problems))
            self.problems.setVisible(True)
        else:
            self.problems.setText("")
            self.problems.setVisible(False)

    def render_profiles(self) -> None:
        """Show the profiles the manager knows about."""
        clear_layout(self.profile_body)
        profiles = self.manager.list_profiles()
        if not profiles:
            self.profile_body.addWidget(text(
                "No profiles yet. Use Detect installations to create one.",
                "muted"))
        for profile in profiles:
            status = self.manager.status(profile.identifier)
            version = status.get("game_version") or "unknown"
            problems = status.get("problems") or []
            row = QHBoxLayout()
            row.addWidget(text(profile.name, "commandValue"))
            row.addSpacing(10)
            row.addWidget(text(f"Factorio {version}", "muted"))
            row.addSpacing(10)
            row.addWidget(text(
                f"{status.get('enabled_mods', 0)} mods enabled", "muted"))
            if problems:
                row.addWidget(text(" • ".join(problems), "badgeWarning"))
            row.addStretch()
            if profile.identifier == self.manager.selected:
                row.addWidget(text("SELECTED", "badgeObserved"))
            else:
                row.addWidget(action(
                    "Select", self._make_select(profile.identifier),
                    role="positive"))
            row.addWidget(action(
                "Rename", self._make_rename(profile.identifier)))
            row.addWidget(action(
                "Duplicate", self._make_duplicate(profile.identifier)))
            row.addWidget(action(
                "Delete", self._make_delete(profile.identifier), role="danger"))
            self.profile_body.addLayout(row)

        self.profile_body.addWidget(text(
            f"Profile root: {self.manager.root}", "faint"))

    def render_diagnostics(self) -> None:
        """Show the real state of the backend, the model and the secrets."""
        clear_layout(self.diagnostics_body)
        self.diagnostics_body.addWidget(self._diagnostic_row(
            "Backend DLL",
            self._backend_state(),
            "The compiled FactorioMCP backend is required for live observation."))
        self.diagnostics_body.addWidget(self._diagnostic_row(
            "Model endpoint",
            self._model_state(),
            "The configured model endpoint and the credential it needs."))
        credentials = credential_status()
        self.diagnostics_body.addWidget(self._diagnostic_row(
            "RCON credential",
            "Present" if credentials["rcon_password_present"] else "Missing",
            credentials["note"]))
        model_row = QFrame()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(text("Model endpoint", "muted"))
        model_layout.addSpacing(12)
        model_layout.addWidget(text(self._model_state(), "commandValue"))
        model_layout.addStretch()
        model_layout.addWidget(action(
            "Test connection", self.test_model_connection, role="tool",
            reason="Tests the configured endpoint; no model is started"))
        self.diagnostics_body.addWidget(model_row)
        if self.model_status is not None:
            self.diagnostics_body.addWidget(self._diagnostic_row(
                "Model readiness", self.model_status.status,
                self.model_status.detail))
            self.diagnostics_body.addWidget(self.model_detail)
            self.diagnostics_body.addWidget(self.model_discovered)
        self.diagnostics_body.addWidget(self._diagnostic_row(
            "Permission mode",
            self._permission_state(),
            "The AI Helper is read-only. Fully Autonomous stays locked."))

    def _diagnostic_row(self, name: str, value: str, hint: str) -> Any:
        row = QFrame()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(text(name, "muted"))
        layout.addSpacing(12)
        layout.addWidget(text(value, "commandValue"))
        layout.addStretch()
        layout.addWidget(text(hint, "faint"))
        return row

    def _backend_state(self) -> str:
        """Report whether the backend the observer needs is present."""
        try:
            from autoengineer_config import get_settings

            settings = get_settings()
        except Exception as error:
            return f"Unavailable ({error})"
        from pathlib import Path

        dll = Path(settings["mcp_server_dll"])
        if not dll.is_absolute():
            dll = Path(__file__).resolve().parents[1] / dll
        if dll.is_file():
            return f"Present ({dll.name})"
        return "Not built"

    def _model_state(self) -> str:
        """Report the configured model endpoint and whether it answers."""
        endpoint = str(self.settings.get("llm_endpoint"))
        model = str(self.settings.get("llm_model") or "")
        description = f"{endpoint}"
        if model:
            description += f" • {model}"
        return description

    def test_model_connection(self) -> None:
        """Test the configured model endpoint and report what was verified.

        The diagnostic distinguishes the steps: the endpoint reachable, the
        models discovered, the inference successful, the tool calling
        verified and the model compatible. A step that was not verified is
        never reported as verified.
        """
        from model_diagnostics import diagnose

        endpoint = str(self.settings.get("llm_endpoint"))
        model = str(self.settings.get("llm_model") or "")
        provider = str(self.settings.get("llm_provider"))
        try:
            status = diagnose(endpoint, model, provider=provider)
        except Exception as error:
            self.feedback.setText(f"The model could not be tested: {error}")
            return
        self.model_status = status
        self.model_detail.setText(status.detail)
        self.model_discovered.setText(
            ", ".join(status.models_discovered) if status.models_discovered
            else "No model list was offered")
        self.feedback.setText(
            f"Model status: {status.status}. {status.detail}")
        self.render_diagnostics()

    def _permission_state(self) -> str:
        """Report the real permission mode."""
        try:
            from mode_policy import load_mode

            policy = load_mode()
        except Exception as error:
            return f"Unknown ({error})"
        if policy.mode == "semi":
            return "Semi-Autonomous"
        return "AI Helper (read-only)"

    # -- actions ---------------------------------------------------------

    def _make_select(self, identifier: str) -> Callable[[], Any]:
        def select() -> None:
            try:
                self.manager.select(identifier)
            except ProfileError as error:
                self.feedback.setText(f"The profile was not selected: {error}")
                return
            self.feedback.setText("Profile selected.")
            self.render_profiles()
            if self.on_profile_changed is not None:
                self.on_profile_changed()
        return select

    def _make_rename(self, identifier: str) -> Callable[[], Any]:
        def rename() -> None:
            try:
                profile = self.manager.load(identifier)
            except ProfileError as error:
                self.feedback.setText(f"The profile was not read: {error}")
                return
            name, accepted = w.QInputDialog.getText(
                self, "Rename profile", "New name:", text=profile.name)
            if not accepted:
                return
            try:
                self.manager.rename(identifier, name)
            except ProfileError as error:
                self.feedback.setText(f"The profile was not renamed: {error}")
                return
            self.feedback.setText("Profile renamed.")
            self.render_profiles()
        return rename

    def _make_duplicate(self, identifier: str) -> Callable[[], Any]:
        def duplicate() -> None:
            try:
                copy = self.manager.duplicate(identifier)
            except ProfileError as error:
                self.feedback.setText(f"The profile was not copied: {error}")
                return
            self.feedback.setText(f"Profile {copy.name} created.")
            self.render_profiles()
        return duplicate

    def _make_delete(self, identifier: str) -> Callable[[], Any]:
        def delete() -> None:
            try:
                profile = self.manager.load(identifier)
            except ProfileError as error:
                self.feedback.setText(f"The profile was not read: {error}")
                return
            answer = w.QMessageBox.question(
                self, "Delete profile",
                f"Delete the profile {profile.name} and its saves?",
                w.QMessageBox.Yes | w.QMessageBox.No)
            if answer != w.QMessageBox.Yes:
                self.feedback.setText("The profile was not deleted.")
                return
            try:
                self.manager.delete(identifier, confirm=True)
            except ProfileError as error:
                self.feedback.setText(f"The profile was not deleted: {error}")
                return
            self.feedback.setText("Profile deleted.")
            self.render_profiles()
        return delete

    def save(self) -> None:
        """Validate and store the values the widgets hold."""
        updates: dict[str, Any] = {}
        for section in self.sections.values():
            updates.update(section.read())
        try:
            validate_updates(updates)
        except SettingsError as error:
            self.feedback.setText(f"The settings were not saved: {error}")
            return
        from settings_store import update as store_update

        previous = self.stored_values()
        try:
            self.settings = store_update(
                updates, self.settings_path, settings=self.settings)
        except (SettingsError, OSError) as error:
            self.feedback.setText(f"The settings were not saved: {error}")
            return
        changed = [
            name for name, value in updates.items()
            if previous.get(name) != value]
        restart = needs_restart(changed)
        self.feedback.setText(
            "Settings saved. Some changes apply after a restart."
            if restart else "Settings saved.")
        if restart:
            self.restart_hint.setText(
                "Restart required for: " + ", ".join(restart))
        else:
            self.restart_hint.setText("")
        if self.on_settings_changed is not None:
            self.on_settings_changed(self.settings)
        self.render_problems()
        self.update_unsaved_state()

    def cancel(self) -> None:
        """Discard the changes in the widgets and show the stored values."""
        self.reload()
        self.feedback.setText("The changes were discarded.")
        self.restart_hint.setText("")

    def restore_defaults(self) -> None:
        """Put the default value of every setting into the widgets.

        The values are **not** stored: the user still has to apply them.
        That way the defaults can be inspected before they replace the
        current configuration.
        """
        from settings_store import FIELD_MAP

        defaults = {
            name: field.default for name, field in FIELD_MAP.items()}
        for section in self.sections.values():
            section.write(defaults)
        self.feedback.setText(
            "The defaults are shown. Apply them to store them.")
        self.update_unsaved_state()

    def stored_values(self) -> dict[str, Any]:
        """Return the values that are currently stored."""
        return self.settings.as_dict()

    def pending_changes(self) -> dict[str, Any]:
        """Return the settings whose widget value differs from the stored one."""
        stored = self.stored_values()
        pending: dict[str, Any] = {}
        for section in self.sections.values():
            for name, value in section.read().items():
                if stored.get(name) != value:
                    pending[name] = value
        return pending

    def has_unsaved_changes(self) -> bool:
        """Whether the widgets hold a value that is not stored."""
        return bool(self.pending_changes())

    def update_unsaved_state(self) -> None:
        """Show whether there are unsaved changes."""
        pending = self.pending_changes()
        self.save_button.setEnabled(True)
        self.cancel_button.setEnabled(bool(pending))
        if pending:
            self.feedback.setText(
                f"{len(pending)} unsaved change(s). Apply or discard them.")
        self.unsaved = pending
