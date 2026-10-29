"""The Qt telemetry workspace: the production and electrical pages.

This widget shows the observed telemetry: the **historical charts**, the
material flow table, the electrical network table, the bottleneck candidates
and the freshness of the observation.

It renders the model that :mod:`qt_telemetry` prepares and the history that
:mod:`qt_telemetry_history` keeps, so the truthfulness rules live in one
testable place. A missing observation shows an empty table and says so; it
never shows a row of zeroes. A chart never draws a point that was not
observed.

The widget holds no transport. It renders what the observation service
already produced.
"""

from __future__ import annotations

import time
from importlib import import_module
from typing import Any, Mapping

from qt_chart import ChartSpec, TelemetryChartWidget
from qt_telemetry import (
    TelemetryModel,
    build_model,
    format_flow_rate,
    network_display,
)
from qt_telemetry_history import (
    FLOW_INPUT,
    FLOW_OUTPUT,
    POWER_CONSUMPTION,
    POWER_GENERATION,
    POWER_SATISFACTION,
    TelemetryHistory,
)
from qt_theme import series_color

try:
    qt_core = import_module("PySide6.QtCore")
    qt_widgets = import_module("PySide6.QtWidgets")
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise SystemExit(
        "Optional UI requires PySide6: python -m pip install PySide6") from exc

QAbstractItemView = qt_widgets.QAbstractItemView
QComboBox = qt_widgets.QComboBox
QFrame = qt_widgets.QFrame
QGridLayout = qt_widgets.QGridLayout
QHBoxLayout = qt_widgets.QHBoxLayout
QHeaderView = qt_widgets.QHeaderView
QLabel = qt_widgets.QLabel
QPlainTextEdit = qt_widgets.QPlainTextEdit
QSplitter = qt_widgets.QSplitter
QTableWidget = qt_widgets.QTableWidget
QTableWidgetItem = qt_widgets.QTableWidgetItem
QVBoxLayout = qt_widgets.QVBoxLayout
QWidget = qt_widgets.QWidget

#: The vertical splitter orientation.
Qt_Vertical = qt_core.Qt.Orientation.Vertical

#: The columns of the production table.
FLOW_COLUMNS = ("Material", "Kind", "In /min", "Out /min", "In /s",
                 "Out /s", "Net /min")

#: The columns of the electrical table.
POWER_COLUMNS = ("Network", "Available Power", "Requested Power", "Demand Energy /s",
                 "Satisfaction", "Headroom")

#: The key of every electrical column in the display mapping.
#:
#: The column *headers* are labels a user reads, while the display mapping
#: is keyed by the name the telemetry model uses. The two are kept apart on
#: purpose: looking a header up in the display mapping would silently
#: produce an empty cell for every column.
POWER_KEYS = ("network", "generation", "consumption", "energy_per_second",
              "satisfaction", "headroom")

#: The upper bound on the rows one table shows.
MAX_ROWS = 200

#: The number of charts side by side.
#:
#: Two columns keep a chart readable on a 1440p display. A single column
#: would stretch one chart across the whole window, which makes a rate
#: change impossible to see.
CHART_COLUMNS = 2

#: The role of a telemetry workspace.
ROLE_PRODUCTION = "production"
ROLE_ELECTRICAL = "electrical"

#: The chart kinds the production workspace draws, in drawing order.
PRODUCTION_SERIES = (FLOW_OUTPUT, FLOW_INPUT)

#: The chart kinds the electrical workspace draws, in drawing order.
ELECTRICAL_SERIES = (POWER_GENERATION, POWER_CONSUMPTION, POWER_SATISFACTION)

#: The title of every chart kind.
SERIES_TITLES = {
    FLOW_OUTPUT: "Output",
    FLOW_INPUT: "Input",
    POWER_GENERATION: "Available power",
    POWER_CONSUMPTION: "Requested power",
    POWER_SATISFACTION: "Satisfaction",
}


