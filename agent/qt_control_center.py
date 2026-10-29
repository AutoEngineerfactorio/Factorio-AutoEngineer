"""Read-only industrial command center for the AutoEngineer Qt dashboard.

All values originate in the observed Qt state. Navigation opens existing
workspaces; unsafe or unimplemented game controls are visibly locked.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Mapping

from production_telemetry import format_power
from qt_theme import HeaderState, MetricTile, Palette
from qt_visual_assets import icon

qt = import_module("PySide6.QtCore")
w = import_module("PySide6.QtWidgets")
QWidget, QFrame = w.QWidget, w.QFrame
QLabel, QPushButton = w.QLabel, w.QPushButton
QVBoxLayout = w.QVBoxLayout
QHBoxLayout, QGridLayout = w.QHBoxLayout, w.QGridLayout
Qt = qt.Qt


def text(value: str, kind: str = "muted") -> Any:
    result = QLabel(value)
    result.setObjectName(kind)
    result.setWordWrap(kind not in ("commandHeadline", "commandTitle", "commandValue", "commandMetric"))
    return result


def section(title: str, subtitle: str = "") -> tuple[Any, Any]:
    card = QFrame()
    card.setObjectName("commandCard")
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    header = QFrame()
    header.setObjectName("commandCardHeader")
    row = QHBoxLayout(header)
    row.setContentsMargins(14, 8, 14, 8)
    glyph = {"Quick Control": "play", "Current World": "blueprint",
             "AI Session": "brain", "Telemetry": "chart",
             "Blueprint Planner": "blueprint", "Production & Tasks": "gear"}
    image = QLabel()
    image.setPixmap(icon(glyph.get(title, "dashboard"), "#ffa323").pixmap(24, 24))
    row.addWidget(image)
    row.addSpacing(4)
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
    return card, body


def action(label: str, callback: Callable[[], Any] | None = None,
           *, role: str = "tool", reason: str = "") -> Any:
    button = QPushButton(label)
    button.setObjectName(role)
    button.setCursor(Qt.PointingHandCursor)
    if callback is not None:
        button.clicked.connect(callback)
    else:
        button.setEnabled(False)
        button.setToolTip(reason or "Requires a verified controller integration")
    return button


class CommandCenter(w.QScrollArea):
    """Overview layout with truthful, incrementally updated status and links."""

    def __init__(self, navigate: Callable[[str], Any], parent: Any = None):
        super().__init__(parent)
        self.navigate = navigate
        self._telemetry_values: dict[str, str] = {}
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("commandScroll")
        content = QWidget()
        content.setObjectName("commandContent")
        root = QVBoxLayout(content)
        root.setContentsMargins(17, 10, 14, 10)
        root.setSpacing(11)
        self.setWidget(content)

        self.live = text("● OFFLINE", "badgeUnavailable")
        quick, quick_body = section("Quick Control",
            "Load a save, choose a profile, and start AI supervision")
        quick_row = QHBoxLayout()
        quick_row.setSpacing(18)
        profile = QVBoxLayout()
        profile.addWidget(text("Load Save", "headerCaption"))
        self.quick_profile = text("—", "selectorValue")
        profile.addWidget(self.quick_profile)
        quick_row.addLayout(profile, 3)
        quick_row.addWidget(action("Browse saves", lambda: navigate("Saves")))
        game = QVBoxLayout()
        game.addWidget(text("AI Profile", "headerCaption"))
        game.addWidget(text("AI Helper (Read only)", "selectorValue"))
        self.quick_version = text("—")
        self.quick_version.hide()
        game.addWidget(self.quick_version)
        quick_row.addLayout(game, 3)
        quick_row.addWidget(action("Settings", lambda: navigate("Settings")))
        quick_row.addWidget(action("Start AI Supervision", role="positive", reason=(
            "No verified AI controller is attached")), 2)
        quick_row.addWidget(action("Stop AI", role="danger", reason=(
            "No verified AI controller is attached")), 1)
        quick_body.addLayout(quick_row)
        root.addWidget(quick)

        middle = QGridLayout()
        middle.setSpacing(11)
        world, world_body = section("Current World")
        summary = QHBoxLayout()
        preview = QFrame()
        preview.setObjectName("worldPreview")
        preview.setMinimumSize(180, 104)
        preview.setMaximumWidth(250)
        preview_body = QVBoxLayout(preview)
        preview_icon = QLabel()
        preview_icon.setPixmap(icon("map", "#53656f", 64).pixmap(64, 64))
        preview_icon.setAlignment(Qt.AlignCenter)
        preview_body.addWidget(preview_icon)
        preview_label = text("World preview unavailable", "faint")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_body.addWidget(preview_label)
        summary.addWidget(preview, 2)
        grid = QGridLayout()
        grid.setSpacing(9)
        self.world_fields = {}
        for index, name in enumerate(("Profile", "Version", "Connection", "Player")):
            tile = QVBoxLayout()
            caption = {"Profile": "Save Name", "Connection": "Status"}.get(name, name)
            tile.addWidget(text(caption, "headerCaption"))
            result = text("—", "commandValue")
            tile.addWidget(result)
            self.world_fields[name] = result
            grid.addLayout(tile, index // 2, index % 2)
        summary.addLayout(grid, 3)
        world_body.addLayout(summary)
        world_metrics = QHBoxLayout()
        for name in ("UPS", "FPS", "Play Time", "Map Size", "Day Time"):
            metric = QVBoxLayout()
            metric.addWidget(text(name, "headerCaption"))
            value = text("—", "commandMetric" if name == "UPS" else "commandValue")
            metric.addWidget(value)
            self.world_fields[name] = value
            value.setStyleSheet(f"color:{Palette.TEXT_MUTED};")
            world_metrics.addLayout(metric)
        world_body.addLayout(world_metrics)
        actions = QHBoxLayout()
        for caption, glyph in (("Save Now", "save"), ("Load Save", "folder"),
                               ("Restart", "refresh"), ("Stop Server", "stop")):
            button = action(caption, role="danger" if caption == "Stop Server" else "tool")
            button.setIcon(icon(glyph, "#c5cdd1", 18))
            actions.addWidget(button)
        world_body.addLayout(actions)
        middle.addWidget(world, 0, 0)

        session, session_body = section("AI Session")
        session_body.addWidget(self.live)
        modebar = QHBoxLayout()
        modebar.addWidget(action("AI Helper", lambda: navigate("Recipes"), role="accent"))
        modebar.addWidget(action("Semi-Autonomous", reason=(
            "Requires an approved supervised agent session and a safe Stop path")))
        modebar.addWidget(action("Full Autonomous", reason=(
            "Full autonomous execution is not yet verified")))
        session_body.addLayout(modebar)
        session_body.addWidget(text("Current Objective", "headerCaption"))
        self.objective = text("No verified AI task active", "commandValue")
        session_body.addWidget(self.objective)
        confidence = QHBoxLayout()
        confidence.addWidget(text("Confidence", "headerCaption"))
        confidence.addStretch()
        confidence.addWidget(text("—  No active AI task", "muted"))
        session_body.addLayout(confidence)
        status = QHBoxLayout()
        status.addWidget(text("Status", "headerCaption"))
        status.addStretch()
        status.addWidget(text("AI Helper • Read only", "muted"))
        session_body.addLayout(status)
        session_body.addStretch()
        actions = QHBoxLayout()
        actions.addWidget(action("Pause AI"))
        actions.addWidget(action("Edit Objective", lambda: navigate("Recipes")))
        actions.addWidget(action("Abort Task", role="danger"))
        session_body.addLayout(actions)
        middle.addWidget(session, 0, 1)
        middle.setColumnStretch(0, 4)
        middle.setColumnStretch(1, 3)
        root.addLayout(middle)

        lower = QGridLayout()
        lower.setSpacing(11)
        telemetry, telemetry_body = section("Telemetry")
        metrics = QGridLayout()
        metrics.setSpacing(9)
        self.metric_fields = {}
        for hidden in ("UPS", "Freshness"):
            self.metric_fields[hidden] = QLabel(content)
            self.metric_fields[hidden].hide()
        captions = {"Production": "Items per second", "Power Generation": "Power Production",
                    "Power": "Power Consumption", "Pollution": "Pollution (local chunk)"}
        for index, name in enumerate(("Production", "Power Generation", "Power",
                                       "Pollution", "Research", "Logistics")):
            cell = QFrame()
            cell.setObjectName("miniMetric")
            inside = QVBoxLayout(cell)
            inside.setContentsMargins(10, 6, 10, 6)
            inside.setSpacing(3)
            inside.addWidget(text(captions.get(name, name), "headerCaption"))
            value = text("—", "commandMetric")
            value.setStyleSheet(f"color:{Palette.TEXT_MUTED};")
            inside.addWidget(value)
            self.metric_fields[name] = value
            metrics.addWidget(cell, index // 3, index % 3)
        telemetry_body.addLayout(metrics)
        actions = QHBoxLayout()
        actions.addWidget(action("Production", lambda: navigate("Production")))
        actions.addWidget(action("Electrical", lambda: navigate("Electrical")))
        telemetry_body.addLayout(actions)
        lower.addWidget(telemetry, 0, 0)

        blueprint, blueprint_body = section("Blueprint Planner")
        self.blueprint_queue = w.QTableWidget(0, 3)
        self.blueprint_queue.setHorizontalHeaderLabels(["Blueprint", "Status", "Actions"])
        self.blueprint_queue.setObjectName("dashboardTable")
        self.blueprint_queue.verticalHeader().hide()
        self.blueprint_queue.horizontalHeader().setSectionResizeMode(0, w.QHeaderView.Stretch)
        self.blueprint_queue.setMinimumHeight(75)
        self.blueprint_queue.setMaximumHeight(95)
        blueprint_body.addWidget(self.blueprint_queue)
        blueprint_body.addWidget(text("No connected generation queue. Open your library to review saved drafts.", "faint"))
        actions = QHBoxLayout()
        actions.addWidget(action("Generate with AI Helper",
            lambda: navigate("Blueprint Studio"), role="accent"))
        actions.addWidget(action("Open Blueprint Library",
            lambda: navigate("Blueprint Studio")))
        blueprint_body.addLayout(actions)
        lower.addWidget(blueprint, 0, 1)
        lower.setColumnStretch(0, 4)
        lower.setColumnStretch(1, 3)
        root.addLayout(lower)

        tasks, tasks_body = section("Production & Tasks")
        self.tasks_status = text("No connected task queue", "faint")
        tasks_body.addWidget(self.tasks_status)
        self.task_table = w.QTableWidget(0, 8)
        self.task_table.setObjectName("dashboardTable")
        self.task_table.setHorizontalHeaderLabels(
            ["#", "Task", "Type", "Status", "Progress", "Started", "ETA", "Actions"])
        self.task_table.verticalHeader().hide()
        self.task_table.horizontalHeader().setSectionResizeMode(1, w.QHeaderView.Stretch)
        self.task_table.setColumnWidth(0, 32)
        for col in (2, 3, 4, 5, 6, 7):
            self.task_table.setColumnWidth(col, 110)
        self.task_table.setMinimumHeight(92)
        self.task_table.setMaximumHeight(130)
        self.task_table.setEditTriggers(w.QAbstractItemView.NoEditTriggers)
        tasks_body.addWidget(self.task_table)
        root.addWidget(tasks)


    @staticmethod
    def _safe(value: Any, maximum: int = 70) -> str:
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            result = str(value).replace("\n", " ").strip()
            if result and len(result) <= maximum:
                return result
        return "—"

    def apply_status(self, frame: Mapping[str, Any] | None,
                     state: HeaderState, tiles: list[MetricTile]) -> None:
        """Paint values from the existing verified header/metric model only."""
        payload = frame if isinstance(frame, Mapping) else {}
        profile = self._safe(payload.get("profile"))
        version = self._safe(payload.get("gameVersion"))
        if version == "—":
            cap = payload.get("capabilities")
            if isinstance(cap, Mapping):
                version = self._safe(cap.get("game_version"))
        self.quick_profile.setText(profile)
        self.quick_version.setText(version)
        self.world_fields["Profile"].setText(profile)
        self.world_fields["Version"].setText(version)
        self.world_fields["Connection"].setText(state.connection_text)
        player = payload.get("player")
        self.world_fields["Player"].setText(
            self._safe(player.get("name")) if isinstance(player, Mapping) else "—")
        self.live.setText(state.connection_text)
        self.live.setStyleSheet(f"color:{state.connection_color};font-weight:700;")
        by_name = {tile.name: tile for tile in tiles}
        for name in ("UPS", "Production", "Power"):
            tile = by_name.get(name)
            val = tile.value_text if tile and tile.observation.known else "—"
            if name == "Power" and tile and tile.observation.known:
                val = format_power(float(tile.observation.value))
            badge = tile.badge_text if tile else "Unavailable"
            self.metric_fields[name].setText(f"{val}  ·  {badge}")
            color = (Palette.ESTIMATED if tile and tile.observation.state == "estimated" else
                     Palette.OBSERVED if tile and tile.observation.known else Palette.TEXT_MUTED)
            self.metric_fields[name].setStyleSheet(f"color:{color};")
        self.world_fields["UPS"].setText(self.metric_fields["UPS"].text())
        self.world_fields["UPS"].setStyleSheet(self.metric_fields["UPS"].styleSheet())
        self.metric_fields["Freshness"].setText(state.freshness_text)
        for name, value in self._telemetry_values.items():
            self.metric_fields[name].setText(value)

    def set_telemetry_model(self, model: Any,
                            *, age_seconds: float | None = None) -> None:
        """Display the already-validated telemetry model; no extra polling."""
        data: dict[str, str] = {}
        if model.available and model.production_status != "unavailable":
            item_flows = [row for row in model.flows if row.kind == "item"]
            if item_flows:
                rate = sum(row.output_per_second for row in item_flows)
                data["Production"] = f"{rate:,.1f} items/s · derived"
        if model.available and model.power_status != "unavailable" and model.networks:
            load = sum(network.delivered_consumption_watts for network in model.networks)
            data["Power"] = f"{format_power(load)} · observed"
            generation = sum(network.delivered_generation_watts for network in model.networks)
            data["Power Generation"] = f"{format_power(generation)} · observed"
        if model.available and model.research_active is False:
            data["Research"] = "No active research · observed"
        elif model.available and model.research_active is True and model.research_progress is not None:
            data["Research"] = f"{model.research_name} · {model.research_progress:.0%}"
        if model.available and model.pollution_amount is not None:
            data["Pollution"] = f"{model.pollution_amount:,.1f} · local chunk"
        if model.partial:
            data = {key: value + " · partial" if key in ("Production", "Power", "Power Generation")
                    else value for key, value in data.items()}
        if age_seconds is not None and age_seconds > 30:
            data = {key: value + " · STALE" for key, value in data.items()}
        for name in self._telemetry_values.keys() | data.keys():
            self.metric_fields[name].setText(data.get(name, "—"))
            color = (Palette.WARNING if "STALE" in data.get(name, "") else
                     Palette.OBSERVED if name in data else Palette.TEXT_MUTED)
            self.metric_fields[name].setStyleSheet(f"color:{color};")
        self._telemetry_values = data

    def set_inventory_model(self, snapshot: Any) -> None:
        """Use the same bounded robot snapshot as the Logistics workspace."""
        if snapshot is None:
            self.metric_fields["Logistics"].setText("—")
            self.metric_fields["Logistics"].setStyleSheet(f"color:{Palette.TEXT_MUTED};")
            return
        robots = snapshot.robots if snapshot.known else None
        label = self.metric_fields["Logistics"]
        if robots is None or robots.total_logistic_robots is None:
            label.setText("—")
            label.setStyleSheet(f"color:{Palette.TEXT_MUTED};")
            return
        suffix = " · partial" if robots.partial else " · observed"
        if snapshot.state != "observed":
            suffix += " · STALE"
        available = robots.available_logistic_robots
        label.setText(f"{available if available is not None else '?'} / {robots.total_logistic_robots} bots" + suffix)
        label.setStyleSheet(f"color:{Palette.OBSERVED if snapshot.state == 'observed' else Palette.WARNING};")

    def show_disconnected(self) -> None:
        """Explicitly erase disconnected metrics instead of showing last live data."""
        self._telemetry_values.clear()
        self.live.setText("● OBSERVER DISCONNECTED")
        self.live.setStyleSheet(f"color:{Palette.ERROR};font-weight:700;")
        self.world_fields["Connection"].setText("Disconnected")
        self.world_fields["UPS"].setText("—")
        self.world_fields["UPS"].setStyleSheet(f"color:{Palette.TEXT_MUTED};")
        for value in self.metric_fields.values():
            value.setText("—")
            value.setStyleSheet(f"color:{Palette.TEXT_MUTED};")
