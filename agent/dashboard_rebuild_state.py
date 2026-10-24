"""Read-only dashboard status presentation; no Factorio or tool access.

This module converts already validated observer state into explicit UI labels.
It never replaces validation in dashboard_feed or invents live measurements.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class Availability(str, Enum):
    CONNECTING = "connecting"
    READY = "ready"
    PARTIAL = "partial"
    STALE = "stale"
    DISCONNECTED = "disconnected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class PanelState:
    label: str
    availability: Availability
    detail: str
    source: str = "not observed"


@dataclass(frozen=True)
class DashboardState:
    connection: PanelState
    production: PanelState
    power: PanelState
    inventory: PanelState
    map: PanelState
    research: PanelState
    game_version: str = "2.1.23"


def _data_panel(label: str, raw: Any, *, connected: bool, stale: bool) -> PanelState:
    if not connected:
        return PanelState(label, Availability.DISCONNECTED, "Observer disconnected")
    if stale:
        return PanelState(label, Availability.STALE, "Last reading is stale")
    if raw is None:
        return PanelState(label, Availability.UNAVAILABLE, "No observation received")
    if label == "Inventory" and isinstance(raw, list):
        return PanelState(label, Availability.READY, "Inventory observed", "live observer")
    if not isinstance(raw, Mapping):
        return PanelState(label, Availability.UNAVAILABLE, "Invalid display data")
    if raw.get("available") is False:
        return PanelState(label, Availability.UNAVAILABLE, "Source reported unavailable")
    if raw.get("partial") is True or raw.get("truncated") is True:
        return PanelState(label, Availability.PARTIAL, "Observation incomplete", "live observer")
    return PanelState(label, Availability.READY, "Observation available", "live observer")


def dashboard_state(
    observation: Mapping[str, Any] | None,
    *,
    connected: bool = False,
    stale: bool = False,
) -> DashboardState:
    """Build display-only statuses from an observer snapshot.

    Only status/provenance is derived. Units, rates and values remain
    exclusively owned by validated telemetry adapters.
    """
    source = observation if isinstance(observation, Mapping) else {}
    if connected and not stale:
        connection = PanelState("Connection", Availability.READY, "Observer connected", "live observer")
    elif stale:
        connection = PanelState("Connection", Availability.STALE, "Observer data is stale")
    elif connected:
        connection = PanelState("Connection", Availability.CONNECTING, "Awaiting snapshot")
    else:
        connection = PanelState("Connection", Availability.DISCONNECTED, "Observer disconnected")

    telemetry = source.get("telemetry")
    production = None
    power = None
    if isinstance(telemetry, Mapping):
        production = telemetry.get("production")
        power = telemetry.get("power")
    return DashboardState(
        connection=connection,
        production=_data_panel("Production", production, connected=connected, stale=stale),
        power=_data_panel("Power", power, connected=connected, stale=stale),
        inventory=_data_panel("Inventory", source.get("inventory"), connected=connected, stale=stale),
        map=_data_panel("Factory map", source.get("terrain"), connected=connected, stale=stale),
        research=_data_panel("Research", source.get("research"), connected=connected, stale=stale),
    )
