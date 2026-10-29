"""The Qt shell window: the navigation rail and the workspace stack.

This module is the frame of the Universal AI Helper dashboard. It owns:

* the **navigation rail** on the left, which switches between the
  workspaces;
* the **workspace stack**, which holds one page per workspace and swaps
  between them without rebuilding the pages;
* the **frame application** path, which feeds an observed frame to the
  header.

The shell never fabricates data. Every number it shows comes from
:mod:`qt_observation`, so a missing observation is an em dash and not a
zero. The shell also never issues a gameplay command: it has no RCON
client, no backend session and no write path at all.

PySide6 is imported dynamically so that a static analyzer does not need
it installed to inspect this module, and so that importing the module
without PySide6 raises a clear message instead of an ImportError trace.
"""

from __future__ import annotations

import time
from dataclasses import replace
from importlib import import_module
from typing import Any, Mapping

from qt_blueprint_studio import BlueprintStudio
from qt_blueprint_workspace import BlueprintWorkspace
from qt_catalog import catalog_snapshot
from qt_catalog_widget import CatalogWidget
from qt_control_center import CommandCenter
from qt_header import HeaderWidget, label
from qt_inventory_widget import InventoryWidget
from qt_map_widget import MapWidget
from qt_observation import (
    OBSERVED,
    STALE,
    UNAVAILABLE,
    Observation,
    estimated,
    unavailable,
)
from qt_observation_bridge import UiFrame
from qt_profile_bar import ProfileBar
from qt_recipe_planner import RecipePlannerWidget
from qt_research_queue import ResearchQueueWidget
from qt_saves_workspace import SavesWorkspace
from qt_settings_workspace import SettingsWorkspace
from qt_telemetry_widget import (
    ROLE_ELECTRICAL,
    ROLE_PRODUCTION,
    TelemetryWidget,
)
from qt_theme import (
    HELPER,
    STYLESHEET,
    HeaderState,
    MetricTile,
    build_header_state,
    build_metric_tiles,
)
from qt_visual_assets import icon

try:
    qt_core = import_module("PySide6.QtCore")
    qt_widgets = import_module("PySide6.QtWidgets")
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise SystemExit(
        "Optional UI requires PySide6: python -m pip install PySide6") from exc

Qt = qt_core.Qt

QFrame = qt_widgets.QFrame
QHBoxLayout = qt_widgets.QHBoxLayout
QMainWindow = qt_widgets.QMainWindow
QPushButton = qt_widgets.QPushButton
QStackedWidget = qt_widgets.QStackedWidget
QVBoxLayout = qt_widgets.QVBoxLayout
QWidget = qt_widgets.QWidget

#: The signal a shell emits when an observed frame arrives.
#:
#: The observation bridge polls the game on a **worker thread**. The frame
#: is handed back to the UI thread through this signal, so the interface
#: never waits for the game and never touches a Qt widget from the worker.
FRAME_SIGNAL = "frameArrived"

#: The workspaces of the dashboard, in navigation order.
WORKSPACES = (
    "Overview",
    "Recipes",
    "Blueprint Studio",
    "Production",
    "Research",
    "Inventory",
    "Electrical",
    "Factory Map",
    "Logistics",
    "Diagnostics",
    "Saves",
    "Settings",
)

#: The role each telemetry workspace plays.
#:
#: The Production workspace draws the **material** history and the
#: Electrical workspace draws the **network** history. Each one has its
#: own bounded history, so the two charts never mix their subjects.
TELEMETRY_ROLES = {
    "Production": ROLE_PRODUCTION,
    "Electrical": ROLE_ELECTRICAL,
}

#: The workspaces that Phase 2 and Phase 4 implement.
IMPLEMENTED_WORKSPACES = (
    "Overview",
    "Factory Map",
    "Production",
    "Electrical",
    "Diagnostics",
)

#: How long a metric observation stays fresh, in seconds.
DEFAULT_METRIC_TTL = 30.0

#: The names of the metric tiles, in the order the header shows them.
METRIC_NAMES = ("Game / profile", "UPS", "Power", "Production")


def _carries_catalog(frame: Mapping[str, Any] | None) -> bool:
    """Whether one frame actually carries an observed catalog.

    A **status** frame carries the player, the surface and the tick, but no
    catalog. Such a frame must never erase the catalog that was already
    observed, so the rows stay on screen instead of being replaced by an
    empty table.
    """
    if not isinstance(frame, Mapping):
        return False
    capabilities = frame.get("capabilities")
    return isinstance(capabilities, Mapping) and bool(capabilities)


