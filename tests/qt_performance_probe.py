"""Measure the offline performance of the Qt dashboard.

This is an **offline, CPU-only** measurement. It opens no game, issues no
command, contacts no backend and touches no save. It measures the local
cost of the interface only:

* the import time of the Qt modules;
* the time to build the shell window;
* the time to build a map scene from an observed map;
* the time to paint the map at 1440p and at 1080p;
* the time a skipped repaint costs.

The numbers are local timings. They say nothing about Factorio's UPS or
FPS, which need an authorized live session.

Run: .venv\\Scripts\\python.exe tests/qt_performance_probe.py
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from importlib import import_module  # noqa: E402

QApplication = import_module("PySide6.QtWidgets").QApplication


def _frame(entities: int = 4000, tiles: int = 2500) -> dict:
    """Return a synthetic observed map of a given size."""
    return {
        "origins": [(0, 0)],
        "entities": [
            {"kind": "building", "x": 10 + (i % 80) * 4, "y": 10 + (i // 80) * 4,
             "name": "assembler-1", "width": 3.0, "height": 3.0}
            for i in range(entities)
        ],
        "terrain": {"tiles": [
            {"x": (i % 50) * 4, "y": (i // 50) * 4, "color": "#3d4a3a"}
            for i in range(tiles)
        ]},
        "overlays": {"available": {"pollution": True},
                     "pollution": [{"x": 40, "y": 40, "value": 20,
                                    "width": 8, "height": 8}]},
        "partial": False,
    }


def _timed(function, repeats: int = 20) -> tuple[float, float]:
    """Return the median and the mean milliseconds of a call."""
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples), statistics.mean(samples)


def _memory_mb() -> float | None:
    """Return the process memory in megabytes, or None when unavailable."""
    try:
        import ctypes
        import ctypes.wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(_Counters),
            ctypes.wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb):
            return None
        return round(counters.WorkingSetSize / (1024.0 * 1024.0), 1)
    except (AttributeError, ImportError, OSError):
        return None


def main() -> int:
    results: dict[str, object] = {}

    start = time.perf_counter()
    import qt_map_viewport
    import qt_map_widget
    import qt_shell
    results["import_ms"] = round((time.perf_counter() - start) * 1000.0, 2)

    app = QApplication.instance() or QApplication(sys.argv[:1])

    start = time.perf_counter()
    window = qt_shell.ShellWindow()
    window.resize(2560, 1440)
    window.show()
    app.processEvents()
    results["shell_build_ms"] = round((time.perf_counter() - start) * 1000.0, 2)

    frame = _frame()
    widget = qt_map_widget.MapWidget(qt_map_viewport.Viewport(
        center_x=160.0, center_y=160.0, radius=256.0))
    widget.resize(2560, 1440)
    widget.show()
    app.processEvents()

    widget.set_map(frame, player={"x": 100, "y": 100})
    app.processEvents()
    results["primitives"] = len(widget.scene.primitives) if widget.scene else 0

    median, mean = _timed(lambda: widget.set_map(frame, player={"x": 100, "y": 100}))
    results["scene_build_ms_median"] = round(median, 3)
    results["scene_build_ms_mean"] = round(mean, 3)

    def paint_once() -> None:
        widget.repaint()
        app.processEvents()

    median, mean = _timed(paint_once, repeats=20)
    results["paint_1440p_ms_median"] = round(median, 3)
    results["paint_1440p_ms_mean"] = round(mean, 3)

    widget.resize(1920, 1080)
    app.processEvents()
    median, mean = _timed(paint_once, repeats=20)
    results["paint_1080p_ms_median"] = round(median, 3)
    results["paint_1080p_ms_mean"] = round(mean, 3)

    median, mean = _timed(lambda: widget.refresh(), repeats=200)
    results["skipped_repaint_ms_median"] = round(median, 4)
    results["skipped_repaint_ms_mean"] = round(mean, 4)

    def pan_once() -> None:
        widget.set_viewport(qt_map_viewport.Viewport(
            center_x=170.0, center_y=160.0, radius=256.0))

    median, mean = _timed(pan_once, repeats=20)
    results["viewport_change_ms_median"] = round(median, 3)
    results["viewport_change_ms_mean"] = round(mean, 3)

    results["max_rss_mb"] = _memory_mb()

    widget.close()
    window.close()
    output = Path(".local/qt_performance.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"WRITTEN {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