def _table(headers: tuple[str, ...]) -> QTableWidget:
    """Return a read-only table with the given headers."""
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    return table


class TelemetryWidget(QWidget):
    """The production and electrical workspace.

    The widget keeps its own bounded :class:`~qt_telemetry_history.TelemetryHistory`
    and draws the historical charts from it. The history is fed by
    :meth:`set_telemetry`, which validates the payload with the existing
    telemetry model first: an invalid payload contributes **no** sample, so
    the charts can only ever show what was really observed.
    """

    def __init__(self, role: str = ROLE_PRODUCTION,
                 parent: QWidget | None = None,
                 history: TelemetryHistory | None = None):
        super().__init__(parent)
        if role not in (ROLE_PRODUCTION, ROLE_ELECTRICAL):
            raise ValueError(f"Unknown telemetry workspace role: {role!r}")
        self._role = role
        self._history = history if history is not None else TelemetryHistory()
        self._model = build_model(None)
        self._series_kinds = (PRODUCTION_SERIES if role == ROLE_PRODUCTION
                              else ELECTRICAL_SERIES)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self.status = QLabel("No telemetry observation yet")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        self.freshness = QLabel("Freshness unknown")
        self.freshness.setObjectName("faint")
        layout.addWidget(self.freshness)

        self.surface = QLabel("")
        self.surface.setObjectName("faint")
        layout.addWidget(self.surface)

        self.selector_label = QLabel(
            "Observed material" if role == ROLE_PRODUCTION
            else "Observed electrical network")
        self.selector_label.setObjectName("faint")
        layout.addWidget(self.selector_label)

        self.selector = QComboBox()
        self.selector.setObjectName("tool")
        self.selector.currentIndexChanged.connect(self._on_selection_changed)
        layout.addWidget(self.selector)

        splitter = QSplitter(Qt_Vertical)

        chart_box = QFrame()
        chart_layout = QVBoxLayout(chart_box)
        chart_layout.setContentsMargins(8, 8, 8, 8)
        self.chart_title = QLabel("HISTORY")
        self.chart_title.setObjectName("faint")
        chart_layout.addWidget(self.chart_title)
        # The charts are laid out in a **grid**, not a column, so a chart
        # keeps a readable width on a 1440p display instead of stretching
        # across the whole window.
        self.chart_grid = QGridLayout()
        self.chart_grid.setSpacing(6)
        chart_layout.addLayout(self.chart_grid)
        self.charts: list[TelemetryChartWidget] = []
        splitter.addWidget(chart_box)

        flow_box = QFrame()
        flow_layout = QVBoxLayout(flow_box)
        flow_layout.setContentsMargins(8, 8, 8, 8)
        flow_layout.addWidget(QLabel("PRODUCTION FLOWS", ))
        flow_layout.itemAt(0).widget().setObjectName("faint")
        self.flow_table = _table(FLOW_COLUMNS)
        flow_layout.addWidget(self.flow_table)
        splitter.addWidget(flow_box)

        power_box = QFrame()
        power_layout = QVBoxLayout(power_box)
        power_layout.setContentsMargins(8, 8, 8, 8)
        power_layout.addWidget(QLabel("ELECTRICAL NETWORKS"))
        power_layout.itemAt(0).widget().setObjectName("faint")
        self.power_table = _table(POWER_COLUMNS)
        power_layout.addWidget(self.power_table)
        splitter.addWidget(power_box)

        layout.addWidget(splitter, 1)

        self.candidates = QPlainTextEdit()
        self.candidates.setReadOnly(True)
        self.candidates.setMaximumHeight(140)
        layout.addWidget(self.candidates)

        self._apply(self._model)

    # -- the observation -------------------------------------------------

    def set_telemetry(self, telemetry: Mapping[str, Any] | None, *,
                      age_seconds: float | None = None,
                      at: float | None = None) -> None:
        """Show one observed telemetry payload.

        The payload is validated by the existing telemetry model and only
        then recorded in the history. A payload that does not validate
        contributes **no** sample, so a chart never shows a point that was
        not observed.
        """
        moment = time.time() if at is None else float(at)
        model = build_model(telemetry)
        self._history.observe(telemetry, at=moment, tick=model.tick)
        self._model = model
        self._apply(self._model, age_seconds=age_seconds)

    @property
    def model(self) -> TelemetryModel:
        """The model the widget currently shows."""
        return self._model

    @property
    def history(self) -> TelemetryHistory:
        """The bounded history behind the charts."""
        return self._history

    @property
    def role(self) -> str:
        """The role of this workspace."""
        return self._role

    # -- rendering --------------------------------------------------------

    def _apply(self, model: TelemetryModel, *,
               age_seconds: float | None = None) -> None:
        """Render the model."""
        self.status.setText(model.status_text or model.reason
                            or "No telemetry observation yet")
        observation = model.freshness(age_seconds)
        self.freshness.setText(
            f"{observation.badge()} • {observation.detail}")
        # The surface names the world the numbers describe. It is shown
        # only when the observation reported one, so the panel never
        # claims a surface that was not observed. The label is hidden
        # rather than left blank, so no empty label reaches the screen.
        if model.surface:
            self.surface.setText(f"Surface: {model.surface}")
            self.surface.setVisible(True)
        else:
            self.surface.setText("Surface: not reported")
            self.surface.setVisible(True)
        self._fill_flows(model)
        self._fill_networks(model)
        self._fill_candidates(model)
        self._refresh_charts()

    # -- the charts --------------------------------------------------------

    def _selected_subject(self) -> str:
        """Return the name of the selected material or network.

        The selection is the **name** of the observed subject, so it is
        matched against the history's own keys rather than against an
        index that could shift.
        """
        index = self.selector.currentIndex()
        if index < 0:
            return ""
        data = self.selector.itemData(index)
        return data if isinstance(data, str) else ""

    def _subjects(self) -> list[str]:
        """Return the names of every observed subject of this workspace.

        The names come from the history, so only subjects that were really
        observed are offered.
        """
        names: list[str] = []
        for kind in self._series_kinds:
            prefix = f"{kind}:"
            for key in self._history.series_keys():
                if not key.startswith(prefix):
                    continue
                name = key[len(prefix):]
                if name not in names:
                    names.append(name)
        return names

    def _refresh_selector(self) -> None:
        """Refresh the list of observed subjects.

        The selection is kept when it is still observed, so a new
        observation does not move the user's choice.
        """
        current = self._selected_subject()
        subjects = self._subjects()
        self.selector.blockSignals(True)
        try:
            self.selector.clear()
            for name in subjects:
                self.selector.addItem(name, name)
            if current and current in subjects:
                self.selector.setCurrentIndex(subjects.index(current))
        finally:
            self.selector.blockSignals(False)

    def _on_selection_changed(self, _index: int) -> None:
        """Redraw the charts for the newly selected subject."""
        self._refresh_charts()

    def _chart_specs(self) -> list[ChartSpec]:
        """Return the specs of the charts this workspace draws.

        One chart is drawn per series kind of the selected subject, so the
        production workspace shows the output and the input of one
        material and the electrical workspace shows the generation, the
        consumption and the satisfaction of one network.
        """
        subject = self._selected_subject()
        if not subject:
            return []
        specs: list[ChartSpec] = []
        for index, kind in enumerate(self._series_kinds):
            key = f"{kind}:{subject}"
            history = self._history.chart(key)
            if history.empty and not specs:
                # The subject was selected but nothing was observed for it
                # yet; an empty chart is shown rather than nothing at all.
                specs.append(ChartSpec(
                    key=key, title=f"{SERIES_TITLES.get(kind, kind)} "
                                    f"— {subject}",
                    unit=history.unit, color=series_color(index)))
                continue
            specs.append(ChartSpec(
                key=key,
                title=f"{SERIES_TITLES.get(kind, kind)} — {subject}",
                unit=history.unit,
                values=tuple(history.values),
                stamps=tuple(history.stamps),
                color=series_color(index),
            ))
        return specs

    def _refresh_charts(self) -> None:
        """Rebuild the chart widgets for the current selection."""
        self._refresh_selector()
        specs = self._chart_specs()
        stale = not self._model.available
        # The chart widgets are reused, so a steady observation stream does
        # not allocate a widget per sample.
        while len(self.charts) < len(specs):
            chart = TelemetryChartWidget()
            self.charts.append(chart)
        while len(self.charts) > len(specs):
            chart = self.charts.pop()
            self.chart_grid.removeWidget(chart)
            chart.setParent(None)
            chart.deleteLater()
        for index, (chart, spec) in enumerate(zip(self.charts, specs)):
            spec.stale = stale
            chart.set_spec(spec)
            self.chart_grid.addWidget(chart, index // CHART_COLUMNS,
                                      index % CHART_COLUMNS)
        self.chart_title.setText(
            f"{'PRODUCTION' if self._role == ROLE_PRODUCTION else 'ELECTRICAL'}"
            " HISTORY")

    def chart_values(self, index: int = 0) -> list[float]:
        """Return the observed values one chart is bound to draw.

        The values come from the chart's **spec**, which is built from the
        history, so they are exactly the observed samples. The chart
        widget itself reports the values it actually painted, which is the
        stronger proof that needs a paint to have happened.
        """
        if index < 0 or index >= len(self.charts):
            return []
        return list(self.charts[index].spec.values)

    def painted_values(self, index: int = 0) -> list[float]:
        """Return the values one chart actually painted.

        This is the stronger proof: it is empty until the chart has been
        painted, and it then holds exactly the observed samples.
        """
        if index < 0 or index >= len(self.charts):
            return []
        return self.charts[index].drawn_values()

    def _fill_flows(self, model: TelemetryModel) -> None:
        """Fill the production table."""
        rows = model.flows[:MAX_ROWS]
        self.flow_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (
                row.name,
                row.kind,
                format_flow_rate(row.input_per_minute),
                format_flow_rate(row.output_per_minute),
                f"{row.input_per_second:,.3f}",
                f"{row.output_per_second:,.3f}",
                format_flow_rate(row.net_per_minute),
            )
            for column, value in enumerate(values):
                self.flow_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_networks(self, model: TelemetryModel) -> None:
        """Fill the electrical table."""
        rows = model.networks[:MAX_ROWS]
        self.power_table.setRowCount(len(rows))
        for index, network in enumerate(rows):
            display = network_display(network)
            values = tuple(display.get(key, "") for key in POWER_KEYS)
            for column, value in enumerate(values):
                self.power_table.setItem(
                    index, column, QTableWidgetItem(value))

    def _fill_candidates(self, model: TelemetryModel) -> None:
        """Fill the bottleneck candidates."""
        rows = model.bottleneck_rows()
        if not rows:
            self.candidates.setPlainText(
                "No telemetry-backed bottleneck candidate was found in the "
                "available samples.")
            return
        lines = []
        for row in rows:
            title = row.get("title", "")
            detail = row.get("detail", "")
            lines.append(f"{title}\n{detail}")
        self.candidates.setPlainText("\n\n".join(lines))

    def stats(self) -> dict[str, Any]:
        """Return the widget's own counters."""
        return {
            "flows": len(self._model.flows),
            "networks": len(self._model.networks),
            "candidates": len(self._model.recommendations),
            "available": self._model.available,
            "charts": len(self.charts),
            "subjects": len(self._subjects()),
            "history": self._history.stats(),
        }


__all__ = [
    "ELECTRICAL_SERIES",
    "FLOW_COLUMNS",
    "POWER_COLUMNS",
    "PRODUCTION_SERIES",
    "ROLE_ELECTRICAL",
    "ROLE_PRODUCTION",
    "TelemetryWidget",
]
