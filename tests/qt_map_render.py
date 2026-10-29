"""Render the Qt map widget offscreen and save a screenshot.

This is an offline, CPU-only visual check of the map workspace. It opens
no game, issues no command and touches no save.

Run: .venv\\Scripts\\python.exe tests/qt_map_render.py [output.png]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from importlib import import_module  # noqa: E402

QApplication = import_module("PySide6.QtWidgets").QApplication

import qt_map_viewport  # noqa: E402
import qt_map_widget  # noqa: E402


def _frame():
    """Return a synthetic observed map with one of each entity kind."""
    entities = []
    for index in range(24):
        entities.append({
            "kind": "building", "x": 30 + index * 3, "y": 40,
            "name": "assembler-1", "width": 3.0, "height": 3.0,
        })
    for index in range(40):
        entities.append({
            "kind": "nature", "x": 60 + index * 2, "y": 90,
            "name": "tree-01", "entity_type": "tree",
            "map_color": [0.61, 1.0, 0.88],
        })
    entities.append({
        "kind": "enemy", "x": 120, "y": 60, "name": "small-biter",
        "enemy_map_color": [1.0, 0.0, 0.0],
    })
    entities.append({
        "kind": "resource", "x": 150, "y": 100, "name": "iron-ore",
        "bounds": {"left_top": {"x": 145.5, "y": 95.5},
                    "right_bottom": {"x": 160.5, "y": 108.5}},
    })
    tiles = [{"x": x, "y": y, "color": "#3d4a3a" if y < 80 else "#4a4438"}
             for x in range(0, 200, 4) for y in range(0, 140, 4)]
    return {
        "origins": [(0, 0)],
        "entities": entities,
        "terrain": {"tiles": tiles},
        "overlays": {"available": {"pollution": True, "electric": True},
                     "pollution": [{"x": 100, "y": 100, "value": 40,
                                    "width": 20, "height": 20}],
                     "electric": [{"x": 50, "y": 50, "radius": 8}]},
        "partial": False,
    }


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        ".local/qt_map_render.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    widget = qt_map_widget.MapWidget(qt_map_viewport.Viewport(
        center_x=90.0, center_y=70.0, radius=90.0))
    widget.resize(1280, 800)
    widget.set_map(_frame(), player={"x": 70, "y": 55})
    widget.show()
    app.processEvents()
    widget.repaint()
    app.processEvents()
    widget.grab().save(str(output))
    print(f"RENDERED {output} ({output.stat().st_size} bytes)")
    print("STATS", widget.stats())
    widget.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
