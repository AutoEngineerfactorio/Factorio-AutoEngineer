"""The telemetry workspace model: production, power, freshness, bottlenecks.

This module turns one observed telemetry payload into the rows, the
series and the indicators the production and electrical workspaces show.
It is deliberately free of any Qt import, so the truthfulness rules are
verifiable offline.

It **reuses** the validated telemetry model rather than re-implementing
it:

* :mod:`production_telemetry` validates the payload, converts the flow
  rates and formats the power.
* :mod:`qt_observation` supplies the observed / estimated / unavailable
  states.

The rules this module adds:

* A rate in **units per second** is *derived* from the observed
  per-minute flow, so it is an **estimate** and is labelled as one.
* A missing telemetry payload is **unavailable**, never zero.
* A bounded history keeps the charts bounded.
* A bottleneck is a **candidate**, not a verdict: the game's own flow
  statistics show an imbalance, and the model says so in those words.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from production_telemetry import (
    convert_flow_rate,
    format_energy,
    format_power,
    power_rate_display,
    telemetry_view_model,
    validate_telemetry,
)
from qt_observation import Observation, estimated, observed, unavailable

#: How many samples one chart series keeps.
MAX_SERIES_POINTS = 240

#: The severity levels a bottleneck candidate can carry.
SEVERITIES = ("high", "candidate", "info")

#: The label of each severity.
SEVERITY_LABELS = {
    "high": "Likely constraint",
    "candidate": "Possible constraint",
    "info": "No candidate found",
}


@dataclass(frozen=True)
class FlowRow:
    """One observed material flow.

    ``input`` and ``output`` are the observed per-minute rates. The
    per-second figures are derived from them and are therefore estimates.
    """

    name: str
    kind: str
    input_per_minute: float
    output_per_minute: float
    input_per_second: float
    output_per_second: float
    partial: bool = False

    @property
    def net_per_minute(self) -> float:
        """The observed output minus the observed input, per minute."""
        return self.output_per_minute - self.input_per_minute

    @property
    def imbalanced(self) -> bool:
        """Whether the flow shows a supply gap worth reporting."""
        return self.output_per_minute > self.input_per_minute * 1.2 + 0.5


@dataclass(frozen=True)
class PowerRow:
    """One observed electrical network."""

    network_id: int
    generation_watts: float
    consumption_watts: float
    consumption_satisfaction: float
    production_satisfaction: float
    accumulator_energy: float
    accumulator_capacity: float
    partial: bool = False

    @property
    def satisfied(self) -> bool:
        """Whether the network is keeping up with its load."""
        return self.consumption_satisfaction >= 0.99

    @property
    def delivered_generation_watts(self) -> float:
        """Available production multiplied by the fraction actually used."""
        return self.generation_watts * self.production_satisfaction

    @property
    def delivered_consumption_watts(self) -> float:
        """Required consumption multiplied by the fraction actually supplied."""
        return self.consumption_watts * self.consumption_satisfaction

    @property
    def headroom_watts(self) -> float:
        """The observed generation minus the observed consumption."""
        return self.generation_watts - self.consumption_watts


@dataclass
class TelemetryModel:
    """Everything the production and electrical workspaces show."""

    status: str = "unavailable"
    status_text: str = "Production and power telemetry unavailable"
    tick: int | None = None
    production_status: str = "unavailable"
    power_status: str = "unavailable"
    partial: bool = False
    flows: list[FlowRow] = field(default_factory=list)
    networks: list[PowerRow] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    #: The Factorio surface the observation came from.
    #:
    #: The surface is a **sibling** of the validated envelope, because
    #: :func:`production_telemetry.validate_telemetry` accepts an envelope
    #: of exactly four keys. The mod reports it next to the envelope, and
    #: it is read here without widening that contract.
    surface: str = ""
    research_active: bool | None = None
    research_name: str | None = None
    research_progress: float | None = None
    pollution_amount: float | None = None

    @property
    def available(self) -> bool:
        """Whether any telemetry was observed at all."""
        return self.status != "unavailable"

    def total_input_per_minute(self) -> float:
        """The observed total input rate, per minute."""
        return sum(row.input_per_minute for row in self.flows)

    def total_output_per_minute(self) -> float:
        """The observed total output rate, per minute."""
        return sum(row.output_per_minute for row in self.flows)

    def worst_satisfaction(self) -> float | None:
        """The lowest observed consumption satisfaction, or None."""
        if not self.networks:
            return None
        return min(row.consumption_satisfaction for row in self.networks)

    def bottleneck_rows(self) -> list[dict[str, Any]]:
        """The bottleneck candidates, most severe first."""
        return sorted(
            self.recommendations,
            key=lambda item: (0 if item.get("severity") == "high" else 1,
                              item.get("title", "")),
        )

    def freshness(self, age_seconds: float | None) -> Observation:
        """Return the freshness of this observation."""
        if not self.available:
            return unavailable("No telemetry observation yet")
        if age_seconds is None:
            return observed(self.status_text, "Telemetry observed",
                            source="telemetry")
        if age_seconds < 0:
            return unavailable("Invalid telemetry age")
        if age_seconds > 30.0:
            return unavailable(
                f"Telemetry is {age_seconds:.0f}s old", source="telemetry")
        return observed(self.status_text, "Telemetry observed",
                        source="telemetry")


def _number(value: Any) -> float | None:
    """Return a finite float, or ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _flow_rows(series: Sequence[Mapping[str, Any]], kind: str,
               partial: bool) -> list[FlowRow]:
    """Turn the observed flow series into the rows the table shows."""
    rows: list[FlowRow] = []
    for entry in series or []:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        inputs = entry.get("input")
        outputs = entry.get("output")
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            continue
        if not inputs or not outputs:
            continue
        input_rate = _number(inputs[-1])
        output_rate = _number(outputs[-1])
        if input_rate is None or output_rate is None:
            continue
        try:
            input_per_second = convert_flow_rate(input_rate, "second")
            output_per_second = convert_flow_rate(output_rate, "second")
        except ValueError:
            continue
        rows.append(FlowRow(
            name=name, kind=kind,
            input_per_minute=input_rate,
            output_per_minute=output_rate,
            input_per_second=input_per_second,
            output_per_second=output_per_second,
            partial=partial,
        ))
    return rows