class MetricState:
    """The persistent, per-metric observation state of the header.

    Each metric is tracked **independently**. An observation that arrives
    for one metric never rebuilds the others from an older frame, so a
    fresh Power reading cannot erase a valid UPS reading.

    The state also records, per metric, when the value was observed, where
    it came from and how fresh it is. Three rules are enforced:

    * An observation that is **older** than the value already held is
      rejected as out of order. A late packet must not overwrite a newer
      reading.
    * An observation that has **aged out** of its freshness window is shown
      as *stale*, keeping its last number but never presenting it as
      current.
    * A **confirmed disconnect** clears the values. A disconnected game must
      not leave a misleading number on screen.
    """

    def __init__(self, ttl: float = DEFAULT_METRIC_TTL,
                 clock=time.monotonic):
        """Create an empty metric state."""
        if ttl <= 0:
            raise ValueError("The metric freshness window must be positive")
        self.ttl = float(ttl)
        self._clock = clock
        self._observations: dict[str, Observation] = {}
        self._timestamps: dict[str, float] = {}
        self._sources: dict[str, str] = {}
        self._sequence = 0

    # -- reading ---------------------------------------------------------

    def observation(self, name: str) -> Observation:
        """Return the current observation of one metric.

        An unknown metric is **unavailable**, never a zero.
        """
        current = self._observations.get(name)
        if current is None:
            return unavailable("Not observed", source=name)
        return current

    def timestamp(self, name: str) -> float | None:
        """Return when one metric was last observed, or ``None``."""
        return self._timestamps.get(name)

    def source(self, name: str) -> str:
        """Return where the current value of one metric came from."""
        return self._sources.get(name, "")

    def age_seconds(self, name: str) -> float:
        """Return the age of one metric's value in seconds."""
        stamp = self._timestamps.get(name)
        if stamp is None:
            return float("inf")
        return max(0.0, self._clock() - stamp)

    def is_fresh(self, name: str) -> bool:
        """Whether one metric's value is still inside its window."""
        return self.age_seconds(name) <= self.ttl

    def names(self) -> tuple[str, ...]:
        """Return the names of the metrics that hold a value."""
        return tuple(name for name in METRIC_NAMES
                     if name in self._observations)

    # -- writing ---------------------------------------------------------

    def update(self, name: str, observation: Observation, *,
               timestamp: float | None = None,
               source: str = "") -> bool:
        """Record one observation for one metric.

        The observation is rejected when it is **out of order**, that is
        when it carries a timestamp older than the value already held. The
        return value says whether the observation was accepted.
        """
        stamp = self._clock() if timestamp is None else float(timestamp)
        previous_stamp = self._timestamps.get(name)
        if previous_stamp is not None and stamp < previous_stamp:
            return False
        self._observations[name] = observation
        self._timestamps[name] = stamp
        self._sources[name] = source or observation.source or name
        self._sequence += 1
        return True

    def refresh(self, name: str, *, timestamp: float | None = None,
                source: str = "") -> Observation:
        """Age one metric out when it is no longer fresh.

        A value that has outlived its freshness window becomes **stale**:
        the last number survives, but it is never presented as current.
        """
        current = self._observations.get(name)
        if current is None:
            return unavailable("Not observed", source=name)
        age = self.age_seconds(name)
        if age <= self.ttl:
            return current
        aged = Observation(
            value=current.value,
            state=STALE,
            detail=f"Last observed {age:.0f}s ago",
            observed_at=current.observed_at,
            age_seconds=age,
            source=current.source,
        )
        self._observations[name] = aged
        return aged

    def refresh_all(self) -> None:
        """Age every metric out that is no longer fresh."""
        for name in list(self._observations):
            self.refresh(name)

    def disconnect(self, detail: str = "Observer disconnected") -> None:
        """Clear the values after a confirmed disconnect.

        A disconnected observer has told us nothing, so the old numbers are
        dropped. They are shown as unavailable rather than as a stale value
        that could still be mistaken for a live reading.
        """
        for name in list(self._observations):
            self._observations[name] = unavailable(detail, source=name)
            self._timestamps.pop(name, None)
            self._sources.pop(name, None)

    def clear(self) -> None:
        """Drop every observation."""
        self._observations.clear()
        self._timestamps.clear()
        self._sources.clear()

    # -- tiles -----------------------------------------------------------

    def tiles(self, frame: Mapping[str, Any] | None = None) -> list[MetricTile]:
        """Build the metric tiles from the persistent state.

        The tiles are built from the **state**, not from a frame, so a
        metric that was not part of the newest frame keeps its value.
        """
        source = frame if isinstance(frame, Mapping) else {}
        tiles: list[MetricTile] = []
        for name in METRIC_NAMES:
            current = self._observations.get(name)
            if current is None:
                tiles.append(MetricTile(name, unavailable(
                    "Not observed", source=name)))
                continue
            tiles.append(MetricTile(name, current))
        # The profile tile is not a metric observation of its own: it comes
        # from the frame, and it never claims a numeric freshness.
        if tiles:
            tiles[0] = MetricTile("Game / profile", Observation(
                value=str(source.get("profile") or "Profile unknown"),
                state=OBSERVED,
                detail="Observed profile",
                source="frame"))
        return tiles


class NavigationRail(QFrame):
    """The left-hand navigation rail.

    The rail is a group of exclusive checkable buttons, so exactly one
    workspace is active and the user always knows where they are.
    """

    def __init__(self, workspaces: tuple[str, ...] = WORKSPACES,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("rail")
        self.setFixedWidth(208)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 5, 14)
        layout.setSpacing(3)
        self.buttons: dict[str, QPushButton] = {}
        for name in workspaces:
            captions = {
                "Overview": ("Dashboard", "dashboard"), "Recipes": ("AI Helper", "brain"),
                "Blueprint Studio": ("Blueprint Planner", "blueprint"),
                "Production": ("Telemetry", "chart"), "Research": ("Research", "research"),
                "Inventory": ("Inventory", "inventory"), "Electrical": ("Power", "power"),
                "Factory Map": ("Factory Map", "map"), "Logistics": ("Logistics", "logistics"),
                "Diagnostics": ("Logs", "logs"), "Saves": ("Saves", "save"),
                "Settings": ("Settings", "gear"),
            }
            caption, glyph = captions.get(name, (name, "dashboard"))
            button = QPushButton("   " + caption)
            button.setIcon(icon(glyph, "#bdc7cc"))
            button.setIconSize(qt_core.QSize(24, 24))
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            layout.addWidget(button)
            self.buttons[name] = button
        layout.addStretch()

    def button(self, name: str) -> QPushButton:
        """Return the navigation button of one workspace."""
        return self.buttons[name]

    def activate(self, name: str) -> QPushButton:
        """Check the button of one workspace and uncheck the others."""
        for other, button in self.buttons.items():
            button.setChecked(other == name)
        return self.buttons[name]


