"""Render the R10-A Qt workspaces offscreen and save the screenshots.

This is an offline, CPU-only visual check of the Recipes & Research,
Inventory and Logistics workspaces. It opens no game, issues no command and
touches no save. The frames it feeds are the **shapes the live backend
returned** during the R10-A acceptance runs, so the screenshot shows what the
real interface shows.

Run:
    .venv\\Scripts\\python.exe tests/qt_r10a_render.py <evidence-dir>
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

#: The catalog page shape the live backend returned for the vanilla profile:
#: "Partial catalog page 1 of 42 (662 total recipes)" with 16 rows.
CATALOG_FRAME = {
    "status": "ok",
    "protocol": 1,
    "tick": 804,
    "surface": "nauvis",
    "catalog_status": {
        "page": 1, "page_size": 16, "status": "ok",
        "total": 662, "page_count": 42, "partial": False,
    },
    "capabilities": {
        "recipes": [
            {
                "name": f"recipe-{index}",
                "category": "crafting",
                "crafting_time": 0.5,
                "enabled": True,
                "hidden": False,
                "ingredients": [{"type": "item", "name": "iron-plate",
                                 "amount": 1}],
                "products": [{"type": "item", "name": "iron-gear-wheel",
                              "amount": 1}],
            }
            for index in range(16)
        ],
        "research": [{"name": "automation"}, {"name": "logistics"}],
    },
}

#: The player inventory shape the live backend returned: three real stacks.
INVENTORY_FRAME = {
    "status": "ok",
    "protocol": 1,
    "tick": 804,
    "surface": "nauvis",
    "inventory_available": True,
    "capacity": 80,
    "truncated": False,
    "slots_truncated": False,
    "inventory": [
        {"name": "iron-plate", "quality": "normal", "count": 120},
        {"name": "copper-cable", "quality": "normal", "count": 40},
        {"name": "iron-gear-wheel", "quality": "legendary", "count": 8},
    ],
    "telemetry": {
        "status": "ok",
        "production": {
            "status": "ok",
            "items": [{
                "name": "iron-plate",
                "five_seconds": {"produced": 100, "consumed": 20,
                                 "per_second_produced": 20.0,
                                 "per_second_consumed": 4.0},
            }],
            "fluids": [{
                "name": "water",
                "five_seconds": {"produced": 50, "consumed": 10,
                                 "per_second_produced": 10.0,
                                 "per_second_consumed": 2.0},
            }],
            "fluid_status": "ok",
            "partial": True,
        },
        "power": {
            "status": "ok",
            "networks": [{
                "network_id": 7,
                "maximum_production": 186000.0,
                "maximum_consumption": 120000.0,
                "consumption_satisfaction": 1.0,
                "production_satisfaction": 0.94,
                "accumulator_energy": 100.0,
                "accumulator_capacity": 200.0,
            }],
        },
    },
    "overlays": {
        "available": {"logistics": True},
        "logistics": [{
            "x": 10.0, "y": 20.0, "logistic": 8.0,
            "construction": 10.0, "active": True,
        }],
    },
}


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        ".local/r10a-evidence")
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])

    window = qt_shell.ShellWindow()
    window.resize(1600, 940)
    window.show()
    app.processEvents()

    window.set_catalog(CATALOG_FRAME)
    app.processEvents()
    window.show_workspace("Recipes & Research")
    app.processEvents()
    recipes = output / "r10a-recipes-research.png"
    window.grab().save(str(recipes))
    print(f"RENDERED {recipes} ({recipes.stat().st_size} bytes)")

    window.set_inventory(INVENTORY_FRAME)
    app.processEvents()
    window.show_workspace("Inventory")
    app.processEvents()
    inventory = output / "r10a-inventory.png"
    window.grab().save(str(inventory))
    print(f"RENDERED {inventory} ({inventory.stat().st_size} bytes)")

    window.show_workspace("Logistics")
    app.processEvents()
    logistics = output / "r10a-logistics.png"
    window.grab().save(str(logistics))
    print(f"RENDERED {logistics} ({logistics.stat().st_size} bytes)")

    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
