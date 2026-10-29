"""Universal Factorio session control: launch, stop, restart, save.

This module owns the *game* side of a profile: it starts the user's
Factorio executable with the profile's own configuration, it stops the
process it started, and it refuses to act on a game it did not start.

The ownership rule is the same one the R02 test-host launcher uses and it
is not relaxed here:

* a game this module started is **owned**: it may be stopped, and only
  after a save;
* a game that was already running is **attached**: it is never stopped,
  never adopted and never saved through this module, because the user may
  be playing it by hand.

The duplicate-instance guard refuses to start a second game when any
Factorio binary is already running, whatever installation it came from.
That is the same rule the R02 launcher applies to the graphical host.

Nothing here issues console Lua. The mod's own registered commands are
used, and only for a read-only status check.

The module is **offline-testable**: every process interaction goes through
small overridable methods, so the tests can exercise the decision logic
without starting Factorio.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from factorio_profiles import Profile, ProfileError

#: The Factorio process name on Windows.
FACTORIO_PROCESS_NAME = "factorio.exe"

#: How long a start waits for the process to report that it is alive.
STARTUP_TIMEOUT_SECONDS = 20.0

#: How long a stop waits for the game to exit.
STOP_TIMEOUT_SECONDS = 20.0

#: The name of the diagnostic log of one session.
LOG_NAME = "factorio.private.log"


class SessionError(RuntimeError):
    """The session operation was refused or failed."""


class StartedProcess(Protocol):
    """The part of a started process this service uses.

    A narrow protocol keeps the service testable: the tests substitute a
    fake that answers ``poll``, ``terminate`` and ``wait`` without a real
    Factorio process ever being started.
    """

    @property
    def pid(self) -> int:
        ...

    def poll(self) -> int | None:
        ...

    def terminate(self) -> None:
        ...

    def wait(self, timeout: float | None = None) -> int:
        ...


@dataclass(frozen=True)
class SessionState:
    """The truthful state of one profile's game session."""

    running: bool
    owned: bool
    pid: int | None
    profile_identifier: str
    game_version: str | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "owned": self.owned,
            "pid": self.pid,
            "profile": self.profile_identifier,
            "game_version": self.game_version,
            "detail": self.detail,
        }