def _power_rows(networks: Sequence[Mapping[str, Any]],
                partial: bool) -> list[PowerRow]:
    """Turn the observed electrical networks into the rows the table shows."""
    rows: list[PowerRow] = []
    for network in networks or []:
        if not isinstance(network, Mapping):
            continue
        network_id = network.get("network_id")
        if not isinstance(network_id, int):
            continue
        values = {}
        for field_name in ("maximum_production", "maximum_consumption",
                           "consumption_satisfaction", "production_satisfaction",
                           "accumulator_energy", "accumulator_capacity"):
            value = _number(network.get(field_name))
            if value is None:
                values = {}
                break
            values[field_name] = value
        if not values:
            continue
        rows.append(PowerRow(
            network_id=network_id,
            generation_watts=values["maximum_production"] * 60.0,
            consumption_watts=values["maximum_consumption"] * 60.0,
            consumption_satisfaction=values["consumption_satisfaction"],
            production_satisfaction=values["production_satisfaction"],
            accumulator_energy=values["accumulator_energy"],
            accumulator_capacity=values["accumulator_capacity"],
            partial=partial,
        ))
    return rows


def payload_surface(telemetry: Mapping[str, Any] | None) -> str:
    """Return the Factorio surface an observed payload came from.

    The surface is a **sibling** of the validated envelope: the mod
    reports it next to the envelope, and the envelope validator accepts
    exactly four keys. The surface is therefore read here, from the
    payload, and it is validated on its own terms.

    A payload without a usable surface yields an **empty** string. The
    empty string means "the surface was not reported", which is not the
    same as "the surface is nauvis", so it never triggers a reset.
    """
    if not isinstance(telemetry, Mapping):
        return ""
    surface = telemetry.get("surface")
    if isinstance(surface, str) and 1 <= len(surface) <= 128:
        return surface
    return ""


