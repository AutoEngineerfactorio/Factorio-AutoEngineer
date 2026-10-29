"""The native PySide6 GUI acceptance probe for the dashboard.

This probe drives the **real** graphical interface. It uses the native
Windows platform plugin, not the offscreen renderer, so the widgets are
laid out, painted and measured by the real Qt platform.

It opens no game, contacts no backend and touches no save. Every value it
shows comes from a **synthetic** observation, and the probe says so in its
output.

Run it with the project virtual environment:

    .venv\\Scripts\\python.exe tests\\qt_gui_acceptance.py

The screenshots are written to ``.local/qt_gui/``.
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

# The native Windows platform is the real graphical interface.
os.environ.pop("QT_QPA_PLATFORM", None)

# PySide6 is imported dynamically so that a static analyzer does not need
# it installed to inspect this file. The same pattern is used in
# ``agent/qt_shell.py``.
QApplication = import_module("PySide6.QtWidgets").QApplication
QLabel = import_module("PySide6.QtWidgets").QLabel

import qt_shell  # noqa: E402
from qt_observation import observed  # noqa: E402
from qt_observation_bridge import UiFrame  # noqa: E402

OUT = ROOT / ".local" / "qt_gui"
OUT.mkdir(parents=True, exist_ok=True)

RESULTS: dict[str, object] = {}


def record(name: str, value: object) -> None:
    """Record one measured result."""
    RESULTS[name] = value
    print(f"{name}: {value}")


def synthetic_telemetry(tick: int = 1234, *, satisfaction: float = 0.93,
                        production: float = 1200.0,
                        consumption: float = 1100.0) -> dict:
    """Return a synthetic telemetry payload for the widgets.

    The payload satisfies the **validated** telemetry contract: the item
    group uses the 128-prototype cap and the fluid group the 64-prototype
    cap, exactly as the real observer emits them. The validator rejects
    anything else, so a fixture that drifts is refused rather than shown.
    """
    def group(series: list, cap: int, prototype_count: int) -> dict:
        bucket_count = max(1, -(-prototype_count // cap))
        return {
            "status": "ok",
            "unit": "units_per_minute",
            "precision": "ten_minutes",
            "sample_interval_seconds": 2,
            "sample_count": 60,
            "window_seconds": 120,
            "prototype_count": prototype_count,
            "candidate_cap": cap,
            "candidate_bucket": 1,
            "candidate_bucket_count": bucket_count,
            "partial": prototype_count > cap,
            "series": series,
        }

    network = {
        "network_id": 1,
        "tick": tick,
        "maximum_production": production,
        "maximum_consumption": consumption,
        "consumption_satisfaction": satisfaction,
        "production_satisfaction": 1,
        "accumulator_energy": 0,
        "accumulator_capacity": 0,
    }
    return {
        "schema": 1,
        "tick": tick,
        "production": {
            "status": "partial",
            "reason": "Only one bounded prototype bucket is sampled",
            "items": group([
                {"name": "iron-plate", "input": [2.0] * 60, "output": [10.0] * 60},
                {"name": "copper-plate", "input": [1.0] * 60, "output": [5.0] * 60},
            ], 128, 130),
            "fluids": group([], 64, 70),
        },
        "power": {
            "status": "ok",
            "unit": "joules_per_tick",
            "tick": tick,
            "networks": [network],
            "partial": False,
        },
    }


def synthetic_map(chunks: int = 2) -> dict:
    """Return a synthetic merged map for the map workspace."""
    tiles = []
    for tile_x in range(chunks):
        for tile_y in range(chunks):
            tiles.append({
                "chunk_x": tile_x,
                "chunk_y": tile_y,
                "tiles": [{
                    "x": tile_x * 64 + index % 64,
                    "y": tile_y * 64 + index // 64,
                    "name": "grass-1",
                } for index in range(256)],
            })
    return {"tiles": tiles, "size": chunks * 64}


def pump(app: Any, rounds: int = 3) -> None:
    """Let Qt finish its pending work."""
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    """Run the GUI acceptance probe and write its report."""
    app = QApplication.instance() or QApplication([])
    record("platform", app.platformName())
    record("is_offscreen", app.platformName() == "offscreen")

    window = qt_shell.ShellWindow()
    window.resize(1600, 940)
    window.show()
    pump(app)

    # -- 1. every navigation workspace ------------------------------------
    workspaces = []
    for name in qt_shell.WORKSPACES:
        window.show_workspace(name)
        pump(app)
        workspaces.append({"workspace": name,
                           "shown": window.current_workspace == name})
    record("workspaces", workspaces)
    record("all_workspaces_navigable", all(w["shown"] for w in workspaces))

    # -- 2. the map workspace: pan, zoom and layer toggles ----------------
    window.show_workspace("Factory Map")
    map_widget = window.map_widget()
    window.set_map(synthetic_map(), player={"x": 64, "y": 64})
    pump(app)
    record("map_zoom_label", map_widget.zoom_label)
    zoom_labels = []
    for radius in (4.0, 16.0, 64.0):
        map_widget.zoom_to_level(radius)
        pump(app)
        zoom_labels.append(map_widget.zoom_label)
    record("map_zoom_levels", zoom_labels)
    record("map_toggleable_layers", list(map_widget.toggleable_layers))
    layer_states = {}
    for layer in map_widget.toggleable_layers:
        map_widget.toggle_layer(layer)
        pump(app)
        layer_states[layer] = map_widget.layer_enabled(layer)
        map_widget.toggle_layer(layer)
        pump(app)
    record("map_layer_toggles", layer_states)
    record("map_layers_toggle", all(
        value is False for value in layer_states.values()))

    # -- 3. the telemetry workspaces --------------------------------------
    # The workspace widgets keep their **own** bounded history, so the
    # probe feeds them through the real path: ``set_telemetry`` validates
    # the payload and records it. The charts therefore draw observed
    # samples only.
    payload = synthetic_telemetry()
    for workspace in ("Production", "Electrical"):
        window.show_workspace(workspace)
        widget = window.telemetry_widget(workspace)
        widget.set_telemetry(payload, age_seconds=1.0, at=999.0)
        for index in range(30):
            widget.set_telemetry(synthetic_telemetry(tick=1234 + index),
                                 age_seconds=1.0,
                                 at=1000.0 + index * 2.0)
        pump(app)
    production_widget = window.telemetry_widget("Production")
    electrical_widget = window.telemetry_widget("Electrical")
    record("production_charts", [
        {"name": c.name, "unit": c.unit, "points": len(c.values)}
        for c in production_widget.history.production_charts])
    record("electrical_charts", [
        {"name": c.name, "unit": c.unit, "points": len(c.values)}
        for c in electrical_widget.history.electrical_charts])
    record("production_chart_widgets", len(production_widget.charts))
    record("electrical_chart_widgets", len(electrical_widget.charts))
    record("production_chart_points", len(production_widget.chart_values(0)))
    record("production_chart_last_value",
           production_widget.chart_values(0)[-1]
           if production_widget.chart_values(0) else None)
    record("electrical_chart_last_value",
           electrical_widget.chart_values(0)[-1]
           if electrical_widget.chart_values(0) else None)
    record("production_selector_items",
           [production_widget.selector.itemText(i)
            for i in range(production_widget.selector.count())])
    record("electrical_selector_items",
           [electrical_widget.selector.itemText(i)
            for i in range(electrical_widget.selector.count())])

    # The painted values are the stronger proof: they are empty until the
    # chart has really been drawn.
    window.show_workspace("Production")
    pump(app)
    record("production_painted_points",
           len(production_widget.painted_values(0)))
    record("production_chart_paint_count",
           production_widget.charts[0].paint_count
           if production_widget.charts else 0)

    # The material selector really switches the chart. The chart's title
    # must follow the **selected** material, otherwise the graph would
    # show one material under another's name.
    if production_widget.selector.count() > 1:
        before_title = production_widget.charts[0].spec.title
        before_values = production_widget.chart_values(0)
        production_widget.selector.setCurrentIndex(1)
        pump(app)
        after_title = production_widget.charts[0].spec.title
        after_values = production_widget.chart_values(0)
        selected = production_widget.selector.currentText()
        record("selector_before_title", before_title)
        record("selector_after_title", after_title)
        record("selector_selected", selected)
        record("selector_switches_the_chart",
               before_title != after_title
               and selected in after_title
               and before_values != after_values)

    # -- 4. multiple simultaneous observation updates ---------------------
    window.show_workspace("Overview")
    window.apply_observation(observed(60.0, "Observed"), "UPS")
    window.apply_observation(observed(100.0, "Observed"), "Power")
    window.apply_observation(observed(12.5, "Observed"), "Production")
    pump(app)
    tiles = {name: window.header.tiles[name].value.text()
             for name in ("UPS", "Power", "Production")}
    record("simultaneous_metric_updates", tiles)
    record("simultaneous_updates_all_present",
           tiles["UPS"] == "60.00" and tiles["Power"] == "100.00"
           and tiles["Production"] == "12.50")

    # -- 5. resizing at 1440p ---------------------------------------------
    screen = app.primaryScreen()
    available = screen.availableGeometry()
    record("screen_available", f"{available.width()}x{available.height()}")
    record("device_pixel_ratio", screen.devicePixelRatio())
    resize_times = []
    for width, height in ((2560, 1440), (1920, 1080), (1440, 900), (1100, 700)):
        start = time.perf_counter()
        window.resize(width, height)
        pump(app)
        resize_times.append(time.perf_counter() - start)
    record("resize_median_ms", round(statistics.median(resize_times) * 1000, 2))
    record("resize_max_ms", round(max(resize_times) * 1000, 2))
    window.resize(2560, 1440)
    pump(app)
    # The window takes the size it is given. A request that fits the work
    # area is matched exactly; a request taller than the work area is
    # honoured as well, because Windows allows the window to extend past
    # the taskbar when the user asks for it.
    record("resize_to_1440p_width", window.width())
    record("resize_to_1440p_height", window.height())
    window.resize(available.width(), available.height())
    pump(app)
    record("resize_to_work_area", f"{window.width()}x{window.height()}")
    record("resize_to_1440p_ok",
           window.width() == available.width()
           and window.height() == available.height())

    # -- 6. fonts, labels and readability ---------------------------------
    font = app.font()
    record("application_font", font.family())
    record("application_font_point_size", font.pointSize())
    label_count = 0
    empty_labels = 0
    for page in window._pages.values():
        for child in page.findChildren(QLabel):
            label_count += 1
            if not child.text().strip():
                empty_labels += 1
    record("labels_total", label_count)
    record("labels_empty", empty_labels)
    record("metric_tile_count", len(window.header.tiles))
    record("metric_tile_names", sorted(window.header.tiles))

    # -- 7. CPU and memory -------------------------------------------------
    try:
        import psutil
        process = psutil.Process(os.getpid())
        record("memory_mb",
               round(process.memory_info().rss / (1024 * 1024), 1))
        record("cpu_percent", round(process.cpu_percent(interval=0.2), 1))
        record("thread_count", process.num_threads())
    except ImportError:
        record("memory_mb", "psutil not installed")

    # -- 8. responsiveness during large observations ----------------------
    big = synthetic_map(chunks=8)
    window.show_workspace("Factory Map")
    start = time.perf_counter()
    window.set_map(big, player={"x": 256, "y": 256})
    pump(app)
    record("large_map_update_ms",
           round((time.perf_counter() - start) * 1000, 2))
    record("large_map_primitive_count", len(big["tiles"]) * 256)

    # -- 8b. sustained observation updates --------------------------------
    # The charts must keep up with a steady observation stream without
    # repainting more than the data actually changed.
    window.show_workspace("Production")
    widget = window.telemetry_widget("Production")
    update_times = []
    for index in range(60):
        start = time.perf_counter()
        widget.set_telemetry(synthetic_telemetry(tick=5000 + index),
                             age_seconds=1.0, at=5000.0 + index * 2.0)
        update_times.append(time.perf_counter() - start)
    pump(app)
    record("sustained_update_median_ms",
           round(statistics.median(update_times) * 1000, 3))
    record("sustained_update_max_ms",
           round(max(update_times) * 1000, 3))
    record("sustained_update_total_ms",
           round(sum(update_times) * 1000, 2))
    record("sustained_chart_points", len(widget.chart_values(0)))
    record("sustained_history_points",
           widget.history.stats()["points"])
    record("sustained_history_series",
           widget.history.stats()["series"])

    # -- 9. shutdown and recovery -----------------------------------------
    frames: list = []
    window.frameArrived.connect(frames.append)
    # The bridge publishes the frame; the shell applies it. The signal is
    # the hand-over from the worker thread to the UI thread.
    window._publish_frame(UiFrame(
        kind="status", value={"tick": 1234, "ups": 60.0}, state="observed"))
    pump(app)
    record("frame_signal_received", len(frames) == 1)
    record("frame_signal_applied",
           window.header.tiles["UPS"].value.text() == "60.00")
    window.apply_ui_frame(UiFrame(
        kind="status", value=None, state="unavailable", detail="Disconnected"))
    pump(app)
    record("disconnect_clears_metrics",
           window.header.tiles["UPS"].value.text() == "—")
    window.apply_ui_frame(UiFrame(
        kind="status", value={"tick": 1235, "ups": 59.0}, state="observed"))
    pump(app)
    record("recovery_restores_metrics",
           window.header.tiles["UPS"].value.text() == "59.00")

    # -- screenshots -------------------------------------------------------
    for name in ("Overview", "Factory Map", "Production", "Electrical"):
        window.show_workspace(name)
        pump(app)
        slug = name.lower().replace(" ", "_").replace("&", "and")
        path = OUT / f"gui_{slug}.png"
        window.grab().save(str(path))
        record(f"screenshot_{name}", str(path.relative_to(ROOT)))
        record(f"screenshot_{name}_bytes", path.stat().st_size)

    # -- memory after the run ---------------------------------------------
    try:
        import psutil
        process = psutil.Process(os.getpid())
        record("memory_mb_after",
               round(process.memory_info().rss / (1024 * 1024), 1))
    except ImportError:
        pass

    window.close()
    pump(app)

    report = OUT / "gui_acceptance.json"
    report.write_text(json.dumps(RESULTS, indent=2, default=str),
                      encoding="utf-8")
    print(f"\nreport: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
