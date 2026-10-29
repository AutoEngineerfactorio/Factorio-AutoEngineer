"""Strict validator and conservative recommendation model for observed flows."""

import math

SAMPLE_COUNT = 60
MAX_FLOW_RATE = 1e12
MAX_POWER_VALUE = 1e18


def _label(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 128
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("Invalid telemetry prototype name")
    return value


def _finite_nonnegative(value, maximum):
    return (
        type(value) in (int, float)
        and 0 <= value <= maximum
        and math.isfinite(value)
    )


def _production_group(raw, expected_cap, expected_series, full_series_limit):
    if not isinstance(raw, dict):
        raise ValueError("Invalid production telemetry group")
    status = raw.get("status")
    if status == "unavailable":
        if set(raw) != {"status", "reason"} or not isinstance(raw["reason"], str):
            raise ValueError("Invalid unavailable production telemetry")
        return {"status": status, "reason": raw["reason"]}
    required = {
        "status", "unit", "precision", "sample_interval_seconds",
        "sample_count", "window_seconds", "prototype_count", "candidate_cap",
        "candidate_bucket", "candidate_bucket_count", "partial", "series",
    }
    # Allow optional "reason" field for consistency with validate_telemetry
    if "reason" in raw:
        if set(raw) != required | {"reason"}:
            raise ValueError("Invalid production telemetry shape")
    else:
        if set(raw) != required:
            raise ValueError("Invalid production telemetry shape")
    full_scan = raw.get("candidate_cap") == 10000
    limit = full_series_limit if full_scan else expected_series
    expected_buckets = 1 if full_scan else max(
        1, math.ceil(raw.get("prototype_count", 0) / expected_cap)
    )
    if (raw["unit"] != "units_per_minute"
            or raw["precision"] != "ten_minutes"
            or type(raw["sample_interval_seconds"]) not in (int, float)
            or raw["sample_interval_seconds"] != 2
            or type(raw["sample_count"]) is not int
            or raw["sample_count"] != SAMPLE_COUNT
            or type(raw["window_seconds"]) is not int
            or raw["window_seconds"] != SAMPLE_COUNT * 2
            or type(raw["prototype_count"]) is not int
            or not 0 <= raw["prototype_count"] <= 10000
            or raw["candidate_cap"] not in (expected_cap, 10000)
            or type(raw["candidate_bucket_count"]) is not int
            or raw["candidate_bucket_count"] != expected_buckets
            or type(raw["candidate_bucket"]) is not int
            or not 1 <= raw["candidate_bucket"] <= raw["candidate_bucket_count"]
            or type(raw["partial"]) is not bool
            or (not full_scan and raw["partial"] != (raw["prototype_count"] > expected_cap))
            or not (isinstance(raw["series"], list) or raw["series"] == {})
            or len(raw["series"]) > limit
            or (full_scan and raw["partial"] and len(raw["series"]) != limit)
            or (full_scan and raw["candidate_bucket_count"] != 1)):
        raise ValueError("Invalid production telemetry bounds")
    series = []
    seen = set()
    for row in ([] if raw["series"] == {} else raw["series"]):
        if not isinstance(row, dict) or set(row) != {"name", "input", "output"}:
            raise ValueError("Invalid production flow series")
        name = _label(row["name"])
        if name in seen:
            raise ValueError("Duplicate production flow series")
        seen.add(name)
        for direction in ("input", "output"):
            values = row[direction]
            if (not isinstance(values, list) or len(values) != SAMPLE_COUNT
                    or any(not _finite_nonnegative(value, MAX_FLOW_RATE)
                           for value in values)):
                raise ValueError("Invalid production flow samples")
        series.append({"name": name, "input": list(row["input"]), "output": list(row["output"])})
    result = {
        "status": status,
        "unit": raw["unit"],
        "precision": raw["precision"],
        "sample_interval_seconds": raw["sample_interval_seconds"],
        "sample_count": raw["sample_count"],
        "window_seconds": raw["window_seconds"],
        "prototype_count": raw["prototype_count"],
        "candidate_cap": raw["candidate_cap"],
        "candidate_bucket": raw["candidate_bucket"],
        "candidate_bucket_count": raw["candidate_bucket_count"],
        "partial": raw["partial"],
        "series": series,
    }
    if "reason" in raw:
        result["reason"] = raw["reason"]
    return result


def validate_telemetry(raw, tick):
    """Validate optional telemetry emitted by an exact-version read adapter."""
    if raw is None:
        return {
            "schema": 1,
            "tick": tick,
            "production": {
                "status": "unavailable",
                "reason": "Backend does not report production telemetry",
                "items": {
                    "status": "unavailable",
                    "reason": "Backend does not report item flow statistics",
                },
                "fluids": {
                    "status": "unavailable",
                    "reason": "Backend does not report fluid flow statistics",
                },
            },
            "power": {
                "status": "unavailable",
                "reason": "Backend does not report power telemetry",
                "unit": "joules_per_tick",
                "tick": tick,
                "networks": [],
                "partial": False,
            },
        }
    if (not isinstance(raw, dict) or set(raw) != {"schema", "tick", "production", "power"}
            or type(raw.get("schema")) is not int or raw["schema"] != 1
            or type(raw.get("tick")) is not int or raw["tick"] != tick):
        raise ValueError("Invalid or stale telemetry envelope")
    production = raw["production"]
    if not isinstance(production, dict):
        raise ValueError("Invalid production telemetry envelope")
    if production["status"] not in ("ok", "partial", "unavailable"):
        raise ValueError("Invalid production telemetry status")
    if set(production) not in (
        {"status", "items", "fluids"},
        {"status", "reason", "items", "fluids"},
    ):
        raise ValueError("Invalid production telemetry envelope")
    if ("reason" in production and not isinstance(production["reason"], str)):
        raise ValueError("Invalid production telemetry envelope")

    # Handle unavailable status separately - no items/fluids to process
    if production["status"] == "unavailable":
        items = {"status": "unavailable", "reason": production.get("reason", "No reason")}
        fluids = {"status": "unavailable", "reason": production.get("reason", "No reason")}
        expected_status = "unavailable"
    else:
        items = _production_group(production["items"], 128, 4, 16)
        fluids = _production_group(production["fluids"], 64, 2, 8)
        expected_status = (
            "unavailable"
            if items["status"] == fluids["status"] == "unavailable"
            else "partial"
            if (items.get("partial") or fluids.get("partial")
                or items["status"] == "unavailable" or fluids["status"] == "unavailable")
            else "ok"
        )

    if production["status"] != expected_status:
        raise ValueError("Inconsistent production telemetry status")

    power = raw["power"]
    # Factorio Lua serializes empty indexed tables as JSON objects ({}).
    # Normalize only the empty object; any nonempty mapping remains invalid.
    power_networks = [] if isinstance(power, dict) and power.get("networks") == {} else (power.get("networks") if isinstance(power, dict) else None)
    if (not isinstance(power, dict)
            or "networks" not in power
            or set(power) not in (
                {"status", "reason", "unit", "tick", "networks", "partial"},
                {"status", "unit", "tick", "networks", "partial"},
            )
            or power.get("status") not in ("ok", "partial", "unavailable")
            or power.get("unit") != "joules_per_tick"
            or type(power.get("tick")) is not int or power["tick"] != tick
            or type(power.get("partial")) is not bool
            or not isinstance(power_networks, list)
            or len(power_networks) > 8):
        raise ValueError("Invalid power telemetry envelope")
    if power["status"] == "unavailable":
        if ("reason" not in power or not isinstance(power["reason"], str)
                or len(power_networks) > 0):
            raise ValueError("Unavailable power telemetry must include a reason and no samples")
    elif power["status"] == "partial":
        if (not isinstance(power.get("reason"), str) or not power["reason"].strip()
                or not power["partial"] or not power_networks):
            raise ValueError("Partial legacy power telemetry requires a reason and visible networks")
    elif "reason" in power or len(power_networks) == 0:
        raise ValueError("Available power telemetry requires network samples and no unavailable reason")
    networks = []
    network_ids = set()
    fields = (
        "maximum_production", "maximum_consumption",
        "consumption_satisfaction", "production_satisfaction",
        "accumulator_energy", "accumulator_capacity",
    )
    for row in power_networks:
        if (not isinstance(row, dict)
                or type(row.get("network_id")) is not int
                or not 0 <= row["network_id"] <= 2**32 - 1
                or row["network_id"] in network_ids
                or type(row.get("tick")) is not int or row["tick"] != tick):
            raise ValueError("Invalid electric network sample")
        network_ids.add(row["network_id"])
        normalized = {"network_id": row["network_id"], "tick": tick}
        if power["status"] == "partial":
            # Archived historical-statistics power payloads are still accepted so
            # captured evidence stays replayable for regression analysis. The
            # supported Factorio 2.1.23 backend no longer emits this shape.
            # Empty history is *unknown*, not evidence of zero production or load.
            if (set(row) != {"network_id", "tick", "source", "history_available",
                             "observed_input", "observed_output"}
                    or row["source"] != "legacy_statistics"
                    or type(row["history_available"]) is not bool
                    or not _finite_nonnegative(row["observed_input"], MAX_POWER_VALUE)
                    or not _finite_nonnegative(row["observed_output"], MAX_POWER_VALUE)
                    or (not row["history_available"]
                        and (row["observed_input"] != 0 or row["observed_output"] != 0))):
                raise ValueError("Invalid historical electric-network sample")
            normalized.update(
                source="legacy_statistics",
                history_available=row["history_available"],
                observed_input=row["observed_input"],
                observed_output=row["observed_output"],
            )
        else:
            if set(row) != {"network_id", "tick", *fields}:
                raise ValueError("Invalid instantaneous electric-network sample")
            for field in fields:
                if (not _finite_nonnegative(row[field], MAX_POWER_VALUE)
                        or (field.endswith("satisfaction") and row[field] > 1)):
                    raise ValueError("Invalid electric network measurement")
                normalized[field] = row[field]
        networks.append(normalized)
    if networks != sorted(networks, key=lambda row: row["network_id"]):
        raise ValueError("Electric networks are not deterministically ordered")
    return {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": production["status"], "items": items, "fluids": fluids,
        },
        "power": {
            "status": power["status"],
            **({"reason": power["reason"]} if "reason" in power else {}),
            "unit": power["unit"], "tick": tick,
            "networks": networks, "partial": power["partial"],
        },
    }