def envelope_of(telemetry: Mapping[str, Any] | None) -> Any:
    """Return the validated envelope of one observed payload.

    The envelope validator accepts **exactly** four keys, so the surface
    - which the mod reports next to the envelope - has to be taken off
    before the envelope is validated.

    Nothing else is removed and nothing is added. A payload that was not
    a mapping is returned unchanged, so the validator rejects it with
    its own reason rather than with a misleading one.
    """
    if not isinstance(telemetry, Mapping):
        return telemetry
    if "surface" not in telemetry:
        return telemetry
    return {key: value for key, value in telemetry.items() if key != "surface"}


def is_live_contract(telemetry: Mapping[str, Any] | None) -> bool:
    """Whether a payload is the **live** mod-command telemetry.

    The R09 work moved the observation onto the registered mod command
    ``/autoengineer-observe``, and that command reports its own shape: a
    ``protocol`` version, a flow **list** per group and the
    ``one_minute`` / ``five_seconds`` rate windows.

    The legacy shape, which the shared validator accepts, carries a
    ``schema`` version and a flow **group** with a ``series`` array. The
    two are told apart by the version key, so the dashboard can accept
    the live document without weakening the legacy contract.
    """
    if not isinstance(telemetry, Mapping):
        return False
    return "protocol" in telemetry and "schema" not in telemetry


def _live_flow_rows(groups: Any, kind: str,
                    partial: bool) -> list[FlowRow]:
    """Return the flow rows of one live mod-command flow group.

    The live group is a **list** of entries. Each entry names the
    material and carries the two rate windows Factorio keeps.

    The one-minute window is the observed **per-minute** rate, and the
    five-second window is the observed per-five-seconds count. The
    per-second figure is derived, so it is an estimate.
    """
    rows: list[FlowRow] = []
    if not isinstance(groups, list):
        return rows
    for entry in groups:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        minute = entry.get("one_minute")
        if not isinstance(minute, Mapping):
            continue
        produced = minute.get("produced")
        consumed = minute.get("consumed")
        output_per_minute = _number(produced)
        input_per_minute = _number(consumed)
        # Missing, malformed or nonfinite rates are UNKNOWN, not zero.
        if (output_per_minute is None or input_per_minute is None
                or not 0 <= output_per_minute <= 1e12
                or not 0 <= input_per_minute <= 1e12):
            continue
        rows.append(FlowRow(
            name=name,
            kind=kind,
            input_per_minute=input_per_minute,
            output_per_minute=output_per_minute,
            input_per_second=input_per_minute / 60.0,
            output_per_second=output_per_minute / 60.0,
            partial=partial,
        ))
    return rows


def _live_power_rows(power: Mapping[str, Any], tick: int) -> list[PowerRow]:
    """Validate actual mod-command electric network samples before display."""
    if power.get("status") == "unavailable":
        return []
    rows = power.get("networks")
    if (power.get("status") != "ok" or power.get("unit") != "joules_per_tick"
            or type(power.get("tick")) is not int or power["tick"] != tick
            or type(power.get("partial")) is not bool
            or not isinstance(rows, list) or not 1 <= len(rows) <= 4):
        raise ValueError("Invalid live electrical envelope")
    fields = ("maximum_production", "maximum_consumption",
              "consumption_satisfaction", "production_satisfaction",
              "accumulator_energy", "accumulator_capacity")
    seen: set[int] = set()
    for row in rows:
        if (not isinstance(row, Mapping)
                or set(row) != {"network_id", "tick", *fields}
                or type(row.get("network_id")) is not int
                or row["network_id"] < 0 or row["network_id"] in seen
                or type(row.get("tick")) is not int or row["tick"] != tick):
            raise ValueError("Invalid live electrical network identifier")
        seen.add(row["network_id"])
        for metric_name in fields:
            value = _number(row.get(metric_name))
            if (value is None or not 0 <= value <= 1e18
                    or (metric_name.endswith("satisfaction") and value > 1)):
                raise ValueError("Invalid live electrical measurement")
    return _power_rows(rows, power["partial"])


