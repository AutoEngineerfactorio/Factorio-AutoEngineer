"""The bounded telemetry history behind the production and power charts.

The dashboard shows **historical** graphs: how a material's rate moved over
time, how the power network's generation and consumption moved, and how the
electrical satisfaction behaved. Those graphs need a history, and a history
needs a bound.

This module keeps that history. It **reuses** the verified telemetry model
rather than re-implementing the mathematics:

* :mod:`qt_telemetry` builds the rows and the observed values.
* :mod:`production_telemetry` validates the payload and converts the rates.
* :mod:`qt_theme` supplies the bounded, validated series container.

There is therefore **no second mathematical engine** here. The module only
decides *what to keep* and *for how long*.

Four rules define the history:

* **Bounded.** Every series keeps at most ``maximum_points`` samples, and
  the window can be configured in minutes.
* **Explicit units.** Each series names its unit, and a series is never
  shown in a unit it was not observed in.
* **Honest resets.** A telemetry reset - a tick that went **backwards** -
  clears the history. A chart that joined two different games into one
  line would be a lie.
* **Honest reconnections.** A gap longer than the allowed gap closes the
  history rather than drawing a straight line across it.

The module contains **no Qt import**, so the whole history is verifiable
offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from qt_telemetry import TelemetryModel, build_model
from qt_theme import TelemetrySeries

#: The default number of minutes a chart keeps.
DEFAULT_WINDOW_MINUTES = 15.0

#: The default number of samples one series keeps.
DEFAULT_MAXIMUM_POINTS = 240

#: The longest gap between two samples that is still joined by a line.
#: A longer gap means the observer lost contact, so the history restarts.
DEFAULT_MAXIMUM_GAP_SECONDS = 60.0

#: The series kinds the production charts draw.
FLOW_OUTPUT = "flow-output"
FLOW_INPUT = "flow-input"

#: The series kinds the electrical charts draw.
POWER_GENERATION = "power-generation"
POWER_CONSUMPTION = "power-consumption"
POWER_SATISFACTION = "power-satisfaction"


@dataclass
class HistorySample:
    """One sample of the history, with the moment it was observed.

    The timestamp is explicit, so a chart never has to guess when a point
    was taken.
    """

    at: float
    tick: int | None = None
    value: float = 0.0


@dataclass
class HistoryPoint:
    """One chart's worth of history.

    ``values`` holds the samples in observation order and ``stamps`` holds
    the moment of each sample, so the two always line up.
    """

    name: str
    unit: str
    values: list[float] = field(default_factory=list)
    stamps: list[float] = field(default_factory=list)
    ticks: list[int] = field(default_factory=list)

    @property
    def latest(self) -> float | None:
        """The most recent value, or ``None`` when there is none."""
        return self.values[-1] if self.values else None

    @property
    def latest_at(self) -> float | None:
        """The moment of the most recent value."""
        return self.stamps[-1] if self.stamps else None

    @property
    def empty(self) -> bool:
        """Whether this chart has no data at all."""
        return not self.values

    def span_seconds(self) -> float:
        """The time span the chart covers."""
        if len(self.stamps) < 2:
            return 0.0
        return self.stamps[-1] - self.stamps[0]


def _configured_retention() -> tuple[float, int]:
    """Return the history window in minutes and the point limit.

    Both come from the settings, so the retention is configurable. A
    missing or unusable setting falls back to the protective default, so
    the history is never unbounded.
    """
    try:
        from runtime_settings import history_retention

        points = history_retention()
    except Exception:
        points = DEFAULT_MAXIMUM_POINTS
    if type(points) is not int or points < 1:
        points = DEFAULT_MAXIMUM_POINTS
    return DEFAULT_WINDOW_MINUTES, points


class TelemetryHistory:
    """The bounded history of the production and electrical telemetry.

    The history is fed one validated telemetry payload at a time. It never
    invents a sample: a payload that does not validate is rejected by
    :func:`qt_telemetry.build_model` and contributes nothing.
    """

    def __init__(self, *, window_minutes: float | None = None,
                 maximum_points: int | None = None,
                 maximum_gap_seconds: float = DEFAULT_MAXIMUM_GAP_SECONDS,
                 context: Any = None):
        if window_minutes is None or maximum_points is None:
            configured_window, configured_points = _configured_retention()
            if window_minutes is None:
                window_minutes = configured_window
            if maximum_points is None:
                maximum_points = configured_points
        window = float(window_minutes)
        points = int(maximum_points)
        if window <= 0:
            raise ValueError("The history window must be positive")
        if points < 1:
            raise ValueError("The history must keep at least one point")
        if maximum_gap_seconds <= 0:
            raise ValueError("The maximum gap must be positive")
        self.window_minutes = window
        self.maximum_points = points
        self.maximum_gap_seconds = float(maximum_gap_seconds)
        #: The cache context the history describes. A payload from another
        #: profile or another mod configuration never joins this history.
        self._context = context
        self._series: dict[str, TelemetrySeries] = {}
        self._stamps: dict[str, list[float]] = {}
        self._ticks: dict[str, list[int]] = {}
        self._last_tick: int | None = None
        self._last_at: float | None = None
        #: The surface the current history describes.
        #:
        #: An empty string means "the surface was not reported", which is
        #: different from "the surface is nauvis". A payload without a
        #: surface therefore never triggers a surface reset.
        self._last_surface: str = ""
        self.resets = 0
        self.rejections = 0

    # -- configuration ---------------------------------------------------

    @property
    def context(self) -> Any:
        """The cache context the history describes."""
        return self._context

    def set_context(self, context: Any) -> bool:
        """Adopt a new cache context.

        The samples belong to the previous context, so they are dropped.
        The method reports whether anything was dropped.
        """
        if self._context is not None and context is not None:
            if getattr(self._context, "key", None) == getattr(context, "key", None):
                return False
        self._context = context
        self.clear()
        return True

    def set_window(self, window_minutes: float) -> None:
        """Change how many minutes of history are kept."""
        if window_minutes <= 0:
            raise ValueError("The history window must be positive")
        self.window_minutes = float(window_minutes)

    # -- the series ------------------------------------------------------

    def _series_for(self, key: str, name: str, unit: str) -> TelemetrySeries:
        """Return the bounded series for one key, creating it if needed."""
        series = self._series.get(key)
        if series is None:
            series = TelemetrySeries(
                name=name, unit=unit, maximum_points=self.maximum_points)
            self._series[key] = series
            self._stamps[key] = []
            self._ticks[key] = []
        return series

    def _append(self, key: str, name: str, unit: str, value: float,
                at: float, tick: int | None) -> None:
        """Append one sample to one series, honouring the window."""
        series = self._series_for(key, name, unit)
        try:
            series.append(value)
        except ValueError:
            # A value that is not a finite number is never charted.
            return
        self._stamps[key].append(at)
        self._ticks[key].append(tick if tick is not None else -1)
        self._trim(key, at)

    def _trim(self, key: str, now: float) -> None:
        """Drop the samples that fell out of the window or the bound."""
        series = self._series.get(key)
        if series is None:
            return
        stamps = self._stamps.get(key, [])
        ticks = self._ticks.get(key, [])
        limit = now - self.window_minutes * 60.0
        while len(series.points) > self.maximum_points:
            series.points.pop(0)
            if stamps:
                stamps.pop(0)
            if ticks:
                ticks.pop(0)
        while len(series.points) > 1 and stamps and stamps[0] < limit:
            series.points.pop(0)
            stamps.pop(0)
            if ticks:
                ticks.pop(0)

    # -- feeding ---------------------------------------------------------

    def observe(self, telemetry: Mapping[str, Any] | None, *,
                at: float, tick: int | None = None) -> TelemetryModel:
        """Record one observed telemetry payload in the history.

        The payload is validated by the existing telemetry model. A payload
        that does not validate contributes nothing and is counted as a
        rejection.

        A payload whose tick went **backwards** is a telemetry reset: the
        history is cleared, because joining two different games into one
        line would misrepresent what happened.

        A payload from a **different surface** is a reset too. The game
        tick keeps rising when the player changes surface, so the tick
        alone cannot detect the change. Joining the production rates of
        two surfaces into one line would claim a continuity that was
        never observed, so the history restarts instead.
        """
        model = build_model(telemetry, tick=tick)
        if not model.available:
            self.rejections += 1
            return model
        if (model.surface and self._last_surface
                and model.surface != self._last_surface):
            # The player changed surface. The new surface's rates are not
            # a continuation of the old surface's rates.
            self.clear()
            self.resets += 1
        if model.tick is not None and self._last_tick is not None:
            if model.tick < self._last_tick:
                # The game restarted or the save was reloaded. The old
                # history no longer describes what is happening.
                self.clear()
                self.resets += 1
        if (self._last_at is not None
                and at - self._last_at > self.maximum_gap_seconds):
            # The observer lost contact for too long. The line across the
            # gap would claim a continuity that was not observed.
            self.clear()
        self._last_tick = model.tick if model.tick is not None else self._last_tick
        self._last_at = at
        if model.surface:
            self._last_surface = model.surface
        self._record(model, at)
        return model

    def _record(self, model: TelemetryModel, at: float) -> None:
        """Record the rows of one validated model."""
        tick = model.tick
        for row in model.flows:
            key = f"{FLOW_OUTPUT}:{row.name}"
            self._append(key, f"{row.name} output", "units/min",
                         row.output_per_minute, at, tick)
            key = f"{FLOW_INPUT}:{row.name}"
            self._append(key, f"{row.name} input", "units/min",
                         row.input_per_minute, at, tick)
        for network in model.networks:
            prefix = f"network-{network.network_id}"
            self._append(f"{POWER_GENERATION}:{prefix}",
                         f"Network {network.network_id} generation", "W",
                         network.generation_watts, at, tick)
            self._append(f"{POWER_CONSUMPTION}:{prefix}",
                         f"Network {network.network_id} consumption", "W",
                         network.consumption_watts, at, tick)
            self._append(f"{POWER_SATISFACTION}:{prefix}",
                         f"Network {network.network_id} satisfaction", "ratio",
                         network.consumption_satisfaction, at, tick)

    # -- reading ---------------------------------------------------------

    def chart(self, key: str) -> HistoryPoint:
        """Return one chart's history."""
        series = self._series.get(key)
        if series is None:
            return HistoryPoint(name=key, unit="")
        return HistoryPoint(
            name=series.name, unit=series.unit,
            values=list(series.points),
            stamps=list(self._stamps.get(key, [])),
            ticks=list(self._ticks.get(key, [])),
        )

    def charts(self, prefix: str) -> list[HistoryPoint]:
        """Return every chart whose key starts with ``prefix``."""
        return [self.chart(key) for key in sorted(self._series)
                if key.startswith(prefix)]

    @property
    def production_charts(self) -> list[HistoryPoint]:
        """The production charts, output first then input."""
        return self.charts(f"{FLOW_OUTPUT}:") + self.charts(f"{FLOW_INPUT}:")

    @property
    def electrical_charts(self) -> list[HistoryPoint]:
        """The electrical charts."""
        return (self.charts(f"{POWER_GENERATION}:")
                + self.charts(f"{POWER_CONSUMPTION}:")
                + self.charts(f"{POWER_SATISFACTION}:"))

    def series_keys(self) -> tuple[str, ...]:
        """The keys of every series the history holds."""
        return tuple(sorted(self._series))

    # -- maintenance -----------------------------------------------------

    def clear(self) -> None:
        """Drop every sample and forget the last observation."""
        self._series.clear()
        self._stamps.clear()
        self._ticks.clear()
        self._last_tick = None
        self._last_at = None
        self._last_surface = ""

    def stats(self) -> dict[str, Any]:
        """Return a bounded summary of the history."""
        return {
            "series": len(self._series),
            "points": sum(len(s.points) for s in self._series.values()),
            "window_minutes": self.window_minutes,
            "maximum_points": self.maximum_points,
            "resets": self.resets,
            "rejections": self.rejections,
        }


__all__ = [
    "DEFAULT_MAXIMUM_GAP_SECONDS",
    "DEFAULT_MAXIMUM_POINTS",
    "DEFAULT_WINDOW_MINUTES",
    "FLOW_INPUT",
    "FLOW_OUTPUT",
    "POWER_CONSUMPTION",
    "POWER_GENERATION",
    "POWER_SATISFACTION",
    "HistoryPoint",
    "HistorySample",
    "TelemetryHistory",
]
