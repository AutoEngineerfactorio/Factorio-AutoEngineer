"""The persistent R06 live test environment.

The previous R06 live harness created a **fresh, empty client profile for
every run** and launched a **new Factorio server for every run**. That is what
produced the repeated "the user has to sign in again" symptom:

* A fresh client profile has an **empty** ``service-token`` in its
  ``player-data.json``. The client therefore cannot authenticate silently and
  must perform a full ``api-login`` against ``auth.factorio.com``.
* A headless client has no way to satisfy the interactive Factorio account
  sign-in that a fresh login needs, so the re-authentication either takes
  hundreds of seconds of retry backoff or stalls entirely.
* A Factorio server always refuses the **first** connection request with
  ``UserVerificationMissing`` because that request carries no user-verification
  key. This is normal, expected multiplayer behaviour, not a fault: the client
  is expected to authenticate and then reconnect with the key.

This module replaces that per-run profile with **one persistent test
environment**:

* a **reusable client profile** whose ``player-data.json`` is seeded once from
  the already-authenticated launcher profile and is then reused and refreshed
  in place, so no run ever needs a fresh sign-in;
* **server reuse**: an already-running test server is detected through a
  bounded RCON health check and reused instead of being relaunched;
* **bounded polling** against real server, RCON and log state, with an
  explicit, meaningful reason for every timeout.

Safety contract:

* The persistent profile lives inside the isolated test base directory and
  never touches the user's own Factorio installation.
* Only the **authentication** state (``service-token`` and
  ``service-username``) is copied out of the launcher profile. No other
  player state, and no credential value is ever logged.
* The module never launches Factorio by itself; the caller owns the process
  lifecycle. This module only prepares configuration and observes state.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local" / "live-pillow-2.1.23"

#: The isolated 2.1.23 executable. The directory is still named
#: ``Factorio_2.1.22``; the version is read from the binary, never the name.
EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")

#: The persistent, authenticated launcher profile. Its ``player-data.json``
#: carries a valid ``service-token`` and is the source of the seeded client
#: authentication state.
LAUNCHER_PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"

#: The persistent client profile. Unlike the old per-run directory this is
#: **not** deleted at the end of a run, so the authentication state survives.
CLIENT_PROFILE = BASE / "client-profile"

#: The persistent server write-data directory. The base config points at it,
#: so the server's own log is always written here and a reused server's log
#: can be found.
SERVER_PROFILE = BASE / "server-profile"

#: The server's write-data directory, taken from the base configuration.
SERVER_DATA = BASE / "server" / "data"

#: Where the per-run evidence (logs, reports, disposable saves) is written.
#: This directory is disposable; the persistent profiles are not.
EVIDENCE = BASE / "evidence"

#: The working directory the restricted backend is hosted from. The backend
#: resolves its own state files relative to this directory.
BACKEND_RUNTIME = BASE / "backend-runtime"

#: The mod suite used by the modded (Pyanodons) profile.
MODS = ROOT / ".local" / "mod-test-mods" / "2.1.23"

#: The disposable modded save. Never written to.
MODDED_SAVE = (
    ROOT / ".local" / "launcher-profiles" / "2.1.23" / "data" / "saves"
    / "autoengineer-py-fresh-20261028.zip"
)

#: The RCON bind address. RCON is always bound to localhost.
RCON_HOST = "127.0.0.1"

#: The keys copied out of the launcher profile. Anything else is discarded.
AUTH_KEYS = ("service-token", "service-username")

#: How long a bounded wait for one condition may take, in seconds.
POLL_INTERVAL_SECONDS = 0.5


class EnvironmentError_(RuntimeError):
    """A bounded wait ended without the awaited condition being reached."""


def _read_ini(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def _set_ini(text: str, key: str, value: str) -> str:
    """Replace one ``key=value`` line, preserving the rest of the file."""
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    if not pattern.search(text):
        raise EnvironmentError_(f"the config has no {key} entry to replace")
    return pattern.sub(f"{key}={value}", text)


def port_is_open(host: str, port: int, timeout: float = 0.4) -> bool:
    """Return True when something accepts a TCP connection on the port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def rcon_is_listening(port: int, host: str = RCON_HOST) -> bool:
    """Return True when the RCON port accepts a connection."""
    return port_is_open(host, port)


