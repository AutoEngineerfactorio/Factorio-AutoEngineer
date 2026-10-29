"""The dark, Factorio-inspired theme and the header state for the Qt UI.

This module is deliberately free of any Qt import. It holds the look of the
interface and the header's summary of the current observation, so both are
testable constants rather than strings buried in a widget constructor.

The truthfulness rules live in :mod:`qt_observation`, which this module
imports. The header is the first place a user looks, so it is also the
first place that could lie: it must never claim a live connection it does
not have, and it must never show an unobserved metric as a number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

from qt_observation import (
    OBSERVED,
    Observation,
    observed,
    optional_number,
    optional_text,
    unavailable,
)

# --------------------------------------------------------------------------
# The palette
# --------------------------------------------------------------------------

class Palette:
    """The dark, Factorio-inspired colour palette.

    The colours are named constants so the stylesheet and the painters use
    the same values, and so a test can assert that a chart series and a
    panel background stay visually distinct.
    """

    WINDOW = "#0c1216"
    SURFACE = "#11191e"
    CARD = "#172126"
    CARD_RAISED = "#253139"
    BORDER = "#344554"
    BORDER_STRONG = "#46607a"

    TEXT = "#e7edf3"
    TEXT_BRIGHT = "#f4f8fb"
    TEXT_MUTED = "#93a2b1"
    TEXT_FAINT = "#6b7a89"

    ACCENT = "#ffa323"
    ACCENT_DIM = "#a87b34"
    ACCENT_TEXT = "#1a1206"

    OBSERVED = "#43d35c"
    ESTIMATED = "#f6b34c"
    STALE = "#93a2b1"
    UNAVAILABLE = "#5a6673"
    ERROR = "#ff6861"
    WARNING = "#ffb347"
    INFO = "#78b8ed"

    PLAYER = "#5ed7f5"
    ENEMY = "#ed4e42"
    BUILDING = "#67acc2"
    NATURE = "#34462a"
    GRID = "#4a5568"

    CHART_SERIES = ("#f6b34c", "#5ed7f5", "#68b64b", "#ff9c5c",
                    "#be92b9", "#78b8ed", "#ffda65", "#b6c6d3")
    """The series colours of a telemetry chart, in drawing order."""


#: The stylesheet of the whole application.
STYLESHEET = f"""
QWidget {{
    background: {Palette.WINDOW};
    color: {Palette.TEXT};
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10pt;
}}
QLabel {{ background: transparent; }}
QMainWindow::separator {{ background: {Palette.BORDER}; width: 1px; height: 1px; }}
QFrame#card {{
    background: {Palette.CARD};
    border: 1px solid {Palette.BORDER};
    border-radius: 8px;
}}
QFrame#rail {{
    background: {Palette.SURFACE};
    border-right: 1px solid {Palette.BORDER};
}}
QFrame#header {{
    background: {Palette.SURFACE};
    border-bottom: 1px solid {Palette.BORDER};
}}
QLabel#brand {{ color: {Palette.ACCENT}; font-size: 17pt; font-weight: 800; }}
QLabel#brandSub {{ color: {Palette.TEXT_MUTED}; font-size: 9pt; }}
QLabel#heading {{ color: {Palette.TEXT_BRIGHT}; font-size: 12pt; font-weight: 700; }}
QLabel#muted {{ color: {Palette.TEXT_MUTED}; }}
QLabel#faint {{ color: {Palette.TEXT_FAINT}; font-size: 9pt; }}
QLabel#metric {{ color: {Palette.TEXT_BRIGHT}; font-size: 21pt; font-weight: 700; }}
QLabel#metricUnit {{ color: {Palette.TEXT_MUTED}; font-size: 9pt; }}
QLabel#badgeObserved {{ color: {Palette.OBSERVED}; font-size: 8pt; font-weight: 700; }}
QLabel#badgeEstimated {{ color: {Palette.ESTIMATED}; font-size: 8pt; font-weight: 700; }}
QLabel#badgeStale {{ color: {Palette.STALE}; font-size: 8pt; font-weight: 700; }}
QLabel#badgeUnavailable {{ color: {Palette.UNAVAILABLE}; font-size: 8pt; font-weight: 700; }}
QLabel#badgeError {{ color: {Palette.ERROR}; font-size: 8pt; font-weight: 700; }}
QLabel#badgeWarning {{ color: {Palette.WARNING}; font-size: 8pt; font-weight: 700; }}
QLabel#badgeInfo {{ color: {Palette.INFO}; font-size: 8pt; font-weight: 700; }}
QPushButton#nav {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: {Palette.TEXT_MUTED};
    padding: 9px 12px;
    text-align: left;
}}
QPushButton#nav:hover {{ background: {Palette.CARD}; color: {Palette.TEXT}; }}
QPushButton#nav:checked {{
    background: {Palette.CARD_RAISED};
    border: 1px solid {Palette.ACCENT_DIM};
    color: {Palette.ACCENT};
    font-weight: 700;
}}
QPushButton#tool {{
    background: {Palette.CARD};
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    color: {Palette.TEXT};
    padding: 5px 10px;
}}
QPushButton#tool:hover {{ border-color: {Palette.BORDER_STRONG}; }}
QPushButton#tool:checked {{
    background: {Palette.CARD_RAISED};
    border-color: {Palette.ACCENT_DIM};
    color: {Palette.ACCENT};
}}
QPlainTextEdit, QTextEdit {{
    background: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    color: {Palette.TEXT};
    padding: 8px;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 9pt;
}}
QTableWidget, QTableView {{
    background: {Palette.SURFACE};
    alternate-background-color: {Palette.CARD};
    gridline-color: {Palette.BORDER};
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    selection-background-color: {Palette.CARD_RAISED};
    selection-color: {Palette.TEXT_BRIGHT};
}}
QHeaderView::section {{
    background: {Palette.CARD};
    color: {Palette.TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {Palette.BORDER};
    padding: 5px;
}}
QSplitter::handle {{ background: {Palette.BORDER}; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:vertical {{ height: 3px; }}
QScrollBar:vertical {{ background: {Palette.SURFACE}; width: 11px; margin: 0; }}
QScrollBar:horizontal {{ background: {Palette.SURFACE}; height: 11px; margin: 0; }}
QScrollBar::handle {{ background: {Palette.BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:hover {{ background: {Palette.BORDER_STRONG}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    color: {Palette.TEXT};
    padding: 4px 8px;
}}
QComboBox QAbstractItemView {{
    background: {Palette.SURFACE};
    border: 1px solid {Palette.BORDER};
    selection-background-color: {Palette.CARD_RAISED};
}}
QToolTip {{
    background: {Palette.CARD_RAISED};
    color: {Palette.TEXT};
    border: 1px solid {Palette.ACCENT_DIM};
    padding: 4px;
}}
QStatusBar {{ background: {Palette.SURFACE}; color: {Palette.TEXT_MUTED}; }}
QStatusBar::item {{ border: none; }}
QWidget#commandContent, QScrollArea#commandScroll {{
    background: {Palette.WINDOW};
}}
QFrame#commandCard {{
    background: #192127;
    border: 1px solid #354148;
    border-radius: 7px;
}}
QFrame#miniMetric {{
    background: #11191e;
    border: 1px solid #29373e;
    border-radius: 6px;
}}
QLabel#commandHeadline {{
    color: #f0f4f4;
    font-size: 18pt;
    font-weight: 800;
}}
QLabel#commandTitle {{
    color: #ffa43c;
    font-size: 11pt;
    font-weight: 750;
}}
QLabel#commandValue {{
    color: #e9f1f1;
    font-size: 11pt;
    font-weight: 700;
}}
QLabel#commandMetric {{
    color: #6fdb78;
    font-size: 14pt;
    font-weight: 800;
}}
QPushButton#accent {{
    background: #ea9731;
    color: #1b140d;
    font-weight: 800;
    border: 1px solid #f1a947;
    border-radius: 5px;
    padding: 9px 14px;
}}
QPushButton#accent:hover {{ background: #f4ad50; }}
QPushButton#accent:disabled {{ background: #3d3931; color: #918675; }}
QPushButton#nav:checked {{
    border-left: 4px solid #f49a29;
    background: #382c20;
    border-top: 1px solid #765026;
    border-right: 1px solid #765026;
    border-bottom: 1px solid #765026;
    color: #ffb451;
}}
QPushButton:disabled {{
    color: #77838c;
    background: #222a30;
}}
/* Industrial dashboard reference: compact steel chrome and readable cards. */
QFrame#header {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #182229,stop:1 #0c1317);
    border-bottom: 1px solid #38464e;
}}
QFrame#headerSegment {{ background: transparent; border-left: 1px solid #2e3c44; }}
QLabel#brand {{ font-size: 19pt; font-weight: 700; }}
QLabel#brandSub {{ font-size: 8pt; letter-spacing: 2px; color: #8c9aa3; }}
QLabel#headerCaption {{ font-size: 9pt; color: #b4bec5; }}
QLabel#headerValue {{ font-size: 11pt; font-weight: 600; color: #edf0f2; }}
QLabel#headerMode {{ font-size: 8pt; color: #8897a0; }}
QPushButton#headerTool, QPushButton#tool {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #35424b,stop:1 #1c272e);
    border: 1px solid #4a5a64; border-radius: 4px;
    padding: 8px 12px; color: #e9edef;
}}
QPushButton#headerTool:hover, QPushButton#tool:hover {{ border-color: #8b9aa4; }}
QPushButton#tool:disabled, QPushButton#headerTool:disabled {{
    color: #6d7d86; background: #1b262c; border-color: #34434b;
}}
QFrame#rail {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #131c22,stop:1 #0d151a);
    border-right: 1px solid #303f48;
}}
QPushButton#nav {{
    text-align: left; padding: 14px 12px; margin: 0;
    border: 1px solid transparent; border-radius: 3px;
    color: #b9c3cb; font-size: 10pt; background: transparent;
}}
QPushButton#nav:checked {{
    border-left: 5px solid #ff9f20; border-top: 1px solid #82551f;
    border-bottom: 1px solid #82551f; border-right: 1px solid #82551f;
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4b321b,stop:.3 #24221d,stop:1 #1a2023);
    color: #f3f3ef; font-weight: 700;
}}
QFrame#commandCard {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #162128,stop:1 #0e171c);
    border: 1px solid #394850; border-radius: 6px;
}}
QFrame#commandCardHeader {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #233139,stop:1 #162127);
    border-bottom: 1px solid #2c3a42; border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QWidget#commandCardBody {{ background: transparent; }}
