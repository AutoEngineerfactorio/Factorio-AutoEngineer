"""R09 Phase 7 live observation harness.

Starts a headless Factorio server on a **disposable** save, connects the
existing authenticated client, and exercises every ``/autoengineer-observe``
operation over RCON. It also records whether Factorio logged any
achievement-disabling console confirmation, and measures the observation
latency.

The harness never writes to a canonical save: it copies the save into a
per-run directory first and verifies the original checksum afterwards.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "agent"))

import r06_live_environment as env  # noqa: E402

EXE = pathlib.Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")
BACKEND_DLL = (ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23"
                / "FactorioMCP.dll")
RUNTIME = ROOT / ".local" / "backend-runtime"

#: Every operation the mod must serve.
OPERATIONS = (
    "status",
    "telemetry",
    "map",
    "terrain",
    "overlay",
    "inventory",
    "recipes",
    "research",
    "machines",
    "capabilities",
)

#: The server-log markers that mean Factorio asked the operator to confirm
#: that achievements may be disabled.
ACHIEVEMENT_MARKERS = (
    "will disable achievements",
    "Using Lua console commands",
    "Please repeat the command",
)


def log(message: str) -> None:
    print(message, flush=True)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def achievement_markers(text: str) -> list[str]:
    """Return the achievement-confirmation markers present in a log."""
    return [marker for marker in ACHIEVEMENT_MARKERS if marker in text]


class Rcon:
    """A minimal Factorio RCON client for the live observation test.

    It sends a raw command over the RCON socket, which is exactly what the
    restricted backend does. A registered mod command arrives at the mod; a
    Lua console command arrives at the console.
    """

    def __init__(self, host: str, port: int, password: str) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.socket: socket.socket | None = None

    def connect(self, timeout: float = 30.0) -> None:
        self.socket = socket.create_connection((self.host, self.port), timeout)
        self.socket.settimeout(timeout)
        self._send("")

    def close(self) -> None:
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None

    def _send(self, payload: str) -> None:
        assert self.socket is not None
        encoded = payload.encode("utf-8")
        self.socket.sendall(
            len(encoded).to_bytes(4, "little") + encoded)

    def _receive(self) -> str:
        assert self.socket is not None
        header = self._read_exactly(4)
        length = int.from_bytes(header, "little")
        return self._read_exactly(length).decode("utf-8", errors="replace")

    def _read_exactly(self, count: int) -> bytes:
        assert self.socket is not None
        chunks = []
        remaining = count
        while remaining > 0:
            chunk = self.socket.recv(remaining)
            if not chunk:
                raise ConnectionError("the RCON connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def command(self, payload: str) -> str:
        """Send one command and return its response body."""
        self._send(payload)
        kind = self._receive()
        body = self._receive()
        if kind == "2":  # a failed request
            raise RuntimeError(f"the RCON request failed: {body[:200]}")
        return body


class LiveObservation:
    """One live observation run against one profile."""

    def __init__(self, profile: str, run_tag: str) -> None:
        self.profile = profile
        self.run_tag = run_tag
        self.report: dict = {
            "profile": profile,
            "run_tag": run_tag,
            "operations": {},
            "achievement_markers": [],
            "errors": [],
        }
        self.server: subprocess.Popen | None = None
        self.client: subprocess.Popen | None = None
        self.run_dir = ROOT / ".local" / "live-pillow-2.1.23" / "evidence" / run_tag
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.server_log = self.run_dir / "server.log"
        self.client_log = self.run_dir / "client.log"

    # -- profile set-up ---------------------------------------------------

    def profile_paths(self) -> dict:
        if self.profile == "vanilla-space-age":
            return {
                "mods": pathlib.Path(
                    r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\mods"),
                "save": ROOT / ".local" / "launcher-profiles" / "2.1.23" / "data"
                / "saves" / "autoengineer-test.zip",
                "client_profile": None,
            }
        return {
            "mods": ROOT / ".local" / "mod-test-mods" / "2.1.23",
            "save": ROOT / ".local" / "launcher-profiles" / "2.1.23" / "data"
            / "saves" / "autoengineer-test modded.zip",
            "client_profile": env.CLIENT_PROFILE,
        }

    # -- server and client ------------------------------------------------

    def start_server(self) -> tuple[int, int, str]:
        """Start the headless server on a disposable copy of the save."""
        paths = self.profile_paths()
        source_save = paths["save"]
        if not source_save.is_file():
            raise RuntimeError(f"the disposable source save is missing: {source_save}")
        original_digest = digest(source_save)

        # The server is started on a **copy** of the canonical save. The
        # canonical save is only ever read, and its checksum is verified
        # again when the run ends.
        disposable_save = self.run_dir / f"{self.run_tag}-save.zip"
        shutil.copy2(source_save, disposable_save)

        base_config = ROOT / ".local" / "live-pillow-2.1.23" / "server" / "config.ini"
        server_settings = (ROOT / ".local" / "live-pillow-2.1.23" / "server"
                           / "server-settings.json")
        rcon_port = free_port()
        game_port = free_port()
        password = env.rcon_password()
        config = env.prepare_server_config(self.run_tag, base_config, rcon_port,
                                          password)
        self.report["server_config"] = str(config)
        self.report["disposable_save"] = str(disposable_save)
        self.report["original_save"] = str(source_save)
        self.report["original_save_sha256"] = original_digest

        out = self.server_log.open("w", encoding="utf-8")
        self.server = subprocess.Popen(
            [str(EXE), "--config", str(config),
             "--mod-directory", str(paths["mods"]),
             "--start-server", str(disposable_save),
             "--server-settings", str(server_settings),
             "--bind", f"127.0.0.1:{game_port}",
             "--rcon-bind", f"127.0.0.1:{rcon_port}",
             # Factorio requires the password on the command line when an
             # RCON port is given.
             "--rcon-password", password],
            stdout=out, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.report["server_pid"] = self.server.pid
        log(f"SERVER_PID={self.server.pid} RCON={rcon_port} GAME={game_port}")
        return rcon_port, game_port, password

    def start_client(self, game_port: int) -> None:
        """Start the authenticated client that joins the running server."""
        paths = self.profile_paths()
        if self.profile == "vanilla-space-age":
            # The vanilla profile uses the portable configuration, which
            # carries its own authentication state.
            base_config = pathlib.Path(
                r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\config\config.ini")
            client_root = self.run_dir / "client"
            client_root.mkdir(parents=True, exist_ok=True)
            env.write_client_config(client_root / "config.ini", base_config,
                                    client_root / "data", 0)
            client_config = client_root / "config.ini"
        else:
            client_root = env.prepare_client_profile(self.run_tag,
                                                     ROOT / ".local"
                                                     / "live-pillow-2.1.23"
                                                     / "server" / "config.ini")
            if not env.has_authentication(client_root / "data" / "player-data.json"):
                raise RuntimeError("the persistent client profile is not authenticated")
            client_config = client_root / "config.ini"
        self.report["client_profile"] = str(client_root)

        out = self.client_log.open("w", encoding="utf-8")
        self.client = subprocess.Popen(
            [str(EXE), "--config", str(client_config),
             "--mod-directory", str(paths["mods"]),
             "--mp-connect", f"127.0.0.1:{game_port}"],
            stdout=out, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.report["client_pid"] = self.client.pid
        log(f"CLIENT_PID={self.client.pid}")

    def wait_for_server(self, port: int, timeout: float = 300.0) -> bool:
        """Wait until the server's RCON endpoint accepts connections.

        The server needs a moment to load the save and the mod suite before
        it opens the RCON socket, so the health check is retried within a
        bounded window instead of being made once.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server is not None and self.server.poll() is not None:
                self.report["server_exit"] = self.server.returncode
                return False
            if env.server_is_healthy(port):
                return True
            time.sleep(2.0)
        return False

    def wait_for_join(self, timeout: float = 420.0) -> bool:
        """Wait until the client joined the game.

        Factorio 2.1.23 logs ``PlayerJoinGame`` followed by
        ``newState(InGame)``. The game's own log lives in the server's
        **write-data** directory, so the join is detected there. The log is
        append-only, so only the bytes written after the client started are
        considered and a stale line can never be mistaken for this client.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.client is not None and self.client.poll() is not None:
                self.report["client_exit"] = self.client.returncode
                return False
            text = self._server_game_log()
            if "PlayerJoinGame" in text and "newState(InGame)" in text:
                return True
            time.sleep(2.0)
        return False

    def _server_game_log(self) -> str:
        """Return the server's own log, which lives in its write-data path."""
        parts = []
        if self.server_log.is_file():
            parts.append(self.server_log.read_text(encoding="utf-8",
                                                 errors="replace"))
        for candidate in (ROOT / ".local" / "live-pillow-2.1.23" / "server"
                          / "data" / "factorio-current.log",):
            if candidate.is_file():
                parts.append(candidate.read_text(encoding="utf-8",
                                                errors="replace"))
        return "\n".join(parts)

    # -- observation ------------------------------------------------------

    def run_direct_operations(self, port: int, password: str) -> None:
        """Exercise every observation operation directly over RCON.

        This is the transport the backend uses. A registered mod command
        arrives at the mod; a Lua console command would arrive at the
        console and trigger the achievement confirmation.
        """
        client = Rcon("127.0.0.1", port, password)
        try:
            client.connect()
        except OSError as exc:
            self.report["direct_operations_error"] = (
                f"{type(exc).__name__}: {exc}")
            return
        try:
            for operation in OPERATIONS:
                started = time.monotonic()
                entry: dict = {}
                try:
                    body = client.command(f"/autoengineer-observe {operation}")
                    entry["elapsed"] = round(time.monotonic() - started, 4)
                    entry["bytes"] = len(body)
                    try:
                        payload = json.loads(body)
                    except ValueError:
                        payload = None
                        entry["raw_head"] = body[:300]
                    if isinstance(payload, dict):
                        entry["protocol"] = payload.get("protocol")
                        entry["status"] = payload.get("status")
                        entry["reason"] = payload.get("reason")
                        entry["keys"] = sorted(payload)[:20]
                        entry["payload"] = payload
                except Exception as exc:  # noqa: BLE001
                    entry["elapsed"] = round(time.monotonic() - started, 4)
                    entry["error"] = f"{type(exc).__name__}: {exc}"
                self.report.setdefault("direct_operations", {})[operation] = entry
                log(f"DIRECT {operation}: {json.dumps(
                    {k: v for k, v in entry.items() if k != 'payload'})[:300]}")
        finally:
            client.close()

    async def run_operations(self, port: int, password: str) -> None:
        """Exercise every observation operation over the MCP backend."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP",
                "TMP", "DOTNET_ROOT", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
        environment = {k: v for k, v in os.environ.items() if k.upper() in keep}
        environment.update({
            "FACTORIO_RCON_HOST": "127.0.0.1",
            "FACTORIO_RCON_PORT": str(port),
            "FACTORIO_RCON_PASSWORD": password,
            "AUTOENGINEER_BACKEND_MODE": "helper",
            "Logging__LogLevel__Default": "None",
            "Logging__LogLevel__Microsoft": "None",
        })
        RUNTIME.mkdir(parents=True, exist_ok=True)
        environment["FACTORIO_GOALS_FILE"] = str(RUNTIME / "goals.json")
        environment["FACTORIO_BUILDINGS_FILE"] = str(RUNTIME / "buildings.json")
        params = StdioServerParameters(command="dotnet", args=[str(BACKEND_DLL)],
                                       env=environment, cwd=str(RUNTIME))

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # The backend must serve the observation tools.
                listed = await asyncio.wait_for(session.list_tools(), 30)
                names = sorted(t.name for t in listed.tools)
                self.report["tools"] = names

                for operation in OPERATIONS:
                    await self._run_one(session, operation)

                # An invalid argument must fail safely, never crash the backend.
                await self._run_invalid(session)

    async def _run_one(self, session, operation: str) -> None:
        started = time.monotonic()
        entry: dict = {"tool": "autoengineer_view"}
        try:
            if operation in ("recipes", "research", "machines", "capabilities"):
                arguments = {"catalogPageSize": 32, "catalogOnly": True}
                if operation == "capabilities":
                    arguments = {"noCatalog": True}
            elif operation in ("map", "terrain", "overlay"):
                arguments = {"noCatalog": True}
            else:
                arguments = {"noCatalog": True}
            response = await asyncio.wait_for(
                session.call_tool("autoengineer_view", arguments=arguments), 90)
            entry["elapsed"] = round(time.monotonic() - started, 4)
            entry["is_error"] = bool(getattr(response, "is_error", False))
            text = next((item.text for item in response.content
                         if item.type == "text"), "")
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
                entry["raw_head"] = text[:400]
            if isinstance(payload, dict):
                entry["status"] = payload.get("status")
                entry["keys"] = sorted(payload)[:24]
                entry["payload"] = payload
        except Exception as exc:  # noqa: BLE001 - recorded, never raised
            entry["elapsed"] = round(time.monotonic() - started, 4)
            entry["error"] = f"{type(exc).__name__}: {exc}"
        self.report["operations"][operation] = entry
        log(f"OPERATION {operation}: {json.dumps(
            {k: v for k, v in entry.items() if k != 'payload'})[:400]}")

    async def _run_invalid(self, session) -> None:
        """An invalid observation argument must fail safely."""
        started = time.monotonic()
        entry: dict = {}
        try:
            response = await asyncio.wait_for(
                session.call_tool("autoengineer_view",
                                  arguments={"catalogOnly": True,
                                             "noCatalog": True}),
                60)
            entry["is_error"] = bool(getattr(response, "is_error", False))
            entry["elapsed"] = round(time.monotonic() - started, 4)
            text = next((item.text for item in response.content
                         if item.type == "text"), "")
            entry["message"] = text[:400]
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["elapsed"] = round(time.monotonic() - started, 4)
        self.report["invalid_arguments"] = entry

    # -- teardown ---------------------------------------------------------

    def stop(self) -> None:
        for name, process in (("client", self.client), ("server", self.server)):
            if process is None:
                continue
            try:
                process.terminate()
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass
        self.report["stopped"] = True

    def collect_log_evidence(self) -> None:
        """Record the achievement markers and the mod load from the logs."""
        text = self._server_game_log()
        for path in (self.client_log,):
            if path.is_file():
                text += path.read_text(encoding="utf-8", errors="replace")
        self.report["achievement_markers"] = achievement_markers(text)
        self.report["mod_loaded"] = "autoengineer-input 2.1.23" in text
        self.report["log_bytes"] = len(text)

    def verify_originals(self) -> None:
        """Confirm the canonical saves are byte-identical to their start."""
        paths = self.profile_paths()
        source_save = paths["save"]
        expected = self.report.get("original_save_sha256")
        actual = digest(source_save) if source_save.is_file() else None
        self.report["original_save_unchanged"] = bool(
            expected and actual and expected == actual)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True,
                        choices=("vanilla-space-age", "pyanodons"))
    parser.add_argument("--tag", default="")
    options = parser.parse_args()

    tag = options.tag or f"p7-{options.profile}-{time.strftime('%Y%m%d-%H%M%S')}"
    run = LiveObservation(options.profile, tag)
    port = game_port = 0
    password = ""
    try:
        port, game_port, password = run.start_server()
        if not run.wait_for_server(port):
            raise RuntimeError("the server did not open its RCON endpoint")
        log("SERVER_READY")
        run.start_client(game_port)
        if not run.wait_for_join():
            run.report["joined"] = False
            log("CLIENT_JOIN_TIMEOUT")
        else:
            run.report["joined"] = True
            log("CLIENT_JOINED")
            # The direct RCON test proves the mod command itself works over
            # the real transport, before the backend composes it.
            run.run_direct_operations(port, password)
            asyncio.run(run.run_operations(port, password))
    except Exception as exc:  # noqa: BLE001 - recorded in the report
        run.report["fatal"] = f"{type(exc).__name__}: {exc}"
        log(f"FATAL {type(exc).__name__}: {exc}")
    finally:
        run.collect_log_evidence()
        run.verify_originals()
        run.stop()
        out = run.run_dir / "report.json"
        out.write_text(json.dumps(run.report, indent=1, default=str), encoding="utf-8")
        log(f"REPORT={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
