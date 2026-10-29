"""User-launchable Qt AutoEngineer shell; never starts Factorio automatically."""
from __future__ import annotations

import sys


def main() -> int:
    from importlib import import_module

    QApplication = import_module("PySide6.QtWidgets").QApplication
    from qt_shell import ShellWindow
    app = QApplication.instance() or QApplication(sys.argv)
    window = ShellWindow()
    # The stored preferences decide the window size and whether the
    # dashboard opens maximized. A broken settings file falls back to the
    # defaults instead of stopping the application from starting.
    try:
        from settings_store import effective_settings

        preferences = effective_settings()
    except Exception:
        preferences = None
    if preferences is None:
        window.resize(1600, 940)
        window.show()
    else:
        window.resize(
            int(preferences.get("window_width")),
            int(preferences.get("window_height")))
        if preferences.get("start_maximized"):
            window.showMaximized()
        else:
            window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
