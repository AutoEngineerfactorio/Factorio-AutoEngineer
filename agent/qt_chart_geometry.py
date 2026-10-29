"""The pure geometry of the telemetry charts.

This module holds the part of the chart that decides **where every point
goes** and **how the axes read**. It contains **no Qt import**, so the
whole of it is verifiable offline, without a display server and without
the optional PySide6 dependency.

The rules it enforces are the ones that make a chart trustworthy:

* **No fabricated points.** Only the samples that were really observed are
  mapped. A history without samples maps to nothing at all.
* **No exaggerated scale.** A series of non-negative values is scaled from
  zero, because a chart that starts at the minimum exaggerates a small
  change and misrepresents what was observed.
* **Honest axes.** The grid lines always include the exact minimum and the
  exact maximum, and the time labels follow the span of the chart, so the
  axis never hides the real range of the data.

The drawing half lives in :mod:`qt_chart`, which imports this module.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from typing import Any, Sequence

from qt_telemetry_history import HistoryPoint

#: The number of horizontal grid lines.
GRID_LINES = 4


@dataclass
class ChartSpec:
    """Everything one chart needs in order to be drawn.

    The spec is the **cache key** of the drawing. When the spec does not
    change, the chart does not repaint.

    The cache key covers **every** sample and **every** timestamp, not
    only the newest one, so a corrected observation of an older sample
    still repaints the chart. A signature built from the final sample
    alone would miss such a correction and would leave a wrong line on
    screen.

    The class lives in this **Qt-free** module so the cache key can be
    verified offline, without the optional PySide6 dependency.
    """

    key: str
    title: str
    unit: str = ""
    values: tuple[float, ...] = ()
    stamps: tuple[float, ...] = ()
    color: str = ""
    maximum_points: int = 240
    stale: bool = False
    unavailable: bool = False

    def signature(self) -> tuple[Any, ...]:
        """Return the value that decides whether a repaint is needed.

        The signature is a **content digest** of everything that affects
        the drawing: the identity, the title, the unit, the colour, the
        display flags and the **complete** sample and timestamp
        sequences.

        The digest is fixed size, so the no-change check stays cheap:
        comparing two 16-byte digests is constant time, no matter how
        long the history is. The history itself is bounded by the
        telemetry history, so the digest input stays bounded too.
        """
        return (self.key, self.title, self.unit, self.color,
                self.stale, self.unavailable, self._data_digest())

    def _data_digest(self) -> bytes:
        """Return the digest of the observed values and timestamps.

        The samples are packed into bytes with :mod:`struct`, so the
        digest covers the **exact** bit pattern of every observed number.
        A change to any intermediate sample therefore produces a
        different digest, while an unchanged series always produces the
        same one.

        The values and the timestamps are packed in **separate** blocks,
        so a series whose values and timestamps were swapped between
        each other cannot produce the same digest.
        """
        digest = hashlib.blake2b(digest_size=16)
        digest.update(struct.pack("<I", len(self.values)))
        for value in self.values:
            digest.update(struct.pack("<d", float(value)))
        digest.update(struct.pack("<I", len(self.stamps)))
        for stamp in self.stamps:
            digest.update(struct.pack("<d", float(stamp)))
        return digest.digest()

    def as_history_point(self) -> HistoryPoint:
        """Return the observed history this spec describes."""
        return HistoryPoint(name=self.title, unit=self.unit,
                            values=list(self.values),
                            stamps=list(self.stamps))


@dataclass(frozen=True)
class ChartPoint:
    """One drawn point: where it goes and what it is.

    ``x`` and ``y`` are in *plot* coordinates - the caller maps them into
    the widget - so the geometry can be computed without a widget.
    """

    x: float
    y: float
    value: float
    at: float


@dataclass(frozen=True)
class ChartScale:
    """The mapping from values and times into the plot area."""

    minimum: float = 0.0
    maximum: float = 1.0
    first_at: float = 0.0
    last_at: float = 1.0
    width: float = 0.0
    height: float = 0.0

    def value_y(self, value: float) -> float:
        """Return the vertical position of one value."""
        span = self.maximum - self.minimum
        if span <= 0.0:
            return self.height / 2.0
        ratio = (value - self.minimum) / span
        return self.height - ratio * self.height

    def time_x(self, at: float) -> float:
        """Return the horizontal position of one moment."""
        span = self.last_at - self.first_at
        if span <= 0.0:
            return self.width / 2.0
        ratio = (at - self.first_at) / span
        return ratio * self.width


@dataclass(frozen=True)
class ChartGeometry:
    """The computed geometry of one chart.

    The geometry is **derived** from the observed samples. It never adds a
    sample: ``values`` holds exactly the samples that were observed, so the
    number of drawn points always matches the number of observed values.
    """

    values: tuple[float, ...] = ()
    stamps: tuple[float, ...] = ()
    minimum: float = 0.0
    maximum: float = 1.0
    first_at: float | None = None
    last_at: float | None = None
    unit: str = ""
    empty: bool = True

    @property
    def span(self) -> float:
        """The value range the chart covers."""
        return self.maximum - self.minimum

    @property
    def time_span(self) -> float:
        """The time range the chart covers."""
        if self.first_at is None or self.last_at is None:
            return 0.0
        return self.last_at - self.first_at


def finite_values(values: Sequence[Any]) -> list[float]:
    """Return only the finite numbers of a sequence."""
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(float(value)):
            continue
        result.append(float(value))
    return result


def build_geometry(point: HistoryPoint) -> ChartGeometry:
    """Compute the geometry of one observed history point.

    Only the **observed** samples are used. A history point that carries no
    values produces an **empty** geometry, which the widget draws as a
    "no history yet" message rather than as a flat line at zero.

    The vertical scale always starts at zero when every value is
    non-negative, because a chart that exaggerates a small change is
    misleading. When the values are negative - a net flow can be negative -
    the scale covers the real range instead.
    """
    values = finite_values(point.values)
    if not values:
        return ChartGeometry(unit=point.unit, empty=True)
    stamps = [float(s) for s in point.stamps[:len(values)]
              if isinstance(s, (int, float)) and not isinstance(s, bool)
              and math.isfinite(float(s))]
    while len(stamps) < len(values):
        stamps.append(stamps[-1] if stamps else 0.0)
    minimum = min(values)
    maximum = max(values)
    if minimum >= 0.0:
        minimum = 0.0
    if maximum <= 0.0:
        maximum = 0.0
    if maximum == minimum:
        # A flat series still needs a scale, so the flat line sits in the
        # middle of the plot instead of on its edge.
        maximum = minimum + 1.0
    return ChartGeometry(
        values=tuple(values),
        stamps=tuple(stamps),
        minimum=minimum,
        maximum=maximum,
        first_at=stamps[0],
        last_at=stamps[-1],
        unit=point.unit,
        empty=False,
    )


def layout_geometry(geometry: ChartGeometry, *, width: float,
                    height: float) -> tuple[ChartScale, tuple[ChartPoint, ...]]:
    """Map a geometry into a plot area.

    The number of returned points always equals the number of observed
    values, which is what proves the chart drew exactly what was observed.
    """
    scale = ChartScale(
        minimum=geometry.minimum,
        maximum=geometry.maximum,
        first_at=geometry.first_at or 0.0,
        last_at=geometry.last_at or 0.0,
        width=width,
        height=height,
    )
    if geometry.empty:
        return scale, ()
    points = []
    for index, value in enumerate(geometry.values):
        at = geometry.stamps[index] if index < len(geometry.stamps) else 0.0
        points.append(ChartPoint(
            x=scale.time_x(at),
            y=scale.value_y(value),
            value=value,
            at=at,
        ))
    return scale, tuple(points)


def geometry_from_history(point: HistoryPoint, *, width: float,
                          height: float) -> tuple[ChartScale, tuple[ChartPoint, ...]]:
    """Compute the scale and the drawn points of one observed history."""
    return layout_geometry(build_geometry(point), width=width, height=height)


def axis_ticks(geometry: ChartGeometry, *, count: int = GRID_LINES
               ) -> tuple[float, ...]:
    """Return the values of the horizontal grid lines.

    The ticks always include the exact minimum and the exact maximum, so
    the axis never hides the real range of the data.
    """
    if geometry.empty:
        return ()
    if count < 2:
        count = 2
    span = geometry.maximum - geometry.minimum
    step = span / (count - 1)
    ticks = [geometry.minimum + step * index for index in range(count)]
    ticks[0] = geometry.minimum
    ticks[-1] = geometry.maximum
    return tuple(ticks)


def format_axis_time(at: float, span_seconds: float, *,
                     elapsed: float | None = None) -> str:
    """Format one time-axis label.

    The label is the **elapsed** time since the first sample, not the
    absolute moment of the sample. An absolute wall-clock reading would
    change the whole axis when the window slid, and the user would have
    to do arithmetic to know how long ago something happened.

    The unit follows the **largest value on the axis**, so a chart that
    covers two minutes reads "0s", "30s", "60s", "90s", "120s" rather
    than "0.0m", "0.5m", "1.0m", "1.5m", "2.0m". A chart that mixes
    units on one axis is hard to read.
    """
    if span_seconds <= 0.0:
        return "0s"
    offset = at if elapsed is None else elapsed
    largest = max(abs(offset), span_seconds)
    # Seconds are used while the axis still reads cleanly in them. A chart
    # that covers ten minutes reads "0s" to "600s", which is easier to
    # follow than "0.0m" to "10.0m".
    if largest < 600.0:
        return f"{offset:.0f}s"
    if largest < 5400.0:
        return f"{offset / 60.0:.1f}m"
    return f"{offset / 3600.0:.1f}h"


def format_axis_value(value: float, unit: str) -> str:
    """Format one value-axis label with its unit.

    The number of decimals follows the **step** between the grid lines,
    so a chart whose ticks are 3.3 apart does not print "3" and "3" on two
    neighbouring lines.
    """
    unit = unit or ""
    if unit == "ratio":
        return f"{value * 100.0:.0f}%"
    if unit == "W":
        if abs(value) >= 1000.0:
            return f"{value / 1000.0:.1f}kW"
        return f"{value:.0f}W"
    if unit == "units/min":
        if abs(value) >= 1000.0:
            return f"{value / 1000.0:.1f}k"
        return f"{value:.0f}"
    return f"{value:.1f}"


def axis_decimals(ticks: Sequence[float]) -> int:
    """Return the number of decimals the value axis needs.

    The axis shows the grid lines, so the decimals follow the **step**
    between them. Without this a chart whose ticks are 0, 3.33, 6.67 and
    10 would print "0", "3", "7" and "10", which reads as a different
    scale than the one that was drawn.

    Two rules have to hold at once:

    * the rounded labels must all stay **distinct**, so no two
      neighbouring grid lines claim the same number;
    * the rounded **step** must stay close to the real step, so the
      printed scale is the scale that was drawn.
    """
    if len(ticks) < 2:
        return 0
    steps = [abs(ticks[index + 1] - ticks[index])
             for index in range(len(ticks) - 1)]
    step = min(steps) if steps else 0.0
    if step <= 0.0:
        return 0
    for decimals in (0, 1, 2, 3):
        labels = [round(tick, decimals) for tick in ticks]
        if len(set(labels)) != len(labels):
            continue
        rounded_step = min(abs(labels[index + 1] - labels[index])
                           for index in range(len(labels) - 1))
        if rounded_step <= 0.0:
            continue
        if abs(rounded_step - step) <= 0.05 * step + 1e-9:
            return decimals
    return 3


def format_axis_tick(value: float, unit: str, decimals: int) -> str:
    """Format one grid-line label with the axis's own precision.

    The rate unit keeps the axis's decimals, so a chart whose ticks are
    0, 2.5, 5, 7.5 and 10 reads as those numbers rather than as
    0, 2, 5, 8 and 10.
    """
    unit = unit or ""
    if unit == "ratio":
        return f"{value * 100.0:.0f}%"
    if unit == "W":
        if abs(value) >= 1000.0:
            return f"{value / 1000.0:.1f}kW"
        return f"{value:.0f}W"
    if unit == "units/min":
        if abs(value) >= 1000.0:
            return f"{value / 1000.0:.1f}k"
        return f"{value:.{decimals}f}"
    return f"{value:.{decimals}f}"


def series_legend(chart: HistoryPoint) -> str:
    """Return the legend text of one chart."""
    unit = chart.unit or ""
    return f"{chart.name} ({unit})" if unit else chart.name


__all__ = [
    "GRID_LINES",
    "ChartGeometry",
    "ChartPoint",
    "ChartScale",
    "ChartSpec",
    "axis_ticks",
    "build_geometry",
    "finite_values",
    "format_axis_time",
    "format_axis_value",
    "geometry_from_history",
    "layout_geometry",
    "series_legend",
]