def _mean_recent(values, count=30):
    sample = values[-count:]
    return sum(sample) / len(sample)


def telemetry_view_model(telemetry):
    """Create dashboard text and chart data without upgrading evidence status."""
    if not isinstance(telemetry, dict):
        return {
            "status": "unavailable",
            "status_text": "Production and power telemetry unavailable",
            "items": [],
            "fluids": [],
            "networks": [],
            "production_status": "unavailable",
            "production_partial": False,
            "power_status": "unavailable",
            "power_reason": "Telemetry payload is unavailable",
            "power_partial": False,
            "partial": False,
            "recommendations": [],
        }
    production = telemetry["production"]
    power = telemetry["power"]
    production_label = {
        "ok": "Observed flow statistics",
        "partial": "Observed flow statistics · bounded prototype coverage",
        "unavailable": "Production statistics unavailable",
    }[production["status"]]
    recommendations = []
    for material_type, group in (("item", production["items"]), ("fluid", production["fluids"])):
        if group["status"] != "ok":
            continue
        for row in group["series"]:
            input_rate = _mean_recent(row["input"])
            output_rate = _mean_recent(row["output"])
            if output_rate >= 2 and output_rate > input_rate * 1.2 + 0.5:
                recommendations.append({
                    "severity": "candidate",
                    "title": f"Check supply for {material_type}:{row['name']}",
                    "detail": (
                        f"Observed consumption averaged {output_rate:.2f}/min versus "
                        f"production {input_rate:.2f}/min in the recent flow samples. "
                        "This is a possible upstream supply constraint, not proof of a shortage; "
                        "check inventory, external supply, and the upstream chain."
                    ),
                    "score": output_rate - input_rate,
                })
    if power["status"] == "ok":
        for network in power["networks"]:
            satisfaction = network["consumption_satisfaction"]
            if satisfaction < 0.99 and network["maximum_consumption"] > 0:
                recommendations.append({
                    "severity": "high" if satisfaction < 0.95 else "candidate",
                    "title": f"Check power network {network['network_id']}",
                    "detail": (
                        f"Latest observed consumption satisfaction is {satisfaction:.1%}. "
                        "Inspect generation, fuel, accumulators, and network connections."
                    ),
                    "score": (1 - satisfaction) * 1e9,
                })
    recommendations.sort(
        key=lambda item: (
            0 if item["severity"] == "high" else 1,
            -item["score"],
            item["title"],
        )
    )
    recommendation_rows = [
        {key: value for key, value in item.items() if key != "score"}
        for item in recommendations[:8]
    ]
    if not recommendation_rows:
        recommendation_rows.append({
            "severity": "info",
            "title": "No telemetry-backed bottleneck candidate",
            "detail": (
                "No qualifying flow imbalance or under-satisfied observed network was found "
                "in the available samples. Missing or untracked systems are not considered healthy."
            ),
        })
    return {
        "status": "ok",
        "status_text": (
            f"{production_label}; power {power['status']} at tick {power['tick']}"
        ),
        "items": production["items"].get("series", []),
        "fluids": production["fluids"].get("series", []),
        "networks": power["networks"],
        "power_status": power["status"],
        "power_reason": power.get("reason"),
        "power_partial": power.get("partial", False),
        "production_status": production["status"],
        "production_partial": production["status"] == "partial",
        "partial": (
            production["status"] == "partial" or power.get("partial", False)
        ),
        "recommendations": recommendation_rows,
    }


