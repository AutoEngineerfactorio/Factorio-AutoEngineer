"""Render the Qt shell offscreen and save a screenshot.

This is an offline, CPU-only visual check of the Phase 2 interface. It
opens no game, issues no command and touches no save. It only proves that
the window builds, lays out and paints with the dark theme.

Run: .venv\\Scripts\\python.exe tests/qt_shell_render.py [output.png]
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

#: A frame with only some fields observed, so the screenshot shows both an
#: observed metric and an unavailable one.
SAMPLE_FRAME = {
    "schema": 1,
    "status": "ok",
    "profile": "vanilla-2.1.23",
    "gameVersion": "2.1.23",
    "ups": 60.0,
    "power": {"consumption": 125000.0, "satisfaction": 0.98},
    "production": {"status": "unavailable", "reason": "No telemetry yet"},
}


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        ".local/qt_shell_render.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = qt_shell.ShellWindow(SAMPLE_FRAME)
    window.resize(1600, 940)
    window.show()
    app.processEvents()
    window.grab().save(str(output))
    window.close()
    print(f"RENDERED {output} ({output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