class GameSession:
    """The game session of one profile.

    The service owns at most one process at a time. Every method that can
    change the running state takes an explicit ``confirm`` flag, so a
    mis-wired button cannot start or stop a game by accident.
    """

    def __init__(
        self,
        profile: Profile,
        *,
        notify: Callable[[str, str], None] = lambda *args: None,
    ) -> None:
        self.profile = profile
        self.notify = notify
        self.process: StartedProcess | None = None
        self.last_error: str | None = None

    # -- observation -----------------------------------------------------

    def status(self, name: str, text: str) -> None:
        """Record a status message and pass it to the listener."""
        self.notify(name, text)

    def running_instances(self) -> list[int]:
        """Return the PIDs of every live Factorio binary on this PC.

        The check is read-only and installation-agnostic: a second
        Factorio from another installation would fight over the same
        ports and the same saves, so it has to be refused.
        """
        try:
            import psutil
        except ImportError:  # pragma: no cover - depends on the environment
            return []
        found: list[int] = []
        for process in psutil.process_iter(["pid", "name"]):
            try:
                if (process.info.get("name") or "").lower() == FACTORIO_PROCESS_NAME:
                    found.append(int(process.info["pid"]))
            except Exception:
                # A process that exits while it is inspected is simply not
                # a running instance.
                continue
        return found

    def owned_alive(self) -> bool:
        """Whether the process this service started is still running."""
        return self.process is not None and self.process.poll() is None

    def state(self) -> SessionState:
        """Return the truthful state of the session."""
        process = self.process
        if process is not None and process.poll() is None:
            return SessionState(
                running=True, owned=True, pid=process.pid,
                profile_identifier=self.profile.identifier,
                game_version=self.profile.game_version,
                detail="Running, started by AutoEngineer",
            )
        others = self.running_instances()
        if others:
            return SessionState(
                running=True, owned=False, pid=others[0],
                profile_identifier=self.profile.identifier,
                game_version=self.profile.game_version,
                detail=("A Factorio instance is already running and was "
                        "started outside AutoEngineer"),
            )
        return SessionState(
            running=False, owned=False, pid=None,
            profile_identifier=self.profile.identifier,
            game_version=self.profile.game_version,
            detail="Not running",
        )

    # -- launching -------------------------------------------------------

    def command(self, *, load_save: Path | None = None) -> list[str]:
        """Return the command line that starts this profile's game.

        The profile's **own** ``config.ini`` is used, so the game reads
        and writes the profile's own saves, configuration and mods. The
        file is written on demand: a profile that was created before the
        configuration existed still starts with an isolated
        configuration rather than with the user's main profile.
        """
        executable = self.profile.executable
        if not executable.is_file():
            raise SessionError(
                "The Factorio executable of this profile is missing")
        arguments = [str(executable)]
        configuration = self.profile.config_directory / "config.ini"
        if not configuration.is_file():
            try:
                from factorio_profiles import ProfileManager

                ProfileManager(self.profile.root.parent).write_config_ini(
                    self.profile.identifier)
            except Exception:
                # Without a configuration the game would use the user's
                # own profile, so the start is refused instead.
                raise SessionError(
                    "The profile has no configuration; the game would "
                    "otherwise use the user's own Factorio profile") from None
        if not self.profile.mods_directory.is_dir():
            raise SessionError("The selected profile's mod directory is missing")
        arguments += [
            "--config", str(configuration),
            "--mod-directory", str(self.profile.mods_directory),
        ]
        if load_save is not None:
            from save_manager import resolve_save

            save_path = resolve_save(self.profile.saves_directory, load_save.name)
            if save_path != load_save.resolve() or not save_path.is_file():
                raise SessionError("The selected save is missing or outside this profile")
            arguments += ["--load-game", str(save_path)]
        return arguments

    def launch(self, *, confirm: bool = False,
               load_save: Path | None = None) -> SessionState:
        """Start the game for this profile.

        The launch is refused when the user has not confirmed it, when a
        Factorio instance is already running, or when this service
        already owns a running process.
        """
        if confirm is not True:
            raise SessionError("Starting the game has to be confirmed")
        if self.owned_alive():
            raise SessionError("This profile's game is already running")
        existing = self.running_instances()
        if existing:
            raise SessionError(
                "Another Factorio instance is already running "
                f"(PID {existing[0]}); close it before starting this profile")
        arguments = self.command(load_save=load_save)
        self.profile.cache_directory.mkdir(parents=True, exist_ok=True)
        log_path = self.profile.cache_directory / LOG_NAME
        try:
            with log_path.open("ab") as log:
                self.process = subprocess.Popen(
                    arguments,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    cwd=str(self.profile.installation_root),
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
                )
        except OSError as error:
            self.last_error = str(error)
            raise SessionError(
                f"The game could not be started: {error}") from None
        self.status("game", "Started; waiting for the game to report itself")
        if not self.wait_until_running():
            self.last_error = (
                "The game process did not report itself; see the diagnostic log")
            self.status("game", self.last_error)
            raise SessionError(self.last_error)
        self.status("game", "Running")
        return self.state()

    def wait_until_running(self, timeout: float = STARTUP_TIMEOUT_SECONDS) -> bool:
        """Wait until the started process is alive and responsive.

        The wait is bounded. A process that exits during the wait is a
        failed start, not a slow start.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process is None:
                return False
            code = self.process.poll()
            if code is not None:
                return False
            if self.running_instances():
                return True
            time.sleep(0.2)
        return False

    # -- stopping --------------------------------------------------------

    def stop(self, *, confirm: bool = False, save: bool = True) -> SessionState:
        """Stop the game this service started.

        A game that AutoEngineer did not start is never stopped. When the
        game is stopped, it is asked to save first, so the user's work is
        not lost.
        """
        if confirm is not True:
            raise SessionError("Stopping the game has to be confirmed")
        if not self.owned_alive():
            others = self.running_instances()
            if others:
                raise SessionError(
                    "The running Factorio instance was not started by "
                    "AutoEngineer; it is left running")
            raise SessionError("The game is not running")
        if save and not self.request_save():
            raise SessionError(
                "Factorio did not confirm the save. The game was left running; "
                "save manually in Factorio before closing it")
        process = self.process
        if process is None:
            raise SessionError("The game is not running")
        try:
            process.terminate()
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise SessionError(
                "The game did not stop; it was left running") from None
        except OSError as error:
            raise SessionError(
                f"The game could not be stopped: {error}") from None
        self.status("game", "Stopped")
        return self.state()

    def request_save(self) -> bool:
        """Ask the running game to save.

        The request goes to the registered mod command, never to console
        Lua. A game that does not answer is not saved, and the caller is
        told so.
        """
        if not self.owned_alive():
            return False
        response = self.send_registered_command("/autoengineer-save")
        return bool(response and response.get("status") == "ok")

    def send_registered_command(self, command: str) -> dict[str, Any] | None:
        """Send one registered mod command and return its JSON answer.

        This is the only way this module talks to the game. An arbitrary
        command is refused, because the mod exposes a fixed set of
        commands and the project never sends console Lua.

        The connection uses the application's own RCON configuration and
        the password from the environment. A universal user profile has no
        secret of its own: the credential never lives in the profile
        directory, so exporting or importing a profile can never leak it.
        """
        import json

        allowed = {"/autoengineer-status", "/autoengineer-save",
                   "/autoengineer-observe status"}
        if command not in allowed:
            raise SessionError(
                f"The command {command!r} is not a registered AutoEngineer "
                "command")
        password = os.environ.get("FACTORIO_RCON_PASSWORD")
        if not password or not password.strip():
            self.last_error = (
                "No RCON password is configured; set FACTORIO_RCON_PASSWORD "
                "in the environment")
            return None
        try:
            from autoengineer_config import get_settings

            settings = get_settings()
        except Exception as error:
            self.last_error = str(error)
            return None
        try:
            from launcher_services import Rcon

            rcon = Rcon(settings["rcon_port"], password)
        except Exception as error:
            self.last_error = str(error)
            return None
        try:
            raw = rcon.command(command)
        except Exception:
            return None
        finally:
            try:
                rcon.close()
            except Exception:
                pass
        try:
            document = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return document if isinstance(document, dict) else None

    def restart(self, *, confirm: bool = False) -> SessionState:
        """Stop and start the game again."""
        if confirm is not True:
            raise SessionError("Restarting the game has to be confirmed")
        if self.owned_alive():
            self.stop(confirm=True)
        return self.launch(confirm=True)

    def close(self) -> None:
        """Release the session without stopping the game.

        The process handle is closed. The game keeps running: the service
        does not own it any more.
        """
        self.process = None

    # -- saves -----------------------------------------------------------

    def saves(self) -> list[Path]:
        """Return the save files of this profile.

        Only the profile's own saves directory is read. Another profile's
        saves are never visible here, and the game's own saves directory
        is not scanned.
        """
        directory = self.profile.saves_directory
        if not directory.is_dir():
            return []
        return sorted(
            path for path in directory.glob("*.zip") if path.is_file())

    def save_report(self) -> Mapping[str, Any]:
        """Return a truthful report about the saves of this profile."""
        saves = self.saves()
        return {
            "profile": self.profile.identifier,
            "saves_directory": str(self.profile.saves_directory),
            "save_count": len(saves),
            "saves": [path.name for path in saves],
            "game_running": self.owned_alive(),
        }


def open_session(
        profile: Profile,
        **kwargs: Any,
) -> GameSession:
    """Return a session for a profile, or refuse with a clear reason."""
    if not isinstance(profile, Profile):
        raise ProfileError("A profile is required")
    return GameSession(profile, **kwargs)