QLabel#selectorValue {{
    border: 1px solid #48565e; border-radius: 3px;
    background: #0d151a; padding: 8px 12px; color: #e7ecef;
    font-size: 10pt; font-weight: 600;
}}
QFrame#worldPreview {{ background: #0b1216; border: 1px solid #26353c; }}
QTableWidget#dashboardTable {{ background: #10191e; border: 1px solid #2b3a42; }}
QTableWidget#dashboardTable QHeaderView::section {{
    background: #172228; border: 0; border-bottom: 1px solid #2b3a42;
    color: #a6b4bc; padding: 4px 8px; font-size: 9pt; text-align: left;
}}

QLabel#commandTitle {{ color: #eef0f1; font-size: 12pt; font-weight: 700; }}
QLabel#commandValue {{ color: #eef1f2; font-size: 10pt; font-weight: 600; }}
QLabel#commandMetric {{ color: #51de69; font-size: 14pt; font-weight: 700; }}
QFrame#miniMetric {{ background: #101a1f; border: 1px solid #25353e; border-radius: 3px; }}
QPushButton#accent {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffb64b,stop:1 #ed8b16);
    color: #17110a; border: 1px solid #ffc164; border-radius: 4px;
    padding: 8px 12px; font-weight: 700;
}}
QPushButton#positive {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #35b94b,stop:1 #1d7b30);
    color: white; border: 1px solid #51cd65; border-radius: 4px;
    padding: 8px 14px; font-weight: 600;
}}
QPushButton#danger {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #d83d3b,stop:1 #9b1f23);
    color: white; border: 1px solid #e2635b; border-radius: 4px;
    padding: 8px 14px; font-weight: 600;
}}
QPushButton#danger:disabled {{ color: #c89898; background: #4b2328; border-color: #68383e; }}
QPushButton#positive:disabled {{ color: #83aa8b; background: #203d2a; border-color: #3b6848; }}

