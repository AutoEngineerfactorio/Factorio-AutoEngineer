"""Render the full Qt dashboard offscreen and save screenshots.

This is an offline, CPU-only visual check. It opens no game, issues no
command and touches no save.

Run: .venv\\Scripts\\python.exe tests/qt_dashboard_render.py [output-dir]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from importlib import import_module  # noqa: E402

QApplication = import_module("PySide6.QtWidgets").QApplication

import qt_shell  # noqa: E402


def _map_frame():
    """Return a synthetic observed map with one of each entity kind."""
    entities = [
        {"kind": "building", "x": 40 + index * 4, "y": 50,
         "name": "assembler-1", "width": 3.0, "height": 3.0}
        for index in range(20)
    ]
    entities += [
        {"kind": "nature", "x": 60 + index * 2, "y": 90, "name": "tree-01",
         "entity_type": "tree", "map_color": [0.61, 1.0, 0.88]}
        for index in range(40)
    ]
    entities.append({"kind": "enemy", "x": 140, "y": 60,
                     "name": "small-biter", "enemy_map_color": [1.0, 0.0, 0.0]})
    entities.append({
        "kind": "resource", "x": 160, "y": 110, "name": "iron-ore",
        "bounds": {"left_top": {"x": 155.5, "y": 105.5},
                    "right_bottom": {"x": 172.5, "y": 118.5}},
    })
    tiles = [{"x": (i % 50) * 4, "y": (i // 50) * 4,
              "color": "#3d4a3a" if (i // 50) % 2 else "#4a4438"}
             for i in range(2500)]
    return {
        "origins": [(0, 0)],
        "entities": entities,
        "terrain": {"tiles": tiles},
        "overlays": {"available": {"pollution": True, "electric": True},
                     "pollution": [{"x": 120, "y": 100, "value": 40,
                                    "width": 20, "height": 20}],
                     "electric": [{"x": 60, "y": 60, "radius": 10}]},
        "partial": False,
    }


def _telemetry(tick=123):
    """Return a validated telemetry payload."""
    def group(cap, series, count=None):
        number = cap if count is None else count
        return {
            "status": "ok", "unit": "units_per_minute",
            "precision": "ten_minutes", "sample_interval_seconds": 2,
            "sample_count": 60, "window_seconds": 120,
            "prototype_count": number, "candidate_cap": cap,
            "candidate_bucket": 1,
            "candidate_bucket_count": max(1, (number + cap - 1) // cap),
            "partial": number > cap, "series": series,
        }

    return {
        "schema": 1, "tick": tick,
        "production": {
            "status": "partial",
            "reason": "Only one bounded prototype bucket is sampled",
            "items": group(128, [
                {"name": "iron-plate", "input": [120.0] * 60,
                 "output": [60.0] * 60},
                {"name": "copper-plate", "input": [80.0] * 60,
                 "output": [80.0] * 60},
                {"name": "electronic-circuit", "input": [10.0] * 60,
                 "output": [95.0] * 60},
            ], count=130),
            "fluids": group(64, []),
        },
        "power": {
            "status": "ok", "unit": "joules_per_tick", "tick": tick,
            "networks": [{
                "network_id": 1, "tick": tick,
                "maximum_production": 5000, "maximum_consumption": 4800,
                "consumption_satisfaction": 0.94, "production_satisfaction": 1,
                "accumulator_energy": 0, "accumulator_capacity": 0,
            }],
            "partial": False,
        },
    }


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".local")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = qt_shell.ShellWindow({
        "schema": 1, "status": "ok", "profile": "vanilla-2.1.23",
        "gameVersion": "2.1.23", "ups": 60.0,
        "power": {"consumption": 288000.0, "satisfaction": 0.94},
    })
    window.resize(1600, 940)
    window.set_map(_map_frame(), player={"x": 70, "y": 55})
    window.set_telemetry(_telemetry())
    window.show()
    app.processEvents()

    for name in ("Factory Map", "Production", "Electrical"):
        window.show_workspace(name)
        app.processEvents()
        window.repaint()
        app.processEvents()
        path = output / f"dashboard_{name.lower().replace(' ', '_')}.png"
        window.grab().save(str(path))
        print(f"RENDERED {path} ({path.stat().st_size} bytes)")

    window.show_workspace("Factory Map")
    app.processEvents()
    print("MAP STATS", window.map_widget().stats())
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
