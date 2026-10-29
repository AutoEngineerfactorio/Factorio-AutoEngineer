"""The profile bar: the selected profile and the game controls.

This is the strip the dashboard shows above the workspace. It carries the
three things the user needs at a glance:

* **which profile is selected**, and its game version;
* **the real state of the game** — running, owned by AutoEngineer, or
  running outside AutoEngineer;
* the **launch and stop** controls.

The controls reflect the **verified** process state, never an assumption.
A button is enabled only when the action behind it can actually run:

* **Launch** is enabled only when a profile is selected, the game is not
  running and no other Factorio instance exists.
* **Stop** is enabled only when the game is running *and* AutoEngineer
  started it. A game the user started by hand is never stopped.

The launch and the stop need an explicit confirmation, because both
change the running state of the user's game. The confirmation is a
question the user answers; it is not a setting that can be forgotten.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Protocol

from factorio_profiles import ProfileError, ProfileManager
from factorio_session import GameSession, SessionError

qt = import_module("PySide6.QtCore")
w = import_module("PySide6.QtWidgets")

QWidget, QFrame = w.QWidget, w.QFrame
QLabel, QPushButton = w.QLabel, w.QPushButton
QHBoxLayout = w.QHBoxLayout
Qt = qt.Qt


class SessionLike(Protocol):
    """The part of a game session the profile bar uses.

    The narrow protocol keeps the bar testable: the tests substitute a
    fake and no Factorio process is ever started.
    """

    def state(self) -> Any:
        ...

    def launch(self, *, confirm: bool = False) -> Any:
        ...

    def stop(self, *, confirm: bool = False) -> Any:
        ...


def label(text: str, object_name: str = "muted") -> Any:
    """Return a themed label."""
    result = QLabel(text)
    result.setObjectName(object_name)
    return result


class ProfileBar(QFrame):
    """The profile selector and the game controls.

    The bar owns no transport: it asks the ``ProfileManager`` and the
    ``GameSession`` for the state and it renders exactly what they say.
    """

    def __init__(
        self,
        manager: ProfileManager | None = None,
        *,
        session_factory: Callable[[Any], SessionLike] | None = None,
        confirm: Callable[[str], bool] | None = None,
        on_game_launched: Callable[[], None] | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager if manager is not None else ProfileManager()
        self.session_factory: Callable[[Any], SessionLike] = (
            session_factory or (lambda profile: GameSession(profile)))
        #: The confirmation the user has to answer. The default answers
        #: "no", so a bar that was wired without a confirmation never
        #: starts or stops a game.
        self.confirm = confirm or (lambda question: False)
        self.on_game_launched = on_game_launched
        self.session: SessionLike | None = None
        #: The profile the current session belongs to. A reload keeps the
        #: session as long as the profile did not change.
        self.session_profile: str | None = None
        self._build()
        self.reload()

    # -- construction ----------------------------------------------------

    def _build(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        layout.addWidget(label("Profile", "muted"))
        self.profile = label("No profile selected", "headerValue")
        self.profile.setMinimumWidth(200)
        layout.addWidget(self.profile)

        self.version = label("—", "muted")
        layout.addWidget(self.version)

        self.state = label("Game not running", "muted")
        layout.addWidget(self.state)

        layout.addStretch()

        self.launch_button = QPushButton("Launch game")
        self.launch_button.setObjectName("positive")
        self.launch_button.setCursor(Qt.PointingHandCursor)
        self.launch_button.clicked.connect(self.launch)
        layout.addWidget(self.launch_button)

        self.stop_button = QPushButton("Stop game")
        self.stop_button.setObjectName("danger")
        self.stop_button.setCursor(Qt.PointingHandCursor)
        self.stop_button.clicked.connect(self.stop)
        layout.addWidget(self.stop_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setObjectName("tool")
        self.settings_button.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.settings_button)

        self.feedback = label("", "faint")
        layout.addWidget(self.feedback)

    # -- state -----------------------------------------------------------

    def reload(self) -> None:
        """Read the manager and the session and show the real state.

        The manager's current selection is used. Only when nothing is
        selected yet is the stored selection restored, so a reload never
        undoes the selection the user just made.

        The session is **reused** for the profile it was created for. A
        reload that replaced it would throw away the owned process of a
        running game, and the bar would then report a game it no longer
        controls.
        """
        identifier = self.manager.selected
        if identifier is None:
            identifier = self.manager.restore_selection()
        if identifier is None:
            self.profile.setText("No profile selected")
            self.version.setText("—")
            self.state.setText("Game not running")
            self.session = None
            self._update_buttons()
            return
        try:
            profile = self.manager.load(identifier)
        except ProfileError as error:
            self.profile.setText(f"Profile unreadable: {error}")
            self.version.setText("—")
            self.session = None
            self._update_buttons()
            return
        self.profile.setText(profile.name)
        self.version.setText(
            f"Factorio {profile.game_version or 'unknown'}")
        if self.session is None or self.session_profile != identifier:
            self.session = self.session_factory(profile)
            self.session_profile = identifier
        state = self.session.state()
        if state.running and state.owned:
            self.state.setText("Game running (started by AutoEngineer)")
        elif state.running:
            self.state.setText("Game running (started outside AutoEngineer)")
        else:
            self.state.setText("Game not running")
        self._update_buttons(state)

    def _update_buttons(self, state: Any = None) -> None:
        """Enable the buttons only when the action can really run."""
        if state is None:
            state = self.session.state() if self.session is not None else None
        running = bool(state.running) if state is not None else False
        owned = bool(state.owned) if state is not None else False
        has_profile = self.session is not None
        self.launch_button.setEnabled(has_profile and not running)
        self.stop_button.setEnabled(has_profile and running and owned)
        if not has_profile:
            self.launch_button.setToolTip("Select a profile first")
            self.stop_button.setToolTip("Select a profile first")
        elif running and not owned:
            self.launch_button.setToolTip(
                "A Factorio instance is already running")
            self.stop_button.setToolTip(
                "The running instance was not started by AutoEngineer and is "
                "left alone")
        else:
            self.launch_button.setToolTip("Start the game for this profile")
            self.stop_button.setToolTip("Stop the game AutoEngineer started")

    # -- actions ---------------------------------------------------------

    def launch(self) -> None:
        """Start the game of the selected profile, after a confirmation."""
        if self.session is None:
            self.feedback.setText("Select a profile first.")
            return
        if not self.confirm(
                f"Start Factorio for the profile {self.profile.text()}?"):
            self.feedback.setText("The game was not started.")
            return
        try:
            state = self.session.launch(confirm=True)
        except SessionError as error:
            self.feedback.setText(f"The game was not started: {error}")
            self.reload()
            return
        self.feedback.setText(state.detail)
        if self.on_game_launched is not None:
            self.on_game_launched()
        self.reload()

    def stop(self) -> None:
        """Stop the game AutoEngineer started, after a confirmation."""
        if self.session is None:
            self.feedback.setText("Select a profile first.")
            return
        if not self.confirm(
                "Stop the game? The game saves before it is closed."):
            self.feedback.setText("The game was not stopped.")
            return
        try:
            state = self.session.stop(confirm=True)
        except SessionError as error:
            self.feedback.setText(f"The game was not stopped: {error}")
            self.reload()
            return
        self.feedback.setText(state.detail)
        self.reload()
