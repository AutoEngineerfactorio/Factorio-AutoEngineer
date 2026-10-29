"""The native Qt charts of the production and electrical workspaces.

The dashboard shows **historical** graphs: how a material's rate moved over
time, how a power network's generation and consumption moved, and how the
electrical satisfaction behaved. This module draws them.

Three properties matter and are enforced here:

* **No fabricated points.** A chart draws only the samples that were really
  observed. A gap in the observation is a gap in the line, never a straight
  line across it and never an interpolated point.
* **Bounded work.** The charts cache their geometry and repaint only when
  the data actually changed, so a fast observation poll does not cost a
  repaint per sample.
* **No heavyweight dependency.** The charts are drawn with the Qt painting
  primitives that PySide6 already provides. There is no plotting library.

The module is split in two halves on purpose:

* :mod:`qt_chart_geometry` computes where every point goes and how the
  axes read. It contains **no Qt import**, so it is verifiable offline.
* :class:`TelemetryChartWidget` paints that geometry with
  :class:`QPainter`.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from qt_chart_geometry import (
    ChartGeometry,
    ChartPoint,
    ChartScale,
    ChartSpec,
    axis_decimals,
    axis_ticks,
    build_geometry,
    format_axis_tick,
    format_axis_time,
    geometry_from_history,
)

try:
    qt_core = import_module("PySide6.QtCore")
    qt_gui = import_module("PySide6.QtGui")
    qt_widgets = import_module("PySide6.QtWidgets")
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise SystemExit(
        "Optional UI requires PySide6: python -m pip install PySide6") from exc

QColor = qt_gui.QColor
QPainter = qt_gui.QPainter
QPen = qt_gui.QPen
QPointF = qt_core.QPointF
QPolygonF = qt_gui.QPolygonF
QRectF = qt_core.QRectF
Qt = qt_core.Qt

QWidget = qt_widgets.QWidget

#: The margins of the plot area, in pixels.
#:
#: The top margin leaves room for the series name, so every chart says
#: which series it shows.
PLOT_MARGIN_LEFT = 62
PLOT_MARGIN_RIGHT = 14
PLOT_MARGIN_TOP = 24
PLOT_MARGIN_BOTTOM = 26

#: The minimum size of the plot area, in pixels.
MIN_PLOT_WIDTH = 120
MIN_PLOT_HEIGHT = 70

#: The number of time labels on the time axis.
TIME_LABELS = 5


class TelemetryChartWidget(QWidget):
    """One drawn chart of an observed series.

    The widget paints from a :class:`ChartSpec`. It caches the drawn
    geometry, so a repaint only recomputes the geometry when the spec
    actually changed.
    """

    def __init__(self, spec: ChartSpec | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self._spec = spec or ChartSpec(key="", title="")
        self._signature = self._spec.signature()
        self._points: tuple[ChartPoint, ...] = ()
        self._scale = ChartScale()
        self._geometry = ChartGeometry(empty=True)
        self._geometry_key: tuple[Any, ...] | None = None
        self._paint_count = 0

    # -- the data --------------------------------------------------------

    @property
    def spec(self) -> ChartSpec:
        """The spec the widget currently draws."""
        return self._spec

    def set_spec(self, spec: ChartSpec) -> bool:
        """Set the spec and repaint only when it actually changed.

        The return value says whether a repaint was scheduled, which is
        what keeps a fast observation poll cheap.
        """
        signature = spec.signature()
        if signature == self._signature:
            return False
        self._spec = spec
        self._signature = signature
        self._invalidate()
        self.update()
        return True

    def _invalidate(self) -> None:
        """Drop the cached geometry."""
        self._points = ()
        self._scale = ChartScale()
        self._geometry = ChartGeometry(empty=True)
        self._geometry_key = None

    # -- the drawing -----------------------------------------------------

    def _plot_rect(self) -> QRectF:
        """Return the rectangle of the plot area."""
        width = max(MIN_PLOT_WIDTH, self.width() - PLOT_MARGIN_LEFT
                    - PLOT_MARGIN_RIGHT)
        height = max(MIN_PLOT_HEIGHT, self.height() - PLOT_MARGIN_TOP
                     - PLOT_MARGIN_BOTTOM)
        return QRectF(PLOT_MARGIN_LEFT, PLOT_MARGIN_TOP, width, height)

    def _compute(self) -> None:
        """Compute the geometry of the current spec.

        The geometry is **cached**: it is only recomputed when the data or
        the size actually changed. A steady observation stream therefore
        costs one polygon build per repaint, not one per sample.
        """
        rect = self._plot_rect()
        key = (self._signature, round(rect.width(), 1),
               round(rect.height(), 1))
        if key == self._geometry_key:
            return
        history = self._spec.as_history_point()
        self._scale, self._points = geometry_from_history(
            history, width=rect.width(), height=rect.height())
        self._geometry = build_geometry(history)
        self._geometry_key = key

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt naming
        """Draw the chart."""
        self._paint_count += 1
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw_background(painter)
            if self._spec.unavailable:
                self._draw_message(painter, "Observation unavailable")
                return
            self._compute()
            if not self._points:
                self._draw_message(painter, "No history observed yet")
                return
            self._draw_grid(painter)
            self._draw_series(painter)
            self._draw_axis(painter)
            self._draw_title(painter)
        finally:
            painter.end()

    def _draw_background(self, painter: QPainter) -> None:
        """Draw the panel behind the plot."""
        painter.fillRect(self.rect(), QColor("#1a232c"))
        painter.setPen(QPen(QColor("#344554"), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _draw_message(self, painter: QPainter, message: str) -> None:
        """Draw the message shown instead of a chart."""
        painter.setPen(QColor("#93a2b1"))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, message)

    def _draw_grid(self, painter: QPainter) -> None:
        """Draw the horizontal grid lines."""
        rect = self._plot_rect()
        painter.setPen(QPen(QColor("#2b3745"), 1))
        for tick in axis_ticks(self._geometry):
            y = rect.top() + self._scale.value_y(tick)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

    def _draw_series(self, painter: QPainter) -> None:
        """Draw the observed line and its last point."""
        rect = self._plot_rect()
        color = QColor(self._spec.color or "#f6b34c")
        if self._spec.stale:
            color = QColor("#93a2b1")
        painter.setPen(QPen(color, 2))
        polygon = QPolygonF()
        for point in self._points:
            polygon.append(QPointF(rect.left() + point.x,
                                   rect.top() + point.y))
        if polygon:
            painter.drawPolyline(polygon)
        if self._points:
            last = self._points[-1]
            painter.setBrush(color)
            painter.drawEllipse(QPointF(rect.left() + last.x,
                                        rect.top() + last.y), 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_axis(self, painter: QPainter) -> None:
        """Draw the value axis and the time axis.

        The value axis shows the grid lines with the precision the step
        between them needs, so the labels never read as a different scale
        than the one that was drawn.
        """
        rect = self._plot_rect()
        painter.setPen(QColor("#6b7a89"))
        ticks = axis_ticks(self._geometry)
        decimals = axis_decimals(ticks)
        for tick in ticks:
            y = rect.top() + self._scale.value_y(tick)
            painter.drawText(QRectF(0, y - 9, PLOT_MARGIN_LEFT - 6, 18),
                             Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter,
                             format_axis_tick(tick, self._spec.unit, decimals))
        span = self._geometry.time_span
        first = self._geometry.first_at or 0.0
        count = min(TIME_LABELS, max(2, len(self._points)))
        for index in range(count):
            ratio = index / (count - 1)
            at = first + ratio * span
            x = rect.left() + ratio * rect.width()
            # The label is the **elapsed** time since the first sample, so
            # the axis does not change when the window slides.
            painter.drawText(QRectF(x - 40, rect.bottom() + 2, 80, 18),
                             Qt.AlignmentFlag.AlignCenter,
                             format_axis_time(at, span, elapsed=at - first))

    def _draw_title(self, painter: QPainter) -> None:
        """Draw the name of the series the chart shows."""
        if not self._spec.title:
            return
        painter.setPen(QColor("#93a2b1"))
        painter.drawText(QRectF(PLOT_MARGIN_LEFT, 0,
                                max(0, self.width() - PLOT_MARGIN_LEFT - 8),
                                PLOT_MARGIN_TOP + 2),
                         Qt.AlignmentFlag.AlignLeft
                         | Qt.AlignmentFlag.AlignVCenter,
                         self._spec.title)

    # -- introspection ----------------------------------------------------

    @property
    def paint_count(self) -> int:
        """How often the widget painted."""
        return self._paint_count

    @property
    def drawn_points(self) -> int:
        """How many observed points the chart drew."""
        return len(self._points)

    def drawn_values(self) -> list[float]:
        """Return the values the chart actually drew."""
        return [point.value for point in self._points]


__all__ = [
    "ChartSpec",
    "TelemetryChartWidget",
]
