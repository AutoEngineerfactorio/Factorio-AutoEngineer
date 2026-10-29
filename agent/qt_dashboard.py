"""Optional read-only Qt dashboard prototype. Tkinter remains the active launcher.

Run: python agent/qt_dashboard.py [--frame-file local-observation.json]
This UI NEVER connects to RCON, executes commands, or fabricates live game data.
"""
import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

try:
    # Resolve the optional UI dependency dynamically so static analyzers do not
    # require PySide6 to be installed just to inspect this module.
    qt_core = import_module("PySide6.QtCore")
    qt_widgets = import_module("PySide6.QtWidgets")
    QTimer = qt_core.QTimer
    QApplication = qt_widgets.QApplication
    QFrame = qt_widgets.QFrame
    QGridLayout = qt_widgets.QGridLayout
    QHBoxLayout = qt_widgets.QHBoxLayout
    QLabel = qt_widgets.QLabel
    QMainWindow = qt_widgets.QMainWindow
    QPlainTextEdit = qt_widgets.QPlainTextEdit
    QTabWidget = qt_widgets.QTabWidget
    QVBoxLayout = qt_widgets.QVBoxLayout
    QWidget = qt_widgets.QWidget
except ImportError as exc:
    raise SystemExit("Optional UI requires PySide6: python -m pip install PySide6") from exc

MAX_BYTES = 4 * 1048576
FRAME_PREFIX = "@AUTOENGINEER_VIEW "


def decode_local_frame(content):
    """Accept native observer frames or a local JSON snapshot; never query the game."""
    if content.startswith(FRAME_PREFIX):
        from dashboard_feed import parse_frame

        parsed = parse_frame(content.strip())
        if parsed is None:
            raise ValueError("Observer frame was not recognized")
        return parsed
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("Observation must be a JSON object")
    return result
PAGES = ("Overview", "Factory Map", "Production", "Blueprint Studio",
         "Recipes & Research", "Logistics", "Diagnostics")
STYLE = """
QWidget { background:#131a21; color:#e7edf3; font: 10pt 'Segoe UI'; }
QLabel#brand { color:#f6b34c; font-size:18pt; font-weight:800; }
QLabel#heading { color:#f0f3f6; font-size:12pt; font-weight:700; }
QLabel#muted { color:#93a2b1; }
QLabel#metric { color:#f0f3f6; font-size:22pt; font-weight:700; }
QFrame#card { background:#1e2833; border:1px solid #344554; border-radius:10px; }
QTabWidget::pane { border:0px; }
QTabBar::tab { background:#1a2530; color:#b6c6d3; padding:11px 13px; }
QTabBar::tab:selected { color:#f6b34c; background:#2a3745; }
QPlainTextEdit { background:#17222c; border:1px solid #344554;
 color:#dae5ee; border-radius:8px; padding:8px; font:10pt Consolas; }
QSplitter::handle { background:#344554; }
"""


def as_text(value, limit=1500):
    """Bound all UI text, including unexpected mod-provided fields."""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)[:limit]


class Metric(QFrame):
    def __init__(self, name):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        title = QLabel(name.upper())
        title.setObjectName("muted")
        self.value = QLabel("—")
        self.value.setObjectName("metric")
        self.detail = QLabel("Awaiting observation")
        self.detail.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def update_value(self, value, detail="Observed snapshot"):
        self.value.setText(as_text(value, 48))
        self.detail.setText(detail)


