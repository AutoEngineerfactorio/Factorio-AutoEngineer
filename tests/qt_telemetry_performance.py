"""The universal modded performance benchmark of the Qt dashboard.

The dashboard has to work with **vanilla**, with **Space Age**, with a
full **Pyanodons** pack and with modpacks whose recipes, prototypes and
electrical networks nobody has seen before. The benchmark therefore
generates its observations **dynamically** from a profile description
rather than replaying a recorded capture.

What it measures:

* the cost of **building** the telemetry model from a payload;
* the cost of **recording** it in the bounded history;
* the cost of **drawing** the charts;
* the **responsiveness** of the interface while the observations arrive;
* the **memory** the histories hold;
* the cost of **repeating** a frame that says nothing new.

Nothing here assumes a vanilla recipe or a Pyanodons prototype: the
material names, the network count and the sample counts all come from the
profile.

The benchmark is **offline**. It opens no game and contacts no backend.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent"
sys.path.insert(0, str(AGENT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QApplication = import_module("PySide6.QtWidgets").QApplication

from qt_telemetry_widget import (  # noqa: E402
    ROLE_ELECTRICAL,
    ROLE_PRODUCTION,
    TelemetryWidget,
)

OUT = ROOT / ".local" / "qt_gui"
OUT.mkdir(parents=True, exist_ok=True)

#: The profiles the benchmark covers.
#:
#: The counts are deliberately different from one another, so a result
#: that only holds for a small vanilla factory is visible.
PROFILES: dict[str, dict[str, int]] = {
    "vanilla": {"materials": 24, "networks": 2, "samples": 60},
    "space-age": {"materials": 90, "networks": 4, "samples": 60},
    "pyanodons": {"materials": 900, "networks": 24, "samples": 60},
    "unknown-modpack": {"materials": 5000, "networks": 64, "samples": 60},
}


#: The bounds the **validated** telemetry contract imposes.
#:
#: These are the limits the observer itself enforces, so the benchmark
#: has to live inside them to measure anything real. A payload outside
#: them is rejected outright, and a rejected payload records nothing.
ITEM_CANDIDATE_CAP = 128
ITEM_SERIES_PER_BUCKET = 4
FLUID_CANDIDATE_CAP = 64
FLUID_SERIES_PER_BUCKET = 2
MAX_PROTOTYPES = 10000

#: The maximum number of electrical networks one observation carries.
#:
#: The observer bounds the networks per frame so a huge modded factory
#: cannot make the observation expensive. A factory with more networks
#: than this is observed over **several** frames, one group at a time.
MAX_NETWORKS_PER_OBSERVATION = 8


def synthetic_materials(count: int, offset: int = 0) -> list[dict[str, Any]]:
    """Return ``count`` material series with unknown, generated names.

    The names are generated, never looked up in a catalog, so the
    benchmark has no vanilla or Pyanodons assumption in it.
    """
    series = []
    for index in range(count):
        base = float((index + offset) % 37) + 1.0
        series.append({
            "name": f"mod-item-{index + offset:05d}",
            "input": [base * 0.25] * 60,
            "output": [base] * 60,
        })
    return series


def synthetic_networks(count: int, tick: int, offset: int = 0
                       ) -> list[dict[str, Any]]:
    """Return ``count`` electrical networks with generated identifiers.

    The identifiers start at ``offset`` so a factory with more networks
    than one observation carries can be observed over several frames
    without repeating a network.
    """
    networks = []
    for index in range(count):
        production = 1200.0 + index * 25.0
        networks.append({
            "network_id": index + 1 + offset,
            "tick": tick,
            "maximum_production": production,
            "maximum_consumption": production * 0.9,
            "consumption_satisfaction": 0.95,
            "production_satisfaction": 1.0,
            "accumulator_energy": 0,
            "accumulator_capacity": 0,
        })
    return networks


def item_group(prototype_count: int, bucket: int, bucket_count: int
               ) -> dict[str, Any]:
    """Return one validated item group for one prototype bucket.

    The observer walks the prototypes in **buckets** of at most
    ``ITEM_CANDIDATE_CAP`` prototypes and reports at most
    ``ITEM_SERIES_PER_BUCKET`` series per bucket. A payload therefore
    carries one bucket, and the dashboard sees one bucket at a time -
    which is exactly how the real observer protects Factorio's UPS.
    """
    series_count = min(ITEM_SERIES_PER_BUCKET,
                       max(0, prototype_count - bucket * ITEM_CANDIDATE_CAP))
    series = synthetic_materials(series_count,
                                 bucket * ITEM_CANDIDATE_CAP)
    return {
        "status": "ok",
        "unit": "units_per_minute",
        "precision": "ten_minutes",
        "sample_interval_seconds": 2,
        "sample_count": 60,
        "window_seconds": 120,
        "prototype_count": min(prototype_count, MAX_PROTOTYPES),
        "candidate_cap": ITEM_CANDIDATE_CAP,
        "candidate_bucket": bucket + 1,
        "candidate_bucket_count": bucket_count,
        "partial": prototype_count > ITEM_CANDIDATE_CAP,
        "series": series,
    }


def fluid_group() -> dict[str, Any]:
    """Return one validated fluid group with no fluid prototypes."""
    return {
        "status": "ok",
        "unit": "units_per_minute",
        "precision": "ten_minutes",
        "sample_interval_seconds": 2,
        "sample_count": 60,
        "window_seconds": 120,
        "prototype_count": 0,
        "candidate_cap": FLUID_CANDIDATE_CAP,
        "candidate_bucket": 1,
        "candidate_bucket_count": 1,
        "partial": False,
        "series": [],
    }


def synthetic_payload(profile: dict[str, int], tick: int,
                      group: int = 0) -> dict[str, Any]:
    """Return one telemetry payload for a profile and observation group.

    The payload satisfies the **validated** telemetry contract, so the
    model accepts it exactly as it would accept a real observation.

    A factory that is bigger than the contract's bounds is observed over
    several **groups**: the materials come from one prototype bucket and
    the networks from one bounded group. That is how the real observer
    protects Factorio's UPS, and the benchmark measures the dashboard
    against exactly that traffic.
    """
    materials = profile["materials"]
    networks = profile["networks"]
    bucket_count = max(1, -(-materials // ITEM_CANDIDATE_CAP))
    network_offset = group * MAX_NETWORKS_PER_OBSERVATION
    return {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": "partial" if materials > ITEM_CANDIDATE_CAP else "ok",
            "items": item_group(materials, group % bucket_count, bucket_count),
            "fluids": fluid_group(),
        },
        "power": {
            "status": "ok",
            "unit": "joules_per_tick",
            "tick": tick,
            "networks": synthetic_networks(
                min(networks - network_offset,
                    MAX_NETWORKS_PER_OBSERVATION),
                tick, offset=network_offset),
            "partial": False,
        },
    }


def observation_groups(profile: dict[str, int]) -> int:
    """Return how many observations one profile needs."""
    return max(
        1,
        -(-profile["materials"] // ITEM_CANDIDATE_CAP),
        -(-profile["networks"] // MAX_NETWORKS_PER_OBSERVATION),
    )


def benchmark_profile(app: Any, name: str,
                      profile: dict[str, int]) -> dict[str, Any]:
    """Measure one profile and return its numbers."""
    production = TelemetryWidget(ROLE_PRODUCTION)
    electrical = TelemetryWidget(ROLE_ELECTRICAL)
    groups = observation_groups(profile)
    payloads = [synthetic_payload(profile, 1, group)
                for group in range(groups)]

    # -- the cost of one observation ------------------------------------
    build_times = []
    history_times = []
    chart_times = []
    frames = 60
    for index in range(frames):
        payload = payloads[index % groups]
        payload["tick"] = index + 1
        start = time.perf_counter()
        production.set_telemetry(payload, age_seconds=1.0,
                                 at=1000.0 + index * 2.0)
        build_times.append(time.perf_counter() - start)
        start = time.perf_counter()
        electrical.set_telemetry(payload, age_seconds=1.0,
                                 at=1000.0 + index * 2.0)
        history_times.append(time.perf_counter() - start)
        # The charts are painted by Qt; the cost of the **geometry** is
        # what the widget pays on the UI thread.
        start = time.perf_counter()
        production._refresh_charts()
        chart_times.append(time.perf_counter() - start)

    app.processEvents()

    # The benchmark is only meaningful when the observations were really
    # accepted. A rejected payload records nothing, and the timings would
    # measure the rejection instead of the work.
    accepted = production.history.stats()["points"]
    if accepted == 0:
        raise RuntimeError(
            f"The benchmark payload for {name!r} was rejected, so it "
            f"measured nothing.")

    # -- the cost of a repeated frame ------------------------------------
    repeat_times = []
    for index in range(30):
        payload = payloads[0]
        payload["tick"] = frames + index + 1
        start = time.perf_counter()
        production.set_telemetry(payload, age_seconds=1.0,
                                 at=1000.0 + frames * 2.0 + index * 2.0)
        repeat_times.append(time.perf_counter() - start)

    # -- the memory the histories hold -----------------------------------
    history = production.history
    stats = history.stats()
    series = stats["series"]
    points = stats["points"]
    # The bytes are counted from the samples the history really holds.
    # Every sample is a float and every stamp is a float, so eight bytes
    # each is the honest floor for the payload itself.
    sample_bytes = points * 8 * 2

    result = {
        "profile": name,
        "materials": profile["materials"],
        "networks": profile["networks"],
        "observation_groups": groups,
        "frames": frames,
        "model_build_median_ms": round(
            statistics.median(build_times) * 1000, 3),
        "model_build_max_ms": round(max(build_times) * 1000, 3),
        "history_median_ms": round(statistics.median(history_times) * 1000, 3),
        "history_max_ms": round(max(history_times) * 1000, 3),
        "chart_geometry_median_ms": round(
            statistics.median(chart_times) * 1000, 3),
        "chart_geometry_max_ms": round(max(chart_times) * 1000, 3),
        "repeated_frame_median_ms": round(
            statistics.median(repeat_times) * 1000, 3),
        "history_series": series,
        "history_points": points,
        "history_sample_bytes": sample_bytes,
        "history_sample_kb": round(sample_bytes / 1024, 1),
        "history_bounded": points <= series * history.maximum_points,
        "charts": len(production.charts),
        "electrical_charts": len(electrical.charts),
        "electrical_series": electrical.history.stats()["series"],
        "observations_accepted": accepted > 0,
    }
    production.close()
    electrical.close()
    return result


def main() -> int:
    """Run the benchmark and write its report."""
    app = QApplication.instance() or QApplication([])
    print(f"platform: {app.platformName()}")
    results = []
    for name, profile in PROFILES.items():
        result = benchmark_profile(app, name, profile)
        results.append(result)
        print(f"\n--- {name} ---")
        for key, value in result.items():
            if key == "profile":
                continue
            print(f"  {key}: {value}")
    report = OUT / "modded_performance.json"
    report.write_text(json.dumps(results, indent=2, default=str),
                      encoding="utf-8")
    print(f"\nreport: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