def live_model(telemetry: Mapping[str, Any]) -> TelemetryModel:
    """Build the telemetry model from a **live** mod-command document.

    The live document is the achievement-safe observation: it travels
    over the registered mod command, so it carries its own protocol
    version and its own rate windows.

    Nothing is invented. A value that the game did not report stays
    unknown, and a partial coverage is reported as partial.
    """
    tick = telemetry.get("tick")
    if (type(telemetry.get("protocol")) is not int
            or telemetry["protocol"] != 1
            or type(tick) is not int or tick < 0):
        return TelemetryModel(reason="Unsupported live observation version or tick")
    production = telemetry.get("production")
    power = telemetry.get("power")
    if not isinstance(production, Mapping):
        production = {}
    if not isinstance(power, Mapping):
        power = {}

    status = telemetry.get("status")
    if status not in ("ok", "unavailable"):
        return TelemetryModel(reason="Invalid live observation status")
    production_status = str(production.get("status") or "unavailable")
    partial = bool(production.get("partial")) or bool(power.get("partial"))

    model = TelemetryModel(
        status="ok" if status == "ok" else "unavailable",
        status_text=("Production and power telemetry unavailable"
                     if status != "ok" else ""),
        tick=tick if isinstance(tick, int) else None,
        production_status=production_status,
        power_status=str(power.get("status") or "unavailable"),
        partial=partial,
        surface=payload_surface(telemetry),
    )
    if status != "ok":
        reason = telemetry.get("reason")
        model.reason = (str(reason) if isinstance(reason, str)
                        else "No telemetry payload was observed")
        return model

    research = telemetry.get("research")
    if isinstance(research, Mapping) and research.get("status") == "ok":
        if research.get("active") is False:
            model.research_active = False
        elif research.get("active") is True:
            name, progress = research.get("name"), _number(research.get("progress"))
            if isinstance(name, str) and 0 < len(name) <= 128 and progress is not None and 0 <= progress <= 1:
                model.research_active, model.research_name, model.research_progress = True, name, progress
    pollution = telemetry.get("pollution")
    if (isinstance(pollution, Mapping) and pollution.get("status") == "ok"
            and pollution.get("coverage") == "character_chunk"):
        amount = _number(pollution.get("amount"))
        if amount is not None and 0 <= amount <= 1e18:
            model.pollution_amount = amount

    model.flows = (
        _live_flow_rows(production.get("items"), "item", partial)
        + _live_flow_rows(production.get("fluids"), "fluid", partial)
    )

    power_reason = power.get("reason")
    if isinstance(power_reason, str):
        model.reason = power_reason
    try:
        model.networks = _live_power_rows(power, tick)
    except ValueError as exc:
        # Corrupt or mismatched power data is unknown, never zero watts.
        model.power_status = "unavailable"
        model.reason = str(exc)
    return model


