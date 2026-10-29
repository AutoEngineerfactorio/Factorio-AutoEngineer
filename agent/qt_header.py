"""The Qt header: the profile row, the indicators and the metric tiles.

The header is the first thing a user sees, so it is also the first place
the interface could mislead. It therefore follows two strict rules:

* The connection indicator is never optimistic. A parsed snapshot is a
  snapshot; only an explicit live marker produces a live indicator.
* Every number carries a badge that says whether it was observed,
  estimated, aged out or never seen. A value that was not observed shows
  an em dash, never a zero.

The widgets here hold no transport and no game connection. They render
what :mod:`qt_theme` builds from an observed frame.
"""

from __future__ import annotations

from importlib import import_module

from qt_theme import HeaderState, MetricTile
from qt_visual_assets import icon, install_fonts

try:
    qt_widgets = import_module("PySide6.QtWidgets")
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise SystemExit(
        "Optional UI requires PySide6: python -m pip install PySide6") from exc

QFrame = qt_widgets.QFrame
QGridLayout = qt_widgets.QGridLayout
QHBoxLayout = qt_widgets.QHBoxLayout
QLabel = qt_widgets.QLabel
QVBoxLayout = qt_widgets.QVBoxLayout
QWidget = qt_widgets.QWidget

#: How many metric tiles fit on one header row.
METRICS_PER_ROW = 4


def label(text: str, object_name: str = "") -> QLabel:
    """Return a styled label."""
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    return widget


class MetricTileWidget(QFrame):
    """One header metric tile.

    The tile shows the metric name, its value, the truthfulness badge and
    the detail. The badge is what tells a user whether the number was
    observed, estimated, aged out or never seen.
    """

    def __init__(self, tile: MetricTile, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.tile = tile
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        layout.addWidget(label(tile.name.upper(), "faint"))
        self.value = label(tile.value_text, "metric")
        layout.addWidget(self.value)
        self.badge = label(tile.badge_text, tile.badge_object_name)
        layout.addWidget(self.badge)
        self.detail = label(tile.detail_text, "faint")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

    def update_tile(self, tile: MetricTile) -> None:
        """Update the tile from a new metric tile.

        The value, the badge and the detail are only rewritten when they
        actually changed, so a redraw does not restart the whole window's
        layout.
        """
        self.tile = tile
        if self.value.text() != tile.value_text:
            self.value.setText(tile.value_text)
        if self.badge.text() != tile.badge_text:
            self.badge.setText(tile.badge_text)
            self.badge.setObjectName(tile.badge_object_name)
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)
        if self.detail.text() != tile.detail_text:
            self.detail.setText(tile.detail_text)


class HeaderWidget(QFrame):
    """The header: profile, connection, mode, freshness and the metrics."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        install_fonts()
        self.setObjectName("header")
        self.setMinimumHeight(82)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        logo=label("")
        logo.setPixmap(icon("gear","#f6a12c",64).pixmap(64,64))
        logo.setFixedSize(68,64)
        top.addWidget(logo)
        brand_box=QVBoxLayout()
        brand_box.setSpacing(2)
        brand=label("")
        brand.setTextFormat(import_module("PySide6.QtCore").Qt.RichText)
        brand.setText('<span style="color:#f6a12c">AutoEngineer</span> '
                      '<span style="color:#edf1f3">Dashboard</span>')
        brand.setObjectName("brand")
        brand_box.addWidget(brand)
        brand_box.addWidget(label("AI-POWERED FACTORIO MANAGEMENT","brandSub"))
        top.addLayout(brand_box,2)

        def field(caption,widget):
            box=QFrame()
            box.setObjectName("headerSegment")
            body=QVBoxLayout(box)
            body.setContentsMargins(14,0,14,0)
            body.setSpacing(4)
            body.addWidget(label(caption,"headerCaption"))
            body.addWidget(widget)
            top.addWidget(box,1)
            return body

        self.profile=label("Profile unknown","headerValue")
        self.profile.setMaximumWidth(280)
        self.profile.setWordWrap(True)
        field("Project / Save",self.profile)
        self.version=label("—","headerValue")
        field("Game Version",self.version)
        self.connection=label("● OFFLINE","muted")
        status_box=field("Agent Status",self.connection)
        self.mode=label("AI HELPER • READ ONLY","headerMode")
        status_box.addWidget(self.mode)
        self.freshness=label("Freshness unknown","faint")
        self.freshness.setVisible(False)
        self.tools={}
        for name,glyph in (("Notifications","bell"),("Diagnostics","terminal"),("Settings","settings")):
            button=qt_widgets.QPushButton()
            button.setObjectName("headerTool")
            button.setToolTip(name)
            button.setIcon(icon(glyph))
            button.setIconSize(import_module("PySide6.QtCore").QSize(24,24))
            button.setFixedSize(48,44)
            self.tools[name]=button
            top.addWidget(button)
        self.ai_logs=qt_widgets.QPushButton("Logs")
        self.ai_logs.setToolTip("View the local AI runtime log")
        self.ai_logs.setObjectName("headerTool")
        top.addWidget(self.ai_logs)
        self.stop_ai=qt_widgets.QPushButton("  Stop AI")
        self.stop_ai.setIcon(icon("stop","#f5f5f5",18))
        self.stop_ai.setObjectName("danger")
        self.stop_ai.setEnabled(False)
        self.stop_ai.setToolTip("No verified AI controller is connected")
        self.stop_ai.setMinimumSize(122,44)
        top.addWidget(self.stop_ai)
        layout.addLayout(top)

        self.metric_host = QWidget()
        self.metrics = QGridLayout(self.metric_host)
        self.metrics.setSpacing(10)
        self.tiles: dict[str, MetricTileWidget] = {}
        layout.addWidget(self.metric_host)
        # The command center renders these same metrics more compactly.
        # Keep header tiles alive for API compatibility and regression tests.
        self.metric_host.setVisible(False)

    def apply_game_context(self, frame) -> None:
        caps=frame.get("capabilities") or {}
        version=frame.get("gameVersion") or caps.get("game_version")
        self.version.setText(str(version) if version else "—")

    def apply_header_state(self, state: HeaderState) -> None:
        """Update the header from a header state."""
        if self.profile.text() != state.profile:
            self.profile.setText(state.profile)
        if self.connection.text() != state.connection_text:
            self.connection.setText(state.connection_text)
            self.connection.setStyleSheet(f"color: {state.connection_color};")
        if self.mode.text() != state.mode_text:
            self.mode.setText(state.mode_text)
        if self.freshness.text() != state.freshness_text:
            self.freshness.setText(state.freshness_text)

    def apply_metric_tiles(self, tiles: list[MetricTile]) -> None:
        """Create or update the metric tiles.

        A tile that already exists is updated in place, so the header does
        not rebuild its layout on every observation.
        """
        for index, tile in enumerate(tiles):
            widget = self.tiles.get(tile.name)
            if widget is None:
                widget = MetricTileWidget(tile)
                self.tiles[tile.name] = widget
                self.metrics.addWidget(
                    widget, index // METRICS_PER_ROW, index % METRICS_PER_ROW)
            else:
                widget.update_tile(tile)


__all__ = [
    "METRICS_PER_ROW",
    "HeaderWidget",
    "MetricTileWidget",
    "label",
]