class ShellWindow(QMainWindow):
    """The dashboard shell.

    The shell owns the rail, the header and the workspace stack. It holds
    **no** transport of its own: the observation frames arrive through
    :meth:`apply_frame`, :meth:`apply_observation` or the
    ``frameArrived`` signal, and nothing here asks the game for anything.
    """

    #: Emitted when an observed frame arrives from the live path.
    frameArrived = qt_core.Signal(object)

    #: Emitted when an observation failed.
    observationError = qt_core.Signal(str)
    observerReady = qt_core.Signal(object)
    saveCatalogReady = qt_core.Signal(object)

    def __init__(self, frame: Mapping[str, Any] | None = None,
                 parent: QWidget | None = None,
                 metric_state: "MetricState | None" = None):
        super().__init__(parent)
        self.setWindowTitle("Factorio AutoEngineer | Universal AI Helper")
        self.resize(1600, 940)
        self.setMinimumSize(1100, 700)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = HeaderWidget()
        outer.addWidget(self.header)

        # The profile bar carries the selected profile and the game
        # controls. It is above the workspace so the user always sees
        # which profile the dashboard is talking about.
        self._ai_process: Any = None
        self.profile_bar = ProfileBar(
            on_game_launched=self._start_local_ai,
            confirm=lambda question: qt_widgets.QMessageBox.question(
                self, "Confirm Factorio action", question,
                qt_widgets.QMessageBox.Yes | qt_widgets.QMessageBox.No,
                qt_widgets.QMessageBox.No,
            ) == qt_widgets.QMessageBox.Yes,
        )
        outer.addWidget(self.profile_bar)
        self.agent_state = qt_widgets.QLabel("Agent: unknown")
        self.stop_ai_button = qt_widgets.QPushButton("Stop AI")
        self.stop_ai_button.clicked.connect(self._stop_local_ai)
        self.ai_logs_button = qt_widgets.QPushButton("AI logs")
        self.ai_logs_button.clicked.connect(self._show_ai_logs)
        self.stop_ai_button.setEnabled(False)
        self.game_data_state = qt_widgets.QLabel("Game data: unavailable")
        self.observerReady.connect(self._attach_game_observer)
        self.observationError.connect(self._observer_error)
        # The real controls belong in the prominent header, not a second strip.
        self.header.stop_ai.clicked.connect(self._stop_local_ai)
        self.header.ai_logs.clicked.connect(self._show_ai_logs)
        self.agent_state.hide()
        self.stop_ai_button.hide()
        self.ai_logs_button.hide()
        self.game_data_state.hide()

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.rail = NavigationRail()
        body.addWidget(self.rail)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(STYLESHEET)

        self._pages: dict[str, QWidget] = {}
        self._current_frame: Mapping[str, Any] | None = None
        self._metrics = metric_state if metric_state is not None else MetricState()
        self._bridge: Any = None
        self._local_observer: Any = None
        self._save_catalog_busy = False
        self._save_catalog_key: tuple[str, str, str] | None = None
        self._save_catalog_pages = 0
        self._save_catalog_last_probe = 0.0
        self.saveCatalogReady.connect(self._apply_save_catalog)
        from dashboard_chunk_cache import ChunkCache
        self._map_cache = ChunkCache()
        self._catalog_requested = False
        self._catalog_recovery_pending = False
        self._last_status_context: tuple[Any, ...] | None = None
        for name in WORKSPACES:
            page = self._create_page(name)
            self._pages[name] = page
            self.stack.addWidget(page)
            button = self.rail.button(name)
            button.clicked.connect(
                lambda _checked=False, target=name: self.show_workspace(target))

        for tool, target in (("Diagnostics", "Diagnostics"), ("Settings", "Settings")):
            self.header.tools[tool].clicked.connect(
                lambda _checked=False, page=target: self.show_workspace(page))
        self.profile_bar.settings_button.clicked.connect(
            lambda _checked=False: self.show_workspace("Settings"))
        # Refresh process state without polling Factorio's game data.
        # Detects a game the user closes from its own window.
        self._game_state_timer = qt_core.QTimer(self)
        self._game_state_timer.setInterval(2000)
        self._game_state_timer.timeout.connect(self._refresh_game_and_ai)
        self._game_state_timer.start()
        self.header.tools["Notifications"].setEnabled(False)
        self.header.tools["Notifications"].setToolTip("No notification feed connected")
        self.map_widget().viewportChanged.connect(self.request_visible_map)
        self.show_workspace(WORKSPACES[0])
        # The header names the selected profile from the start, so the top
        # bar is truthful before a game is connected.
        self.header.apply_header_state(build_header_state(
            None, selected_profile=self.selected_profile_label()))
        self.recipe_widget().planReady.connect(self._send_plan_to_studio)
        if frame is not None:
            self.apply_frame(frame)

    # -- construction helpers -------------------------------------------

    def _create_page(self, name: str) -> QWidget:
        """Create one workspace page.

        A page that is not implemented yet says so plainly. It never
        shows a placeholder that could be mistaken for real data.
        """
        if name == "Overview":
            return CommandCenter(self.show_workspace)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(label(name, "heading"))
        if name == "Factory Map":
            content = MapWidget()
            layout.addWidget(content, 1)
        elif name in ("Production", "Electrical"):
            content = TelemetryWidget(TELEMETRY_ROLES[name])
            layout.addWidget(content, 1)
        elif name == "Recipes":
            content = RecipePlannerWidget()
            layout.addWidget(content, 1)
        elif name == "Research":
            content = ResearchQueueWidget()
            layout.addWidget(content, 1)
        elif name == "Inventory":
            content = InventoryWidget(scope="inventory")
            layout.addWidget(content, 1)
        elif name == "Logistics":
            content = InventoryWidget(scope="logistics")
            layout.addWidget(content, 1)
        elif name == "Settings":
            content = SettingsWorkspace(
                manager=self.profile_bar.manager,
                on_profile_changed=self.profile_bar.reload,
            )
            layout.addWidget(content, 1)
        elif name == "Saves":
            content = SavesWorkspace(
                manager=self.profile_bar.manager,
                session_factory=lambda _profile: self.profile_bar.session,
                confirm=self.profile_bar.confirm,
            )
            layout.addWidget(content, 1)
        elif name == "Blueprint Studio":
            content = BlueprintWorkspace()
            layout.addWidget(content, 1)
        elif name in IMPLEMENTED_WORKSPACES:
            content = QWidget()
            content.setObjectName("card")
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(14, 12, 14, 12)
            content_layout.addWidget(label(
                "Workspace under construction in this phase.", "muted"))
            layout.addWidget(content, 1)
        else:
            layout.addWidget(label(
                "This workspace is not implemented yet. "
                "It shows no data rather than invented data.", "muted"))
            layout.addStretch()
        return page

    # -- navigation ------------------------------------------------------

    def show_workspace(self, name: str) -> None:
        """Switch to one workspace."""
        page = self._pages.get(name)
        if page is None:
            raise KeyError(f"Unknown workspace: {name!r}")
        self.stack.setCurrentWidget(page)
        self.rail.activate(name)
        if name == "Settings":
            self.profile_bar.reload()
            settings_page = page.findChild(SettingsWorkspace)
            if settings_page is not None:
                settings_page.render_profiles()
        if name == "Saves":
            # The Saves page shows the profile's own saves, so it is
            # refreshed whenever the user opens it.
            self.profile_bar.reload()
            saves_page = page.findChild(SavesWorkspace)
            if saves_page is not None:
                saves_page.reload()
        if name == "Factory Map":
            self.request_visible_map()

    def _observer_error(self, message: str) -> None:
        self.game_data_state.setText("Game data: disconnected")
        self.game_data_state.setToolTip(message)
        if self._local_observer is not None and self._local_observer.bridge is None:
            self._local_observer = None
            self._bridge = None

    def _attach_game_observer(self, bridge: Any) -> None:
        self._bridge = bridge
        self.game_data_state.setText("Game data: backend ready; awaiting observations")
        self.frameArrived.connect(self.apply_ui_frame)
        self.catalog_widget().refreshRequested.connect(self.request_catalog_refresh)
        self.catalog_widget().loadMoreRequested.connect(self.request_catalog_more)
        self.request_catalog_refresh()

    def _connect_game_data_if_available(self) -> None:
        if self._local_observer is not None:
            return
        import socket
        with socket.socket() as sock:
            sock.settimeout(0.1)
            if sock.connect_ex(("127.0.0.1", 27015)) != 0:
                self.game_data_state.setText("Game data: RCON unavailable")
                return
        # A foreign RCON listener is never proof that this single-player
        # world is hosted there. Only enter the server observation path
        # when an actual Factorio host/server process is present.
        import psutil

        host_detected = False
        for running in psutil.process_iter(["name", "cmdline"]):
            try:
                if (running.info["name"] or "").lower() != "factorio.exe":
                    continue
                args = running.info["cmdline"] or []
                if "--host" in args or "--start-server" in args:
                    host_detected = True
                    break
            except (psutil.Error, OSError):
                continue
        if not host_detected:
            self.game_data_state.setText("Game data: single-player export")
            return
        from qt_local_game_observer import LocalGameObserver
        self.game_data_state.setText("Game data: connecting")
        self._local_observer = LocalGameObserver(
            on_ready=self.observerReady.emit,
            on_frame=self._publish_frame,
            on_error=self._report_observation_error,
        )
        self._local_observer.start()

    def _stop_local_ai(self) -> None:
        """Stop only the launcher-owned local model."""
        process = self._ai_process
        if process is None or process.state() == qt_core.QProcess.NotRunning:
            self.agent_state.setText("Agent: not launcher-owned")
            return
        process.terminate()
        self.agent_state.setText("Agent: stopping")
        self.stop_ai_button.setEnabled(False)
        self.header.connection.setText("MODEL STOPPING")
        self.header.stop_ai.setEnabled(False)

    def _show_ai_logs(self) -> None:
        """Display the latest model output without opening an external shell."""
        from pathlib import Path
        log = Path(__file__).resolve().parents[1] / ".local" / "ai-runtime.log"
        dialog = qt_widgets.QDialog(self)
        dialog.setWindowTitle("AI runtime logs")
        dialog.resize(850, 500)
        layout = qt_widgets.QVBoxLayout(dialog)
        view = qt_widgets.QPlainTextEdit(dialog)
        view.setReadOnly(True)
        try:
            with log.open("rb") as source:
                source.seek(0, 2)
                source.seek(max(0, source.tell() - 100000))
                view.setPlainText(source.read().decode("utf-8", "replace"))
        except OSError as error:
            view.setPlainText(f"Log not available: {error}")
        layout.addWidget(view)
        dialog.exec()

    def _update_top_header(self) -> None:
        """Render process facts in the main header, separate from game-data health."""
        import socket

        session = self.profile_bar.session
        if session is not None:
            self.header.version.setText(self.profile_bar.version.text())
        process = self._ai_process
        owned = process is not None and process.state() != qt_core.QProcess.NotRunning
        if owned:
            status = "MODEL RUNNING"
        else:
            with socket.socket() as sock:
                sock.settimeout(0.1)
                external = sock.connect_ex(("127.0.0.1", 8080)) == 0
            status = "MODEL EXTERNAL" if external else "OFFLINE"
        self.header.connection.setText(status)
        self.header.connection.setToolTip(
            "Model process status; game observation is shown separately")
        self.header.stop_ai.setEnabled(owned)
        self.header.stop_ai.setToolTip(
            "Stop the local model owned by this window" if owned
            else "No launcher-owned AI process to stop")

    def _apply_save_catalog(self, result: object) -> None:
        """Ingest only new pages on the UI thread; keep catalog assembly local."""
        self._save_catalog_busy = False
        if not isinstance(result, tuple) or len(result) != 5:
            return
        identifier, save_id, generation, total, pages = result
        manager = self.profile_bar.manager
        selected = manager.selected or manager.restore_selection()
        if selected != identifier or not isinstance(pages, list):
            return
        key = (identifier, save_id, generation)
        if self._save_catalog_key != key:
            self._save_catalog_key = key
            self._save_catalog_pages = 0
            self.catalog_widget().set_pager(None)
        if isinstance(pages, dict):
            self._save_catalog_pages = total
            self.catalog_widget().set_pager(None)
            self.set_catalog(
                pages, state="stale",
                detail="Completed saved catalog (cached; not live)")
            self.game_data_state.setText(
                f"Game data: cached save catalog ({total} pages)")
            return
        if not pages:
            return
        from dataclasses import replace

        snapshot = None
        for frame in pages:
            snapshot = self.catalog_widget().apply_page(frame)
            self._save_catalog_pages += 1
        if snapshot is None:
            return
        complete = self._save_catalog_pages >= total and total > 0
        detail = ("Completed" if complete else "Building") + (
            f" save catalog: {self._save_catalog_pages}/{total} pages")
        snapshot = replace(
            snapshot, state="stale", detail=detail,
            status="ok" if complete else "partial")
        self.recipe_widget().set_snapshot(snapshot)
        self.research_widget().set_snapshot(snapshot)
        self.blueprint_widget().set_catalog_snapshot(snapshot)
        self.blueprint_workspace().set_observed_catalog(snapshot)
        self.game_data_state.setText("Game data: " + detail)

    def _check_singleplayer_cache(self) -> None:
        """Read a few exported pages off-thread while Factorio keeps running."""
        import threading
        import time

        if self._bridge is not None or self._save_catalog_busy:
            return
        now = time.monotonic()
        if now - self._save_catalog_last_probe < 8:
            return
        self._save_catalog_last_probe = now
        manager = self.profile_bar.manager
        identifier = manager.selected or manager.restore_selection()
        if identifier is None:
            return
        try:
            profile = manager.load(identifier)
        except Exception:
            return
        root = profile.root / "script-output" / "autoengineer" / "catalog"
        current_key = self._save_catalog_key
        current_pages = self._save_catalog_pages
        session = self.profile_bar.session
        offline = session is None or not session.state().running
        self._save_catalog_busy = True

        def load() -> None:
            from qt_save_catalog_cache import read_active_pages, read_or_build_compiled

            try:
                header = read_active_pages(
                    root, max_pages=0, game_version=profile.game_version,
                    allow_stale=offline)
                if header is None:
                    self.saveCatalogReady.emit(None)
                    return
                save_id, generation, _total, _pages = header
                same = current_key == (identifier, save_id, generation)
                if same and current_pages >= _total and _total > 0:
                    self.saveCatalogReady.emit(None)
                    return
                import json

                current = json.loads(
                    (root / "current.json").read_text(encoding="utf-8"))
                signature = current.get("mod_signature")
                if isinstance(signature, str):
                    complete = read_or_build_compiled(
                        root, profile.cache_directory / "autoengineer" / "catalog",
                        save_id=save_id, generation=generation,
                        game_version=profile.game_version,
                        mod_signature=signature)
                    if complete is not None:
                        self.saveCatalogReady.emit((
                            identifier, save_id, generation, _total, complete))
                        return
                result = read_active_pages(
                    root, after_page=current_pages if same else 0,
                    max_pages=16, game_version=profile.game_version,
                    allow_stale=offline)
                if result is None:
                    self.saveCatalogReady.emit(None)
                    return
                _, _, total, pages = result
                self.saveCatalogReady.emit(
                    (identifier, save_id, generation, total, pages))
            except Exception:
                self.saveCatalogReady.emit(None)

        threading.Thread(target=load, daemon=True,
                         name="ae-save-catalog-loader").start()

    def _refresh_game_and_ai(self) -> None:
        self.profile_bar.reload()
        self._check_singleplayer_cache()
        self._update_top_header()
        if self.profile_bar.session is not None and self.profile_bar.session.state().running:
            self._connect_game_data_if_available()
        elif self._local_observer is not None:
            self._local_observer.stop()
            self._local_observer = None
            self._bridge = None
            self.game_data_state.setText("Game data: game closed")
        process = self._ai_process
        if process is not None and process.state() != qt_core.QProcess.NotRunning:
            self.agent_state.setText("Agent: model process running (not gameplay-connected)")
            self.stop_ai_button.setEnabled(True)
        else:
            import socket
            with socket.socket() as connection:
                connection.settimeout(0.1)
                available = connection.connect_ex(("127.0.0.1", 8080)) == 0
            self.agent_state.setText(
                "Agent: external endpoint detected" if available
                else "Agent: offline")
            self.stop_ai_button.setEnabled(False)
        if process is None:
            return
        if process.state() == qt_core.QProcess.NotRunning:
            self._ai_process = None
            process.deleteLater()
            return
        session = self.profile_bar.session
        if session is None or not session.state().running:
            process.terminate()
            self._ai_process = None

    def _start_local_ai(self) -> None:
        """Start the local inference service for an owned game launch.

        This does not claim that recipe observation or autonomy is connected.
        Never replace a service already using the configured port.
        """
        import socket
        from pathlib import Path

        exe = Path(r"D:\AI\Factorio-AutoEngineer\llama.cpp\llama-server.exe")
        model = Path(r"D:\AI\Factorio-AutoEngineer\models\FrogNano-4B-2609-Q4_K_M.gguf")
        if self._ai_process is not None and self._ai_process.state() != qt_core.QProcess.NotRunning:
            return
        if not exe.is_file() or not model.is_file():
            self.profile_bar.feedback.setText("Game started; local AI files are missing.")
            return
        with socket.socket() as probe:
            probe.settimeout(0.15)
            if probe.connect_ex(("127.0.0.1", 8080)) == 0:
                self.profile_bar.feedback.setText(
                    "Game started; AI endpoint already occupied (not verified).")
                return
        process = qt_core.QProcess(self)
        process.setProgram(str(exe))
        process.setArguments([
            "--model", str(model), "--host", "127.0.0.1",
            "--port", "8080", "--ctx-size", "4096",
            "--n-gpu-layers", "99", "--alias", "autoengineer-local",
        ])
        log_path = Path(__file__).resolve().parents[1] / ".local" / "ai-runtime.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        process.setStandardOutputFile(str(log_path), qt_core.QIODevice.Append)
        process.setProcessChannelMode(qt_core.QProcess.MergedChannels)
        process.start()
        if not process.waitForStarted(2000):
            self.profile_bar.feedback.setText(
                "Game started; local AI failed to start. Check ai-runtime.log.")
            process.deleteLater()
            return
        self._ai_process = process
        self.agent_state.setText("Agent: model process starting")
        self.stop_ai_button.setEnabled(True)
        self.profile_bar.feedback.setText(
            "Game started; local AI launching (readiness not yet verified).")
        self._update_top_header()

    def selected_profile_label(self) -> str:
        """Return the name of the selected profile, or an empty string.

        The header shows this when no game is connected, so the top bar
        always names the profile the application is working with.
        """
        manager = self.profile_bar.manager
        identifier = manager.selected
        if identifier is None:
            identifier = manager.restore_selection()
        if identifier is None:
            return ""
        try:
            profile = manager.load(identifier)
        except Exception:
            return ""
        version = profile.game_version or "unknown"
        return f"{profile.name} • Factorio {version}"

    def request_visible_map(self, *_args: Any) -> None:
        """Ask only for visible chunks when the user opens or moves the map."""
        if self.current_workspace != "Factory Map" or self._bridge is None:
            return
        if hasattr(self._bridge, "request_map"):
            self._bridge.request_map(self.map_widget().visible_chunks(limit=16))

    @property
    def current_workspace(self) -> str:
        """The name of the visible workspace."""
        current = self.stack.currentWidget()
        for name, page in self._pages.items():
            if page is current:
                return name
        return WORKSPACES[0]

    def page(self, name: str) -> QWidget:
        """Return the page widget of one workspace."""
        page = self._pages.get(name)
        if page is None:
            raise KeyError(f"Unknown workspace: {name!r}")
        return page

    def command_center(self) -> CommandCenter:
        return self.page("Overview")

    def map_widget(self) -> MapWidget:
        """Return the interactive map widget.

        The widget lives inside the Factory Map page, so it is found
        rather than kept twice.
        """
        page = self.page("Factory Map")
        for child in page.findChildren(MapWidget):
            return child
        raise KeyError("The Factory Map workspace has no map widget")

    def telemetry_widget(self, workspace: str = "Production") -> TelemetryWidget:
        """Return the telemetry widget of one telemetry workspace."""
        page = self.page(workspace)
        for child in page.findChildren(TelemetryWidget):
            return child
        raise KeyError(f"The {workspace} workspace has no telemetry widget")

    def blueprint_workspace(self) -> BlueprintWorkspace:
        """Return the persistent library and observed-recipe generation workspace."""
        for child in self.page("Blueprint Studio").findChildren(BlueprintWorkspace):
            return child
        raise KeyError("The Blueprint Studio workspace is missing")

    def blueprint_widget(self) -> BlueprintStudio:
        """Return the standalone read-only blueprint importer/preview/exporter."""
        for child in self.page("Blueprint Studio").findChildren(BlueprintStudio):
            return child
        raise KeyError("The Blueprint Studio workspace has no blueprint widget")

    def recipe_widget(self) -> RecipePlannerWidget:
        """Return the production planner and observed catalog browser."""
        for child in self.page("Recipes").findChildren(RecipePlannerWidget):
            return child
        raise KeyError("Recipes workspace has no production planner")

    def research_widget(self) -> ResearchQueueWidget:
        """Return the independent persistent local research-queue workspace."""
        for child in self.page("Research").findChildren(ResearchQueueWidget):
            return child
        raise KeyError("Research workspace has no queue widget")

    def catalog_widget(self) -> CatalogWidget:
        """Preserve the live catalog browser API under the recipe planner."""
        return self.recipe_widget().catalog

    def set_catalog(self, frame: Mapping[str, Any] | None, *,
                   state: str = "observed",
                   detail: str = "Observed catalog") -> None:
        """Show an observed catalog frame in the browser.

        A frame that carries no catalog at all is a **status** frame. It
        must not erase a catalog that was already observed, so the observed
        rows stay on screen instead of being replaced by an empty table.
        """
        if not _carries_catalog(frame):
            return
        snapshot = catalog_snapshot(frame, state=state, detail=detail)
        self.recipe_widget().set_snapshot(snapshot)
        self.research_widget().set_snapshot(snapshot)
        self.blueprint_widget().set_catalog_snapshot(snapshot)
        self.blueprint_workspace().set_observed_catalog(snapshot)

    def inventory_widget(self, workspace: str = "Inventory") -> InventoryWidget:
        """Return the observed inventory widget of one workspace.

        The widget lives inside its workspace page, so it is found rather
        than kept twice.
        """
        page = self.page(workspace)
        for child in page.findChildren(InventoryWidget):
            return child
        raise KeyError(f"The {workspace} workspace has no inventory widget")

    def set_inventory(self, frame: Mapping[str, Any] | None, *,
                      state: str = "observed",
                      detail: str = "Observed inventory") -> None:
        """Show one observed frame in the Inventory and Logistics workspaces.

        Both workspaces consume the **same** observed frame, so the two
        never show contradictory numbers.
        """
        for workspace in ("Inventory", "Logistics"):
            self.inventory_widget(workspace).set_frame(
                frame, state=state, detail=detail)

    def set_inventory_observation(self, frame: Mapping[str, Any] | None, *,
                                  state: str = "observed",
                                  detail: str = "Observed inventory and logistics"
                                  ) -> None:
        """Show one observed R10-B frame in the two workspaces.

        The R10-B observation carries the machine inventories, the
        logistic networks, the robot counters and the transport inventories.
        Both workspaces consume the **same** observed frame, so the two
        never show contradictory numbers.
        """
        for workspace in ("Inventory", "Logistics"):
            self.inventory_widget(workspace).set_observation(
                frame, state=state, detail=detail)
        self.command_center().set_inventory_model(self.inventory_widget("Logistics").snapshot)

    def set_map(self, merged_map: Mapping[str, Any] | None,
                player: Mapping[str, Any] | None = None) -> None:
        """Show an observed map in the Factory Map workspace."""
        self.map_widget().set_map(merged_map, player=player)

    def set_telemetry(self, telemetry: Mapping[str, Any] | None, *,
                      age_seconds: float | None = None) -> None:
        """Show an observed telemetry payload in the telemetry workspaces."""
        for workspace in ("Production", "Electrical"):
            self.telemetry_widget(workspace).set_telemetry(
                telemetry, age_seconds=age_seconds)
        self.command_center().set_telemetry_model(
            self.telemetry_widget("Production").model, age_seconds=age_seconds)

    # -- observation -----------------------------------------------------

    def apply_frame(self, frame: Mapping[str, Any] | None,
                    *, age_seconds: float | None = None,
                    mode: str = HELPER) -> None:
        """Apply one observed frame to the header.

        The frame is the only source of truth in the header. A frame that
        is missing fields leaves those metrics unavailable rather than
        blank or zero.

        The frame also **seeds** the persistent metric state, so the
        metrics it carries survive the arrival of later, individually
        delivered observations.
        """
        self._current_frame = frame
        self._seed_metrics_from_frame(frame)
        self.set_catalog(frame)
        self.set_inventory(frame)
        state = build_header_state(frame, mode=mode, age_seconds=age_seconds,
                                   selected_profile=self.selected_profile_label())
        self.header.apply_header_state(state)
        self.header.apply_game_context(frame or {})
        tiles = self._metrics.tiles(frame)
        self.header.apply_metric_tiles(tiles)
        self.command_center().apply_status(frame, state, tiles)

    def _seed_metrics_from_frame(self, frame: Mapping[str, Any] | None
                                 ) -> None:
        """Seed the metric state from an observed frame.

        Only the metrics the frame actually carries are seeded. A frame
        without a Power reading does not clear a Power reading that
        arrived on its own earlier.
        """
        if not isinstance(frame, Mapping):
            return
        for tile in build_metric_tiles(frame):
            if tile.name == "Game / profile":
                continue
            if tile.observation.state == UNAVAILABLE:
                continue
            self._metrics.update(
                tile.name, tile.observation, source=tile.observation.source)

    def apply_observation(self, observation: Observation, name: str,
                          *, age_seconds: float | None = None,
                          timestamp: float | None = None,
                          source: str = "") -> bool:
        """Apply one named observation to the header.

        This is the path the live pollers use: each observation arrives
        separately, and the header shows the newest value of each.

        The observation updates **only its own metric**. The other
        metrics keep the values they already hold, so a Power reading
        never erases a valid UPS reading.

        An observation that is **out of order** - older than the value
        already held for that metric - is rejected, and the method returns
        ``False``. The rejected value never reaches the header.
        """
        accepted = self._metrics.update(
            name, observation, timestamp=timestamp, source=source)
        if not accepted:
            return False
        tiles = self._metrics.tiles(self._current_frame)
        self.header.apply_metric_tiles(tiles)
        state = build_header_state(self._current_frame, age_seconds=age_seconds)
        self.command_center().apply_status(self._current_frame, state, tiles)
        if age_seconds is not None:
            self.header.apply_header_state(state)
        return True

    def _invalidate_catalog(self, detail: str) -> None:
        snapshot = self.catalog_widget().snapshot
        if snapshot is None or not snapshot.known:
            return
        stale = replace(snapshot, state=STALE, detail=detail)
        self.recipe_widget().set_snapshot(stale)
        self.research_widget().set_snapshot(stale)
        self.blueprint_widget().set_catalog_snapshot(stale)
        self.blueprint_workspace().set_observed_catalog(stale)

    def apply_disconnect(self, detail: str = "Observer disconnected",
                         *, age_seconds: float | None = None) -> None:
        """Clear the metric state after a confirmed disconnect.

        A disconnected observer has reported nothing, so the old numbers
        are dropped rather than left on screen as if they were live.
        """
        snapshot = self.catalog_widget().snapshot
        self._catalog_recovery_pending = self._catalog_requested or bool(snapshot and snapshot.known)
        self._last_status_context = None
        from dashboard_chunk_cache import ChunkCache
        self._map_cache = ChunkCache()
        self.set_map(None)
        disconnected = dict(self._current_frame or {})
        disconnected.update(status="unavailable", live=False)
        disconnected.pop("transport", None)
        self._current_frame = disconnected
        self.set_inventory_observation(None, state=UNAVAILABLE, detail=detail)
        self._metrics.disconnect(detail)
        self._invalidate_catalog(detail)
        self.header.apply_metric_tiles(self._metrics.tiles(self._current_frame))
        self.command_center().show_disconnected()
        state = build_header_state(disconnected, age_seconds=age_seconds,
                                   message=detail,
                                   selected_profile=self.selected_profile_label())
        self.header.apply_header_state(state)

    def refresh_metrics(self, *, age_seconds: float | None = None) -> None:
        """Age the metrics out that are no longer fresh.

        A value that outlived its freshness window becomes **stale**: the
        last number survives, but it is never presented as current.
        """
        self._metrics.refresh_all()
        tiles = self._metrics.tiles(self._current_frame)
        self.header.apply_metric_tiles(tiles)
        self.command_center().apply_status(
            self._current_frame,
            build_header_state(self._current_frame, age_seconds=age_seconds), tiles)
        if age_seconds is not None:
            state = build_header_state(
                self._current_frame, age_seconds=age_seconds)
            self.header.apply_header_state(state)

    @property
    def metric_state(self) -> MetricState:
        """The persistent per-metric observation state."""
        return self._metrics

    def metric_observation(self, name: str) -> Observation:
        """Return the current observation of one metric tile."""
        return self._metrics.observation(name)

    def apply_header_state(self, state: HeaderState) -> None:
        """Apply a header state directly.

        The live path builds the header state itself, because it knows the
        age of each observation.
        """
        self.header.apply_header_state(state)

    def apply_ui_frame(self, frame: UiFrame) -> None:
        """Apply one validated observation frame from the live path.

        The frame arrives from the observation bridge, which already
        deduplicated it, ordered it and translated its truthfulness. The
        shell only routes it:

        * a **status** frame updates the header's metric tiles;
        * a **telemetry** frame updates the telemetry workspaces;
        * a frame that reports a **disconnect** clears the metric state,
          so no misleading number survives a lost observer.
        """
        if frame.kind == "status":
            self._apply_status_frame(frame)
            return
        if frame.kind == "telemetry":
            self.set_telemetry(frame.value if frame.observed else None,
                               age_seconds=frame.age_seconds)
            return
        if frame.kind == "map":
            if frame.observed and isinstance(frame.value, dict):
                surface = frame.value.get("surface")
                current = (self._current_frame or {}).get("surface")
                if surface and surface == current:
                    from dashboard_chunk_map import merge_chunks
                    terrain, tick = frame.value.get("terrain"), frame.value.get("tick")
                    if isinstance(terrain, dict) and type(tick) is int:
                        try:
                            self._map_cache.set_surface(surface)
                            self._map_cache.store(terrain, tick=tick)
                        except ValueError:
                            return
                        self.set_map(merge_chunks(self._map_cache, self._map_cache.records()))
            return
        if frame.kind == "inventory":
            payload = frame.value if isinstance(frame.value, Mapping) else None
            self.set_inventory_observation(payload, state=frame.state, detail=frame.detail)
            return
        if frame.kind == "catalog":
            self._apply_catalog_frame(frame)
            return
        if frame.disconnected:
            self.apply_disconnect(frame.detail, age_seconds=frame.age_seconds)

    def _apply_catalog_frame(self, frame: UiFrame) -> None:
        """Show one observed catalog frame in the Recipes & Research page.

        The frame is the page the user asked for. A frame that failed is
        shown as unavailable, and the rows that were already shown stay
        visible instead of being replaced by an empty table.
        """
        payload = frame.value if isinstance(frame.value, Mapping) else None
        if payload is None:
            self._invalidate_catalog(frame.detail)
            self.catalog_widget().status.setText(
                f"Catalog unavailable: {frame.detail}")
            return
        snapshot = self.catalog_widget().apply_page(payload)
        if frame.state != OBSERVED or frame.partial:
            snapshot = replace(snapshot, state=frame.state, detail=frame.detail,
                               truncated=snapshot.truncated or frame.partial)
        self.recipe_widget().set_snapshot(snapshot)
        self.research_widget().set_snapshot(snapshot)
        self.blueprint_widget().set_catalog_snapshot(snapshot)
        self.blueprint_workspace().set_observed_catalog(snapshot)

    def _apply_status_frame(self, frame: UiFrame) -> None:
        """Apply the metric tiles carried by a status frame."""
        payload = dict(frame.value) if isinstance(frame.value, Mapping) else {}
        if frame.disconnected:
            self.apply_disconnect(frame.detail, age_seconds=frame.age_seconds)
            return
        snapshot = self.catalog_widget().snapshot
        self._catalog_requested = self._catalog_requested or bool(snapshot and snapshot.known)
        if not frame.observed:
            self.set_map(None)
            self._catalog_recovery_pending = self._catalog_requested
            self._invalidate_catalog(frame.detail)
        if not frame.known:
            unavailable_frame = dict(self._current_frame or {})
            unavailable_frame.update(status="unavailable", live=False)
            unavailable_frame.pop("transport", None)
            self._current_frame = unavailable_frame
            self.refresh_metrics(age_seconds=frame.age_seconds)
            return
        payload["live"] = frame.observed
        if not frame.observed:
            payload.pop("transport", None)
        else:
            previous = self._last_status_context
            if previous is None:
                previous = (snapshot.surface, snapshot.force, snapshot.game_version) if snapshot else (None, None, None)
            keys = ("surface", "force", "gameVersion")
            context = tuple(payload.get(key, old) for key, old in zip(keys, previous))
            changed = any(old is not None and new is not None and old != new
                          for old, new in zip(previous, context))
            self._last_status_context = context
            if changed and self._catalog_requested:
                self._invalidate_catalog("Observed game, force or surface changed; refreshing catalog")
                self._catalog_recovery_pending = True
            if self._catalog_recovery_pending:
                self._catalog_recovery_pending = False
                self.request_catalog_refresh()
        self.apply_frame(payload, age_seconds=frame.age_seconds)
        if frame.derived_ups is not None and frame.observed:
            self.apply_observation(estimated(frame.derived_ups,
                "Game tick change divided by elapsed monotonic time", source="tick rate"), "UPS",
                age_seconds=frame.age_seconds, source="tick rate")

    # -- the live observation path ---------------------------------------

    def start_observations(self, bridge: Any, session: Any) -> None:
        """Start the observation bridge and show what it observes.

        The bridge polls the game on a **worker thread**. Every frame is
        handed back through the shell's ``frameArrived`` signal, which Qt
        delivers on the UI thread, so no widget is ever touched from the
        worker and the interface never waits for the game.
        """
        if self._bridge is not None:
            raise RuntimeError("The shell is already observing")
        self._bridge = bridge
        self.frameArrived.connect(self.apply_ui_frame)
        self.catalog_widget().refreshRequested.connect(self.request_catalog_refresh)
        self.catalog_widget().loadMoreRequested.connect(self.request_catalog_more)
        bridge.start(session, self._publish_frame,
                     on_error=self._report_observation_error)

    def _send_plan_to_studio(self, plan: dict[str, Any]) -> None:
        """Open the generator with the R06 plan and actual observed machine."""
        workspace = self.blueprint_workspace()
        studio = workspace.studio
        studio.designer.load_plan(plan)
        self.show_workspace("Blueprint Studio")
        studio.tabs.setCurrentWidget(studio.designer)
        workspace._message("R06 production plan sent to blueprint creator. "
                           "The generated layout is a draft, not a connected factory.")

    def request_catalog_refresh(self) -> bool:
        """Ask the observer for the first page of the observed catalog.

        The request is handed to the observation worker thread. The
        interface never waits for the game, and the rows that are already
        shown stay visible until the new page arrives.
        """
        bridge = self._bridge
        if bridge is None:
            return False
        self._catalog_requested = True
        self._catalog_recovery_pending = False
        return bool(bridge.request_catalog(1, page_size=128, refresh=True))

    def request_catalog_more(self) -> bool:
        """Ask the observer for the next page of the observed catalog."""
        bridge = self._bridge
        if bridge is None:
            return False
        widget = self.catalog_widget()
        assembly = widget.assembly
        loaded = len(assembly.pages_loaded) if assembly else 0
        snapshot = widget.snapshot
        if snapshot is not None and snapshot.page:
            loaded = max(loaded, snapshot.page)
        return bool(bridge.request_catalog(loaded + 1,
                    page_size=widget.pager.page_size if widget.pager else 16))

    def _publish_frame(self, frame: UiFrame) -> None:
        """Emit one frame from the worker thread.

        The signal is emitted with a **queued** connection, so the frame is
        handled on the UI thread rather than on the worker.
        """
        self.frameArrived.emit(frame)

    def _report_observation_error(self, error: BaseException) -> None:
        """Report a failed observation without stopping the dashboard."""
        self.observationError.emit(f"{type(error).__name__}: {error}")

    def stop_observations(self, timeout: float = 5.0) -> None:
        """Stop the observation bridge and release its service."""
        bridge = self._bridge
        self._bridge = None
        if bridge is not None:
            try:
                self.frameArrived.disconnect(self.apply_ui_frame)
            except (RuntimeError, TypeError):
                # The signal may already be disconnected.
                pass
            bridge.stop(timeout)

    def closeEvent(self, event: Any) -> None:
        """Stop the observation worker before the window closes.

        The worker thread is a daemon, but it is stopped explicitly so the
        service's worker pool is released and the game is not polled after
        the window has gone.
        """
        if self._local_observer is not None:
            self._local_observer.stop()
            self._local_observer = None
            self._bridge = None
        else:
            self.stop_observations()
        super().closeEvent(event)


__all__ = [
    "DEFAULT_METRIC_TTL",
    "IMPLEMENTED_WORKSPACES",
    "METRIC_NAMES",
    "WORKSPACES",
    "MetricState",
    "NavigationRail",
    "ShellWindow",
]