def convert_flow_rate(value, interval="second"):
    """Factorio 2.1 LuaFlowStatistics reports item/fluid flow per minute."""
    if not _finite_nonnegative(value, MAX_FLOW_RATE):
        raise ValueError("Invalid flow rate")
    if interval == "second":
        return value / 60.0
    if interval == "minute":
        return value
    raise ValueError("Expected second or minute interval")


def format_power(watts):
    """Format instantaneous 60-tick/s equivalent electrical power."""
    if not _finite_nonnegative(watts, MAX_POWER_VALUE):
        raise ValueError("Invalid power")
    for factor, label in ((1e9, "GW"), (1e6, "MW"), (1e3, "kW")):
        if watts >= factor:
            return f"{watts / factor:,.2f} {label}"
    return f"{watts:,.1f} W"


def format_energy(joules):
    if not _finite_nonnegative(joules, MAX_POWER_VALUE):
        raise ValueError("Invalid energy")
    for factor, label in ((1e9, "GJ"), (1e6, "MJ"), (1e3, "kJ")):
        if joules >= factor:
            return f"{joules / factor:,.2f} {label}"
    return f"{joules:,.1f} J"


def power_rate_display(network):
    """At standard 60 ticks/s, convert J/tick to power and energy rate.

    Estimates over a minute assume steady load; they are not metered totals.
    """
    production_watts = network["maximum_production"] * 60
    consumption_watts = network["maximum_consumption"] * 60
    return {
        "production": format_power(production_watts),
        "consumption": format_power(consumption_watts),
        "energy_per_second": format_energy(consumption_watts),
        "energy_per_minute_at_current_rate": format_energy(consumption_watts * 60),
    }
