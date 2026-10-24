"""Offline rehearsal of real Factorio item/fluid production-counter telemetry.

The same strict trace schema can accept later approved native-game captures.
This script never connects to Factorio, issues RCON, loads saves, sends AI
prompts, or labels synthetic/externally supplied samples as verified gameplay.
The required counters describe *produced* statistics, NOT chest inventory.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

TICKS_PER_SECOND = 60
WINDOWS_MINUTES = (1, 5, 10)
MAX_TRACE_BYTES = 5_000_000
MAX_SAMPLES = 4096
MAX_PRODUCTS = 256
NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$")
VERSION = re.compile(r"^2\.\d+\.\d+(?:\.\d+)?$")


class TraceError(ValueError):
    """Reject incomplete, contradictory or otherwise unsafe observations."""


def finite_nonnegative(value: object) -> float:
    if not isinstance(value, (int, float)) or type(value) not in (int, float):
        raise TraceError("A flow counter or measurement is invalid")
    if not math.isfinite(value) or value < 0:
        raise TraceError("A flow counter or measurement is invalid")
    return float(value)


def identity(raw: object) -> tuple[str, str, str]:
    if not isinstance(raw, dict) or set(raw) not in (
        {"kind", "name"}, {"kind", "name", "quality"}
    ):
        raise TraceError("Product identity needs kind, name and optional quality")
    kind, name = raw["kind"], raw["name"]
    if kind not in ("item", "fluid") or not isinstance(name, str) or not NAME.fullmatch(name):
        raise TraceError("Invalid item/fluid identity")
    quality = raw.get("quality", "normal" if kind == "item" else "none")
    if (not isinstance(quality, str) or not NAME.fullmatch(quality)
            or (kind == "fluid" and quality != "none")):
        raise TraceError("Invalid quality identity for item/fluid")
    return kind, name, quality


def read_counters(rows: object, *, strict_products: set | None = None) -> dict:
    if not isinstance(rows, list) or len(rows) > MAX_PRODUCTS:
        raise TraceError("Counter array is not bounded")
    counters = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) not in (
            {"kind", "name", "total"}, {"kind", "name", "quality", "total"}
        ):
            raise TraceError("Invalid counter row schema")
        key = identity({k: v for k, v in row.items() if k != "total"})
        if key in counters:
            raise TraceError("Duplicate counter identity")
        counters[key] = finite_nonnegative(row["total"])
    if strict_products is not None and set(counters) != strict_products:
        raise TraceError("Captured products changed or are missing")
    return counters


def validate_trace(trace: object) -> tuple[dict, list, dict]:
    if not isinstance(trace, dict) or set(trace) != {
        "schema", "evidence", "profile", "targets", "samples"
    } or trace["schema"] != 1:
        raise TraceError("Invalid replay trace schema")
    if trace["evidence"] not in ("synthetic_fixture", "external_capture_unverified"):
        raise TraceError("Trace evidence must be classified conservatively")
    profile = trace["profile"]
    if (not isinstance(profile, dict) or set(profile) !=
            {"game_version", "force", "surface", "content", "tick_rate"}
            or not isinstance(profile["game_version"], str)
            or VERSION.fullmatch(profile["game_version"]) is None
            or any(not isinstance(profile[k], str) or not NAME.fullmatch(profile[k])
                   for k in ("force", "surface"))
            or type(profile["tick_rate"]) is not int
            or profile["tick_rate"] != TICKS_PER_SECOND
            or not isinstance(profile["content"], list)
            or not 1 <= len(profile["content"]) <= 32
            or any(not isinstance(x, str) or not NAME.fullmatch(x) for x in profile["content"])
            or len(set(profile["content"])) != len(profile["content"])):
        raise TraceError("Invalid or unsupported fixed game profile")
    targets = trace["targets"]
    if not isinstance(targets, list) or not 1 <= len(targets) <= MAX_PRODUCTS:
        raise TraceError("Targets must be a bounded nonempty list")
    wanted = {}
    for item in targets:
        if not isinstance(item, dict) or set(item) not in (
            {"kind", "name", "target_per_minute"},
            {"kind", "name", "quality", "target_per_minute"},
            {"kind", "name", "target_per_minute", "predicted_per_minute"},
            {"kind", "name", "quality", "target_per_minute", "predicted_per_minute"},
        ):
            raise TraceError("Invalid target")
        key = identity({k: v for k, v in item.items()
                        if k not in ("target_per_minute", "predicted_per_minute")})
        amount = finite_nonnegative(item["target_per_minute"])
        predicted = (finite_nonnegative(item["predicted_per_minute"])
                     if "predicted_per_minute" in item else None)
        if amount <= 0 or key in wanted:
            raise TraceError("Target must be positive and unique")
        wanted[key] = (amount, predicted)
    samples = trace["samples"]
    if not isinstance(samples, list) or not 2 <= len(samples) <= MAX_SAMPLES:
        raise TraceError("Not enough (or too many) samples")
    measured = []
    previous_tick = -1
    previous_counters = {}
    for raw in samples:
        if not isinstance(raw, dict) or set(raw) != {"tick", "produced", "consumed", "power_satisfaction"}:
            raise TraceError("Invalid sample; inventory cannot substitute for produced counters")
        tick = raw["tick"]
        if type(tick) is not int or tick <= previous_tick or tick < 0:
            raise TraceError("Ticks must increase without resets or duplicates")
        produced = read_counters(raw["produced"], strict_products=set(wanted))
        consumed = read_counters(raw["consumed"])
        # Missing authorized power telemetry must remain unknown, not 100%.
        power = (None if raw["power_satisfaction"] is None
                 else finite_nonnegative(raw["power_satisfaction"]))
        if power is not None and power > 1:
            raise TraceError("Power satisfaction must be 0 through 1")
        for key, count in produced.items():
            if count + 1e-8 < previous_counters.get(("produced", key), 0):
                raise TraceError("Production counter decreased, reset, or trace crossed a save")
            previous_counters[("produced", key)] = count
        for key, count in consumed.items():
            if count + 1e-8 < previous_counters.get(("consumed", key), 0):
                raise TraceError("Consumption counter decreased or reset")
            previous_counters[("consumed", key)] = count
        measured.append((tick, produced, consumed, power))
        previous_tick = tick
    return profile, measured, wanted


def evaluate_trace(trace: dict, *, tolerance=0.05) -> dict:
    if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
        raise TraceError("Invalid comparison tolerance")
    profile, samples, wanted = validate_trace(trace)
    by_tick = {row[0]: row for row in samples}
    final = samples[-1]
    summary = []
    for key, (target, predicted) in wanted.items():
        windows = {}
        for minutes in WINDOWS_MINUTES:
            start = final[0] - minutes * 60 * TICKS_PER_SECOND
            start_row = by_tick.get(start)
            if start_row is None:
                windows[str(minutes)] = {"status": "NOT_MEASURED",
                                         "reason": "Missing exact game-tick endpoint"}
                continue
            delta = final[1][key] - start_row[1][key]
            if delta < 0:
                raise TraceError("Negative observed production")
            rate = delta / minutes
            status = ("BELOW_TARGET" if rate < target * (1 - tolerance)
                      else "ABOVE_TARGET" if rate > target * (1 + tolerance)
                      else "WITHIN_TARGET")
            consumption_known = (key in start_row[2] and key in final[2])
            used = final[2][key] - start_row[2][key] if consumption_known else None
            windows[str(minutes)] = {"status": status, "units": "per_minute",
                                     "produced": round(delta, 6),
                                     "consumed": round(used, 6) if used is not None else None,
                                     "observed_rate": round(rate, 6),
                                     "target_rate": target,
                                     "predicted_rate": predicted,
                                     "achievement_percent": round(100 * rate / target, 3),
                                     "prediction_error_percent": (
                                         round(100 * (rate - predicted) / predicted, 3)
                                         if predicted is not None and predicted > 0 else None)}
        summary.append({"kind": key[0], "name": key[1], "quality": key[2],
                        "windows_minutes": windows})
    return {
        "schema": 1,
        "evidence": trace["evidence"],
        "validation": "offline_counter_replay_only",
        "live_game_verified": False,
        "note": ("External captures remain unverified until collected and "
                 "validated against an explicitly approved isolated Factorio session."),
        "profile": profile,
        "last_tick": final[0],
        "sample_count": len(samples),
        "minimum_power_satisfaction": min(
            (row[3] for row in samples if row[3] is not None), default=None),
        "products": summary,
    }


def make_demo_trace() -> dict:
    """Independent illustrative factory lines with a synthetic mid-run shortage.

    Gear/plate targets come from the repo's base chain, but these counters are
    illustrative, NOT observed, nor a physically simulated belt/furnace grid.
    """
    products = [
        ("item", "iron-gear-wheel", "normal", 300.0),
        ("item", "iron-plate", "normal", 600.0),
        ("item", "electronic-circuit", "normal", 180.0),
        ("fluid", "water", "none", 1200.0),
    ]
    targets = [
        {"kind": kind, "name": name, **({"quality": quality} if kind == "item" else {}),
         "target_per_minute": target, "predicted_per_minute": target}
        for kind, name, quality, target in products
    ]
    totals = {(kind, name, quality): 0.0 for kind, name, quality, _ in products}
    samples = []
    for second in range(601):
        if second:
            for kind, name, quality, target in products:
                # A modeled supply/power disruption from 5:00 through 6:59.
                scale = 0.4 if 300 <= second - 1 < 420 and kind == "item" else 1.0
                totals[(kind, name, quality)] += target / 60 * scale
        rows = [
            {"kind": kind, "name": name,
             **({"quality": quality} if kind == "item" else {}),
             "total": round(totals[(kind, name, quality)], 7)}
            for kind, name, quality, _ in products
        ]
        samples.append({
            "tick": second * TICKS_PER_SECOND,
            "produced": rows,
            "consumed": [],
            "power_satisfaction": 0.55 if 300 <= second < 420 else 1.0,
        })
    return {
        "schema": 1,
        "evidence": "synthetic_fixture",
        "profile": {"game_version": "2.1.23", "force": "player", "surface": "nauvis",
                    "content": ["base"], "tick_rate": TICKS_PER_SECOND},
        "targets": targets,
        "samples": samples,
    }


def load_trace(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_TRACE_BYTES:
        raise TraceError("Missing or oversized telemetry trace")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise TraceError("Invalid JSON telemetry trace") from exc


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--demo", action="store_true")
    choice.add_argument("--constrained-demo", action="store_true",
                        help="Generate the bounded recipe/machine-limited offline chain")
    choice.add_argument("--input", type=Path)
    p.add_argument("--out", type=Path, help="Optional report file under .local/test-evidence only")
    args = p.parse_args()
    try:
        if args.constrained_demo:
            from factory_chain_simulation import make_constrained_trace

            data = make_constrained_trace()
        elif args.demo:
            data = make_demo_trace()
        else:
            data = load_trace(args.input)
        report = evaluate_trace(data)
        if args.out is not None:
            root = Path(__file__).resolve().parents[1] / ".local" / "test-evidence"
            destination = args.out.resolve()
            if not destination.is_relative_to(root.resolve()) or destination.suffix != ".json":
                raise TraceError("Reports may only be saved under .local/test-evidence as JSON")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    except TraceError as exc:
        print("REPLAY FAILED:", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