def build_model(telemetry: Mapping[str, Any] | None, *,
                tick: int | None = None) -> TelemetryModel:
    """Build the telemetry model from one observed payload.

    A payload that does not validate becomes an **unavailable** model
    with the reason attached. It never becomes a model of zeroes.

    The payload carries its own tick, and the validator insists that the
    telemetry matches it. The tick argument is therefore only a **cross
    check**: when the caller knows the tick the observation arrived with,
    a payload that disagrees is rejected instead of being accepted under
    the payload's own claim.
    """
    if telemetry is None:
        return TelemetryModel(reason="No telemetry payload was observed")
    surface = payload_surface(telemetry)
    if is_live_contract(telemetry):
        # Live registered-command payloads are versioned and independently
        # validated; reject a mismatched game tick rather than mixing saves.
        if tick is not None and telemetry.get("tick") != tick:
            return TelemetryModel(reason="Live telemetry tick disagrees with frame")
        model = live_model(telemetry)
        if not model.surface:
            model.surface = surface
        return model
    payload_tick = telemetry.get("tick") if isinstance(telemetry, Mapping) else None
    if tick is not None and isinstance(payload_tick, int) and payload_tick != tick:
        return TelemetryModel(
            reason=(f"Telemetry is for tick {payload_tick}, not tick {tick}"),
            surface=surface)
    if not isinstance(payload_tick, int):
        return TelemetryModel(reason="Telemetry payload has no valid tick",
                              surface=surface)
    try:
        validated = validate_telemetry(envelope_of(telemetry), payload_tick)
    except ValueError as exc:
        return TelemetryModel(reason=f"Telemetry payload rejected: {exc}",
                              surface=surface)
    view = telemetry_view_model(validated)
    production = validated["production"]
    power = validated["power"]

    items = production["items"]
    fluids = production["fluids"]
    item_series = items.get("series", []) if isinstance(items, Mapping) else []
    fluid_series = fluids.get("series", []) if isinstance(fluids, Mapping) else []

    model = TelemetryModel(
        status=view.get("status", "ok"),
        status_text=view.get("status_text", ""),
        tick=validated.get("tick"),
        production_status=view.get("production_status", "unavailable"),
        power_status=view.get("power_status", "unavailable"),
        partial=bool(view.get("partial")),
        recommendations=list(view.get("recommendations") or []),
    )
    model.flows = (
        _flow_rows(item_series, "item", bool(items.get("partial"))
                   if isinstance(items, Mapping) else False)
        + _flow_rows(fluid_series, "fluid", bool(fluids.get("partial"))
                     if isinstance(fluids, Mapping) else False)
    )
    model.networks = _power_rows(
        power.get("networks") or [], bool(power.get("partial")))
    model.surface = surface
    if power.get("status") == "unavailable" and power.get("reason"):
        model.reason = str(power["reason"])
    return model


def flow_rate_observation(row: FlowRow) -> Observation:
    """Return the per-second rate of one flow as an observation.

    The per-second figure is derived from the observed per-minute flow,
    so it is an **estimate** and says so.
    """
    return estimated(
        row.output_per_second,
        "Per-second rate derived from the observed per-minute flow",
        source=f"flow:{row.name}",
    )


def power_observation(row: PowerRow) -> Observation:
    """Return the consumption of one electrical network as an observation."""
    return observed(row.delivered_consumption_watts, "Observed delivered power network",
                    source=f"power:{row.network_id}")


def format_flow_rate(value: float) -> str:
    """Format a flow rate for the table."""
    return f"{value:,.2f}/min"


def format_watts(value: float) -> str:
    """Format a power figure for the table."""
    return format_power(value)


def format_energy_rate(value: float) -> str:
    """Format an energy rate for the table."""
    return format_energy(value)


def network_display(network: PowerRow) -> dict[str, str]:
    """Return the labelled values of one electrical network.

    The power display comes from the verified telemetry model, so the
    Qt interface and the Tkinter dashboard agree on the wording.
    """
    rates = power_rate_display({
        "maximum_production": network.generation_watts / 60.0,
        "maximum_consumption": network.consumption_watts / 60.0,
    })
    return {
        "network": f"Network {network.network_id}",
        "generation": rates["production"],
        "consumption": rates["consumption"],
        "energy_per_second": rates["energy_per_second"],
        "satisfaction": f"{network.consumption_satisfaction:.1%}",
        "headroom": format_power(network.headroom_watts),
    }


__all__ = [
    "MAX_SERIES_POINTS",
    "SEVERITIES",
    "SEVERITY_LABELS",
    "FlowRow",
    "PowerRow",
    "TelemetryModel",
    "build_model",
    "envelope_of",
    "flow_rate_observation",
    "is_live_contract",
    "live_model",
    "format_energy_rate",
    "format_flow_rate",
    "format_watts",
    "network_display",
    "payload_surface",
    "power_observation",
]