def read_auth_state(path: Path) -> dict[str, str]:
    """Return the authentication state of a ``player-data.json``.

    Only the presence and the length of each value is reported; the values
    themselves are never returned, so a token can never leak into a log or a
    report through this helper.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    state: dict[str, str] = {}
    for key in AUTH_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            state[key] = f"present:{len(value)}"
        else:
            state[key] = "absent"
    return state


def has_authentication(path: Path) -> bool:
    """Return True when the profile carries a non-empty service token."""
    state = read_auth_state(path)
    return state.get("service-token", "absent").startswith("present:")


def seed_authentication(source: Path, target: Path) -> dict[str, str]:
    """Copy the authentication state from ``source`` into ``target``.

    The copy is **additive and minimal**: only ``service-token`` and
    ``service-username`` are taken. Every other player setting is left at the
    target's own default, so no unrelated player state leaks between profiles.

    An existing non-empty token in the target is **kept**: the target is the
    persistent profile and its token is the one the client actually refreshes.
    """
    source = Path(source)
    target = Path(target)
    if not has_authentication(source):
        raise EnvironmentError_(
            "the launcher profile carries no authentication token, so the "
            "client profile cannot be seeded; sign in once with the normal "
            "Factorio client before running the live harness"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if has_authentication(target):
        return read_auth_state(target)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EnvironmentError_(
            f"the launcher profile could not be read: {type(exc).__name__}"
        ) from exc
    if not isinstance(data, dict):
        raise EnvironmentError_("the launcher profile is not a player-data object")
    seeded = {key: data.get(key) for key in AUTH_KEYS
              if isinstance(data.get(key), str) and data.get(key)}
    target.write_text(json.dumps(seeded, indent=2), encoding="utf-8")
    return read_auth_state(target)


def write_client_config(config_path: Path, base_config: Path,
                        data_dir: Path, rcon_port: int) -> Path:
    """Write the persistent client's ``config.ini``.

    The client gets its **own** ``write-data`` directory. Sharing the
    server's makes the game refuse to start with "Couldn't create lock file".
    """
    config_path = Path(config_path)
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    text = _read_ini(Path(base_config))
    text = _set_ini(text, "write-data", str(data_dir).replace("\\", "/"))
    if rcon_port:
        text = _set_ini(text, "local-rcon-socket", f"{RCON_HOST}:{rcon_port}")
    config_path.write_text(text, encoding="utf-8")
    return config_path


def prepare_client_profile(run_tag: str, base_config: Path,
                            rcon_port: int = 0) -> Path:
    """Prepare the persistent, reusable client profile.

    The profile is **not** removed after a run. Its ``player-data.json`` is
    seeded once from the authenticated launcher profile and is then maintained
    by the game itself, which refreshes the token in place.
    """
    data_dir = CLIENT_PROFILE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    # A lock left behind by a previous run stops the client from starting.
    clear_stale_lock(data_dir)
    seed_authentication(
        LAUNCHER_PROFILE / "data" / "player-data.json",
        data_dir / "player-data.json",
    )
    write_client_config(
        CLIENT_PROFILE / "config.ini",
        base_config,
        data_dir,
        rcon_port,
    )
    return CLIENT_PROFILE


def client_auth_state() -> dict[str, str]:
    """Return the authentication state of the persistent client profile."""
    return read_auth_state(CLIENT_PROFILE / "data" / "player-data.json")


def clear_stale_lock(profile_data: Path) -> bool:
    """Remove a stale ``.lock`` file from a harness-owned profile.

    Factorio refuses to start when its profile's ``.lock`` file exists. The
    lock is only meaningful while the game is running, so a lock left behind
    by a previous run prevents the next client from starting at all.

    Only a **harness-owned** profile may be unlocked. The lock is removed
    only when no Factorio process is using the profile, which the caller has
    already established by not running a client for it.
    """
    lock = Path(profile_data) / ".lock"
    if not lock.is_file():
        return False
    try:
        lock.unlink()
    except OSError:
        return False
    return True


def game_log_path(profile_data: Path) -> Path:
    """Return the log file Factorio writes into a profile.

    Factorio writes its own log into the profile's write-data directory as
    ``factorio-current.log``. The redirected standard output of the process is
    **not** the game's log, so the log is read from the profile.
    """
    return Path(profile_data) / "factorio-current.log"


def read_game_log(profile_data: Path) -> str:
    """Return the text of the profile's current game log."""
    path = game_log_path(profile_data)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


#: The operating modes the restricted backend accepts.
#:
#: ``helper`` is the AI Helper mode. It is read-only: the backend refuses
#: every gameplay write and every lease activation, so no craft can be
#: performed in it. ``semi`` is the supervised mode that permits a bounded
#: gameplay operation under an owned safety lease.
BACKEND_MODES = ("helper", "semi")

#: The tools the AI Helper mode permits. The gameplay write tools and the
#: lease tools are deliberately absent.
HELPER_READ_ONLY_TOOLS = (
    "autoengineer_operation_preview",
    "autoengineer_view",
    "autoengineer_policy",
    "get_player_position",
    "scan_resources",
    "get_nearby_entities",
    "autoengineer_status",
    "autoengineer_stop",
)