class Dashboard(QMainWindow):
    """Standalone visualization shell. No Factorio state mutation interfaces."""

    def __init__(self, frame_file):
        super().__init__()
        self.frame_file = frame_file
        self.signature = None
        self.setWindowTitle("Factorio AutoEngineer | Universal AI Helper — Qt Preview")
        self.resize(1450, 880)
        outer = QWidget()
        shell = QVBoxLayout(outer)
        shell.setSpacing(14)

        header = QHBoxLayout()
        brand = QLabel("AUTOENGINEER")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch()
        self.connection = QLabel("● OFFLINE PREVIEW   |   HELPER • READ ONLY")
        self.connection.setObjectName("muted")
        header.addWidget(self.connection)
        shell.addLayout(header)

        metrics = QGridLayout()
        self.metrics = {}
        for index, label in enumerate(("Game / profile", "UPS", "Power", "Production")):
            tile = Metric(label)
            self.metrics[label] = tile
            metrics.addWidget(tile, 0, index)
        shell.addLayout(metrics)

        self.tabs = QTabWidget()
        self.pages = {}
        for name in PAGES:
            page = QWidget()
            layout = QVBoxLayout(page)
            title = QLabel(name)
            title.setObjectName("heading")
            layout.addWidget(title)
            panel = QPlainTextEdit()
            panel.setReadOnly(True)
            panel.setPlainText(self.placeholder(name))
            layout.addWidget(panel)
            self.pages[name] = panel
            self.tabs.addTab(page, name)
        shell.addWidget(self.tabs, 1)

        footer = QLabel(
            "Qt migration prototype • Local snapshot only • "
            "No gameplay commands • No hidden polling of Factorio"
        )
        footer.setObjectName("muted")
        shell.addWidget(footer)
        self.setCentralWidget(outer)
        self.setStyleSheet(STYLE)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    @staticmethod
    def placeholder(name):
        messages = {
            "Overview": "Game observations will appear here when a verified frame is available.",
            "Factory Map": "Map renderer migration pending. Existing Tkinter map remains available.",
            "Production": "Production and power values must come from real observed data.",
            "Blueprint Studio": "Read-only blueprint preview and local export are planned.",
            "Recipes & Research": "Universal, mod-aware catalog browser is planned.",
            "Logistics": "Train, robot, belt and fluid diagnostics are planned.",
            "Diagnostics": "Observation freshness, errors and profile details will appear here.",
        }
        return messages[name]

    def refresh(self):
        if self.frame_file is None:
            return
        try:
            info = self.frame_file.stat()
            if info.st_size > MAX_BYTES:
                raise ValueError("Snapshot exceeds 4 MiB safety limit")
            signature = (info.st_size, info.st_mtime_ns)
            if signature == self.signature:
                return
            raw = decode_local_frame(self.frame_file.read_text(encoding="utf-8"))
            self.signature = signature
            self.display(raw)
        except (OSError, ValueError, UnicodeError) as exc:
            self.connection.setText(f"● OBSERVATION UNAVAILABLE: {type(exc).__name__}")
            self.pages["Diagnostics"].setPlainText(as_text(str(exc)))

    def display(self, frame):
        # Field presence, not default numbers, determines what is shown.
        if frame.get("status") == "unavailable":
            self.connection.setText("● OBSERVER UNAVAILABLE | HELPER • READ ONLY")
            for tile in self.metrics.values():
                tile.update_value("—", "Unavailable")
            return
        self.connection.setText("● LOCAL SNAPSHOT   |   HELPER • READ ONLY")
        self.metrics["Game / profile"].update_value(
            frame.get("profile", frame.get("gameVersion", "Unknown")))
        for label, key in (("UPS", "ups"), ("Power", "power"),
                           ("Production", "production")):
            value = frame.get(key)
            self.metrics[label].update_value(
                value if value is not None else "—",
                "Observed snapshot" if value is not None else "Not reported",
            )
        sources = {
            "Overview": ("status", "capabilities"),
            "Factory Map": ("map", "terrain", "overlay"),
            "Production": ("telemetry", "production", "power"),
            "Blueprint Studio": ("blueprints", "blueprint"),
            "Recipes & Research": ("recipes", "research", "machines"),
            "Logistics": ("logistics", "inventory"),
            "Diagnostics": ("errors", "freshness", "observation", "schema"),
        }
        for name, keys in sources.items():
            subset = {k: frame[k] for k in keys if k in frame}
            if subset:
                self.pages[name].setPlainText(as_text(subset, 60000))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame-file", type=Path)
    parser.add_argument("--legacy-preview", action="store_true",
                        help="Open the earlier Qt prototype (rollback)")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    if args.legacy_preview:
        window = Dashboard(args.frame_file)
    else:
        from qt_shell import ShellWindow

        window = ShellWindow()
        if args.frame_file is not None:
            signature: list[tuple[int, int] | None] = [None]

            def refresh_snapshot():
                try:
                    info = args.frame_file.stat()
                    if info.st_size > MAX_BYTES:
                        raise ValueError("Snapshot exceeds 4 MiB safety limit")
                    stamp = (info.st_size, info.st_mtime_ns)
                    if stamp == signature[0]:
                        return
                    frame = decode_local_frame(
                        args.frame_file.read_text(encoding="utf-8"))
                    window.apply_frame(frame)
                    signature[0] = stamp
                except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
                    window.apply_disconnect("Local snapshot unavailable")

            timer = QTimer(window)
            timer.timeout.connect(refresh_snapshot)
            timer.start(1500)
            refresh_snapshot()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