"""

# --------------------------------------------------------------------------
# Connection and mode indicators
# --------------------------------------------------------------------------

OFFLINE = "offline"
SNAPSHOT = "snapshot"
LIVE = "live"
UNAVAILABLE_STATE = "unavailable"

CONNECTION_STATES = (OFFLINE, SNAPSHOT, LIVE, UNAVAILABLE_STATE)

CONNECTION_LABELS = {
    OFFLINE: "● OFFLINE",
    SNAPSHOT: "◆ LOCAL SNAPSHOT",
    LIVE: "● LIVE OBSERVATION",
    UNAVAILABLE_STATE: "● OBSERVER UNAVAILABLE",
}

CONNECTION_COLORS = {
    OFFLINE: Palette.TEXT_MUTED,
    SNAPSHOT: Palette.ACCENT,
    LIVE: Palette.OBSERVED,
    UNAVAILABLE_STATE: Palette.ERROR,
}

HELPER = "helper"
SEMI = "semi"
FULL = "full"

MODE_LABELS = {
    HELPER: "AI HELPER • READ ONLY",
    SEMI: "SEMI-AUTONOMOUS",
    FULL: "FULLY AUTONOMOUS (LOCKED)",
}


def connection_state(frame: Mapping[str, Any] | None) -> str:
    """Derive the connection indicator from a frame.

    The state is never optimistic. A frame that says the observer is
    unavailable is reported as unavailable, and a frame with no live
    transport is a snapshot, never a live connection.
    """
    if not isinstance(frame, Mapping):
        return OFFLINE
    if frame.get("status") == "unavailable":
        return UNAVAILABLE_STATE
    if frame.get("live") is True or frame.get("transport") == "live":
        return LIVE
    if frame.get("status") == "ok" or frame.get("schema") is not None:
        return SNAPSHOT
    return OFFLINE


def profile_label(frame: Mapping[str, Any] | None) -> str:
    """Return the profile and game version shown in the header.

    Only observed fields are used. When the game version was not reported,
    the label says so instead of guessing the version.
    """
    if not isinstance(frame, Mapping):
        return "Profile unknown"
    profile = optional_text(frame, "profile", 64)
    version = optional_text(frame, "gameVersion", 32)
    parts = [part for part in (profile, version) if part]
    return " • ".join(parts) if parts else "Profile unknown"


def freshness_label(age_seconds: float | None) -> str:
    """Return the freshness text shown next to the observation age."""
    if age_seconds is None:
        return "Freshness unknown"
    if not math.isfinite(age_seconds):
        return "Freshness unknown"
    if age_seconds < 1.0:
        return "Fresh (<1s)"
    if age_seconds < 60.0:
        return f"Fresh ({age_seconds:.0f}s)"
    return f"Stale ({age_seconds / 60.0:.1f} min)"


@dataclass
class HeaderState:
    """Everything the header shows about the current observation."""

    connection: str = OFFLINE
    profile: str = "Profile unknown"
    mode: str = HELPER
    age_seconds: float | None = None
    message: str = ""

    @property
    def connection_text(self) -> str:
        return CONNECTION_LABELS.get(self.connection, CONNECTION_LABELS[OFFLINE])

    @property
    def connection_color(self) -> str:
        return CONNECTION_COLORS.get(self.connection, Palette.TEXT_MUTED)

    @property
    def mode_text(self) -> str:
        return MODE_LABELS.get(self.mode, MODE_LABELS[HELPER])

    @property
    def freshness_text(self) -> str:
        return freshness_label(self.age_seconds)


def build_header_state(frame: Mapping[str, Any] | None, *, mode: str = HELPER,
                       age_seconds: float | None = None,
                       message: str = "",
                       selected_profile: str = "") -> HeaderState:
    """Build the header state from one observed frame.

    ``selected_profile`` is the profile the launcher has selected. It is
    shown when the frame does **not** carry an observed profile, so the
    header names the profile the application is working with even when no
    game is connected. An observed profile always wins: the game is the
    authority on what it is running.
    """
    if mode not in MODE_LABELS:
        raise ValueError(f"Unknown operating mode: {mode!r}")
    observed = profile_label(frame)
    if observed == "Profile unknown" and selected_profile.strip():
        observed = selected_profile.strip()
    return HeaderState(
        connection=connection_state(frame),
        profile=observed,
        mode=mode,
        age_seconds=age_seconds,
        message=message,
    )


# --------------------------------------------------------------------------
# The metric tiles
# --------------------------------------------------------------------------

@dataclass
class MetricTile:
    """One header metric: a name, a value and the truthfulness of that value."""

    name: str
    observation: Observation = field(default_factory=unavailable)
    unit: str = ""

    @property
    def value_text(self) -> str:
        return self.observation.display()

    @property
    def badge_text(self) -> str:
        return self.observation.badge()

    @property
    def badge_object_name(self) -> str:
        return self.observation.badge_object_name()

    @property
    def detail_text(self) -> str:
        return self.observation.detail


def build_metric_tiles(frame: Mapping[str, Any] | None) -> list[MetricTile]:
    """Build the header metric tiles from one observed frame.

    A field that is absent produces an **unavailable** tile, never a zero.
    """
    source = frame if isinstance(frame, Mapping) else {}
    return [
        MetricTile("Game / profile", Observation(
            value=profile_label(source), state=OBSERVED,
            detail="Observed profile", source="frame")),
        MetricTile("UPS", _number_observation(source, "ups")),
        MetricTile("Power", _power_observation(source)),
        MetricTile("Production", _production_observation(source)),
    ]


def _number_observation(source: Mapping[str, Any], key: str) -> Observation:
    """Return an observed or unavailable numeric observation."""
    value = optional_number(source, key)
    if value is None:
        return unavailable("Not reported by the observer", source=key)
    return observed(value, "Observed snapshot", source=key)


def _power_observation(source: Mapping[str, Any]) -> Observation:
    """Return the power observation, distinguishing observed from derived."""
    power = source.get("power")
    if isinstance(power, Mapping):
        generation = optional_number(power, "generation")
        consumption = optional_number(power, "consumption")
        if generation is None and consumption is None:
            return unavailable(
                optional_text(power, "reason", 160) or "Power not reported",
                source="power")
        detail = "Observed power network"
        satisfaction = optional_number(power, "satisfaction")
        if satisfaction is not None:
            # Satisfaction is observed next to the load, so the header can
            # show whether the network is actually keeping up.
            detail = f"Observed power network • satisfaction {satisfaction:.1%}"
        return observed(
            consumption if consumption is not None else generation,
            detail,
            source="power",
        )
    value = optional_number(source, "power")
    if value is None:
        return unavailable("Not reported by the observer", source="power")
    return observed(value, "Observed snapshot", source="power")


def _production_observation(source: Mapping[str, Any]) -> Observation:
    """Return the production observation, distinguishing observed from derived."""
    production = source.get("production")
    if isinstance(production, Mapping):
        status = production.get("status")
        if status == "unavailable":
            return unavailable(
                optional_text(production, "reason", 160)
                or "Production telemetry unavailable",
                source="production",
            )
        rate = optional_number(production, "rate")
        if rate is None:
            return unavailable("Production rate not reported", source="production")
        return observed(rate, "Observed production rate", source="production")
    value = optional_number(source, "production")
    if value is None:
        return unavailable("Not reported by the observer", source="production")
    return observed(value, "Observed snapshot", source="production")


__all__ = [
    "CONNECTION_COLORS",
    "CONNECTION_LABELS",
    "CONNECTION_STATES",
    "FULL",
    "HELPER",
    "HeaderState",
    "LIVE",
    "MODE_LABELS",
    "MetricTile",
    "OFFLINE",
    "Palette",
    "SEMI",
    "SNAPSHOT",
    "STYLESHEET",
    "TelemetrySeries",
    "UNAVAILABLE_STATE",
    "build_header_state",
    "build_metric_tiles",
    "connection_state",
    "freshness_label",
    "profile_label",
    "series_color",
]


# --------------------------------------------------------------------------
# Telemetry series
# --------------------------------------------------------------------------

def series_color(index: int) -> str:
    """Return the colour of the *index*-th chart series.

    The colours cycle, so a chart with more series than palette entries
    still renders every series in a distinct colour for the first pass
    through the palette.
    """
    if index < 0:
        raise ValueError("Series index must not be negative")
    palette = Palette.CHART_SERIES
    return palette[index % len(palette)]


@dataclass
class TelemetrySeries:
    """One bounded telemetry series for a chart.

    ``points`` holds the samples in observation order. The series keeps its
    own bound so a chart can never grow without limit, which is what keeps
    the historical graphs bounded.
    """

    name: str
    unit: str = ""
    points: list[float] = field(default_factory=list)
    maximum_points: int = 240
    color: str = ""

    def append(self, value: Any) -> None:
        """Append one finite sample, dropping the oldest when full.

        The value is validated at runtime rather than only by the type
        hint, because the samples arrive from a decoded observation frame
        and a NaN in a chart series breaks the chart's own scale.
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Telemetry samples must be numbers")
        if not math.isfinite(value):
            raise ValueError("Telemetry samples must be finite")
        if self.maximum_points < 1:
            raise ValueError("Telemetry series must keep at least one point")
        self.points.append(float(value))
        while len(self.points) > self.maximum_points:
            self.points.pop(0)

    @property
    def latest(self) -> float | None:
        """The most recent sample, or ``None`` when there is none."""
        return self.points[-1] if self.points else None

    @property
    def color_for_chart(self) -> str:
        """The colour this series draws in."""
        return self.color or series_color(0)