def backend_launch_environment(rcon_port: int, password: str,
                               mode: str = "helper") -> dict[str, str]:
    """Build the environment the restricted backend is hosted with.

    The backend is a .NET 9 assembly. It is hosted by the ``dotnet`` muxer,
    which resolves the shared framework through ``DOTNET_ROOT``. That variable
    is **not** set in this environment by default, and the backend then fails
    to load ``System.Runtime`` before it ever connects to RCON. The root is
    therefore derived from the installed ``dotnet`` executable instead of
    being inherited.

    The backend's own state files are placed in its runtime directory, which
    is also its working directory, so the restricted backend never writes
    into the repository root.

    ``mode`` selects the operating mode. The default is the **read-only**
    AI Helper mode. The supervised ``semi`` mode is only used when a test
    explicitly asks for a bounded gameplay operation.
    """
    if mode not in BACKEND_MODES:
        raise ValueError(f"unknown backend operating mode: {mode}")
    keep = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP",
            "DOTNET_ROOT", "USERPROFILE", "APPDATA", "LOCALAPPDATA")
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in keep}
    environment.setdefault("DOTNET_ROOT", dotnet_root())
    environment.update({
        "FACTORIO_RCON_HOST": RCON_HOST,
        "FACTORIO_RCON_PORT": str(rcon_port),
        "FACTORIO_RCON_PASSWORD": password,
        "AUTOENGINEER_BACKEND_MODE": mode,
        "Logging__LogLevel__Default": "None",
        "Logging__LogLevel__Microsoft": "None",
    })
    BACKEND_RUNTIME.mkdir(parents=True, exist_ok=True)
    environment["FACTORIO_GOALS_FILE"] = str(BACKEND_RUNTIME / "goals.json")
    environment["FACTORIO_BUILDINGS_FILE"] = str(BACKEND_RUNTIME / "buildings.json")
    return environment


def dotnet_root() -> str:
    """Return the .NET installation root the backend must be hosted from.

    The root is derived from the ``dotnet`` executable on ``PATH``. When it
    cannot be derived the environment variable is used, and the empty string
    is returned when neither is available so the caller can report a clear
    failure instead of a confusing assembly-load error.
    """
    existing = os.environ.get("DOTNET_ROOT", "").strip()
    if existing:
        return existing
    path = os.environ.get("PATH", "")
    for entry in path.split(os.pathsep):
        candidate = Path(entry.strip().strip('"')) / "dotnet.exe"
        if candidate.is_file():
            return str(candidate.parent)
    return ""


@dataclass
class WaitResult:
    """The outcome of one bounded wait."""

    ok: bool
    reason: str
    waited_seconds: float = 0.0
    detail: str = ""


def wait_for(predicate, timeout: float, description: str,
             poll_interval: float = POLL_INTERVAL_SECONDS) -> WaitResult:
    """Poll ``predicate`` until it is true, the timeout expires or the
    condition is reported as impossible.

    ``predicate`` returns either a truthy value (the wait succeeded) or a
    string (the wait failed with that reason) or ``None`` (keep waiting).
    The wait is always bounded and always reports why it ended.
    """
    started = time.monotonic()
    deadline = started + timeout
    last: object = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
        except Exception as exc:  # noqa: BLE001 - the wait must not mask errors
            return WaitResult(False, f"{description} raised {type(exc).__name__}",
                              time.monotonic() - started)
        if isinstance(result, str):
            return WaitResult(False, result, time.monotonic() - started)
        if result:
            return WaitResult(True, description, time.monotonic() - started,
                              str(last) if last is not None else "")
        last = result
        time.sleep(poll_interval)
    return WaitResult(
        False,
        f"{description} did not happen within {timeout:.0f}s",
        time.monotonic() - started,
    )


def server_is_healthy(rcon_port: int, host: str = RCON_HOST) -> bool:
    """Return True when a Factorio RCON endpoint is accepting connections."""
    return rcon_is_listening(rcon_port, host)


def discover_running_server(rcon_port: int, host: str = RCON_HOST) -> bool:
    """Return True when a test server is already serving RCON on the port."""
    return server_is_healthy(rcon_port, host)


def prepare_server_config(run_tag: str, base_config: Path, rcon_port: int,
                          password: str) -> Path:
    """Write a per-run server ``config.ini`` with the run's RCON settings."""
    text = _read_ini(Path(base_config))
    text = _set_ini(text, "local-rcon-socket", f"{RCON_HOST}:{rcon_port}")
    text = _set_ini(text, "local-rcon-password", password)
    path = BASE / "server-profile" / f"{run_tag}-config.ini"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@dataclass
class ServerSession:
    """The state of the Factorio server the live tests run against."""

    rcon_port: int
    game_port: int
    password: str
    reused: bool = False
    pid: int | None = None
    log_path: Path | None = None
    started_at: float = field(default_factory=time.monotonic)

    def age_seconds(self) -> float:
        return time.monotonic() - self.started_at


def copy_disposable_save(source: Path, run_tag: str,
                         destination: Path | None = None) -> Path:
    """Copy the source save to a disposable per-run file.

    The source save is opened read-only and never written back. The
    destination defaults to the evidence directory.
    """
    target = Path(destination) if destination is not None else (
        EVIDENCE / f"{run_tag}-save.zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(source), target)
    return target


def rcon_secret_path() -> Path:
    """Return the path of the environment's persistent RCON secret."""
    return BASE / "rcon.secret.json"


def rcon_password() -> str:
    """Return the environment's persistent RCON password.

    The password belongs to the **environment**, not to a run. A server that
    is reused across runs was started with the password that was current
    then, so a per-run password would make the reused server unreachable
    ("RCON authentication failed").

    The secret is created once and then reused. It is never printed and
    never written into a report.
    """
    path = rcon_secret_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}
        password = data.get("rcon_password")
        if isinstance(password, str) and password:
            return password
    password = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rcon_password": password}), encoding="utf-8")
    return password
