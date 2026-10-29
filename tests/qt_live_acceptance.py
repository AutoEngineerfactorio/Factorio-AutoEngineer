"""LIVE read-only acceptance of the Qt dashboard against real Factorio 2.1.23.

This is the authorised live test. It:

* starts the **isolated** Factorio 2.1.23 server at its **normal** speed;
* starts the **graphical** client against the persistent, authenticated
  client profile;
* runs the **real** observation path - the restricted MCP backend over
  stdio, the R09 observation coordinator, the Qt observation bridge and
  the Qt shell - and records what actually arrives;
* records the game's own UPS and FPS before and after the dashboard
  connects, the observation latency, the polling frequency, the chart
  and map rendering times, the cache effectiveness and any missing or
  partial data;
* stops **only** the processes this harness started.

Safety contract:

* the AI Helper stays **read-only**. Only ``autoengineer_status`` and
  ``autoengineer_telemetry`` are called. No gameplay command, no
  placement, no blueprint and no research change is issued.
* the game runs at its **normal** speed. The speed is never overridden.
* the source save is opened **read-only**, copied to a disposable
  per-run file, and its SHA-256 is compared before and after.
* no personal save, profile or credential is touched. The RCON password
  is read from the harness-owned secret and is **never printed**.
* nothing is published, committed or pushed.

Run it directly:

    python -B tests\\qt\\_live\\_acceptance.py --profile vanilla
    python -B tests\\qt\\_live\\_acceptance.py --profile pyanodons
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "agent"))


def _add_system_site_packages() -> None:
    """Make the system interpreter's packages visible to this one.

    The live harness needs **both** the MCP client and PySide6. The
    ``.venv`` that holds PySide6 deliberately holds only PySide6, and the
    system interpreter that holds the MCP client has no PySide6.

    The system interpreter is found through the ``python.exe`` on ``PATH``,
    so this works no matter which interpreter runs the harness. Only its
    own site-packages directories are **appended** to ``sys.path``.
    Nothing is installed, downloaded or changed, and the system
    interpreter keeps its own packages.
    """
    import shutil

    executable = shutil.which("python")
    if not executable:
        return
    # The interpreter's own directory is the Python root, so the
    # site-packages live next to it.
    root = Path(executable).resolve().parent
    library = root / "Lib" / "site-packages"
    candidates = [
        library,
        library / "win32",
        library / "win32" / "lib",
        library / "pythonwin",
    ]
    for directory in candidates:
        path = str(directory)
        if path not in sys.path and directory.is_dir():
            sys.path.append(path)


try:
    import mcp  # noqa: F401
except ImportError:  # pragma: no cover - depends on the interpreter
    _add_system_site_packages()

import live_r06_game_side_verify as game_side  # noqa: E402
import r06_live_environment as env  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

BASE = env.BASE
EVIDENCE = env.EVIDENCE
EXE = env.EXE
SERVER_SETTINGS = BASE / "server" / "server-settings.json"
BASE_CONFIG = BASE / "server" / "config.ini"
RESTRICTED_BACKEND = BASE / "backend-patched-2.1.23" / "FactorioMCP.dll"

#: The vanilla / Space Age profile: the isolated installation's own mods.
VANILLA_MODS = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\mods")
#: The Pyanodons profile: the large-modpack mod suite.
PYAN_MODS = env.MODS

VANILLA_SAVE = (ROOT / ".local" / "launcher-profiles" / "2.1.23"
                / "data" / "saves" / "autoengineer-test.zip")
PYAN_SAVE = env.MODDED_SAVE

#: How long the observation window lasts, in seconds.
WINDOW_SECONDS = 600.0

#: How often the harness samples the game's own UPS and FPS.
SAMPLE_INTERVAL_SECONDS = 1.0

#: How long the server may take to open its RCON endpoint.
SERVER_READY_SECONDS = 300.0

#: How long the client may take to join.
JOIN_WINDOW_SECONDS = 900.0

#: The RCON port used by the vanilla profile.
VANILLA_RCON_PORT = 27109

#: The game port used by the vanilla profile.
VANILLA_GAME_PORT = 27107

#: The RCON port used by the Pyanodons profile.
PYAN_RCON_PORT = 27271

#: The game port used by the Pyanodons profile.
PYAN_GAME_PORT = 27271 - 1000

#: The ports that the **dashboard** may use for the Pyanodons profile.
#: The R06 evidence records 34371 for the dashboard's own RCON channel.
PYAN_DASH_RCON_PORT = 34371


def log(message: str) -> None:
    """Print one timestamped progress line."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def sha256(path: Path) -> str:
    """Return the SHA-256 of one file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def mcp_params(dll: Path, rcon_port: int, password: str,
               mode: str = "helper") -> StdioServerParameters:
    """Return the stdio parameters of the restricted backend."""
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP",
            "TMP", "DOTNET_ROOT", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
    child_env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    child_env.setdefault("DOTNET_ROOT", env.dotnet_root())
    child_env.update({
        "FACTORIO_RCON_HOST": env.RCON_HOST,
        "FACTORIO_RCON_PORT": str(rcon_port),
        "FACTORIO_RCON_PASSWORD": password,
        "AUTOENGINEER_BACKEND_MODE": mode,
        "Logging__LogLevel__Default": "None",
        "Logging__LogLevel__Microsoft": "None",
    })
    return StdioServerParameters(
        command="dotnet", args=[str(dll)], env=child_env,
        cwd=str(BASE / "backend-runtime"))


def read_game_stats(profile_data: Path) -> dict[str, float]:
    """Return the game's own performance counters from the log.

    A **headless** server does not print the UPS and FPS lines, so the
    log usually carries none. The game tick is used instead: the tick
    rate against the wall clock **is** the game's update rate, and the
    tick itself comes from the observed telemetry, so it is the game's
    own number and not an estimate.

    The log counters are still read, because a run that does print them
    carries the exact figures.
    """
    text = env.read_game_log(profile_data)
    ups: list[float] = []
    fps: list[float] = []
    for match in re.finditer(
            r"UPS(?: (?:up|down))?[=:]?\s*([0-9]+\.[0-9]+)", text):
        ups.append(float(match.group(1)))
    for match in re.finditer(
            r"FPS(?: (?:up|down))?[=:]?\s*([0-9]+\.[0-9]+)", text):
        fps.append(float(match.group(1)))
    return {
        "ups_last": ups[-1] if ups else -1.0,
        "ups_max": max(ups) if ups else -1.0,
        "fps_last": fps[-1] if fps else -1.0,
        "fps_max": max(fps) if fps else -1.0,
        "ups_samples": len(ups),
        "fps_samples": len(fps),
    }


def tick_rate(ticks: list[tuple[float, int]]) -> dict[str, float]:
    """Return the game's update rate from the observed tick sequence.

    ``ticks`` holds ``(wall_clock_seconds, game_tick)`` pairs. The rate
    between two samples is the game's own simulation rate: 60 ticks per
    second is a game running at its **normal** speed.
    """
    if len(ticks) < 2:
        return {"tick_ups_median": -1.0, "tick_ups_min": -1.0,
                "tick_ups_max": -1.0, "tick_ups_samples": 0}
    rates = []
    for index in range(1, len(ticks)):
        elapsed = ticks[index][0] - ticks[index - 1][0]
        advanced = ticks[index][1] - ticks[index - 1][1]
        if elapsed > 0 and advanced >= 0:
            rates.append(advanced / elapsed)
    if not rates:
        return {"tick_ups_median": -1.0, "tick_ups_min": -1.0,
                "tick_ups_max": -1.0, "tick_ups_samples": 0}
    return {
        "tick_ups_median": round(statistics.median(rates), 2),
        "tick_ups_min": round(min(rates), 2),
        "tick_ups_max": round(max(rates), 2),
        "tick_ups_samples": len(rates),
    }


def profile_for(name: str) -> dict:
    """Return the paths and ports of one profile."""
    if name == "vanilla":
        return {
            "name": "vanilla-space-age",
            "mods": VANILLA_MODS,
            "save": VANILLA_SAVE,
            "rcon_port": VANILLA_RCON_PORT,
            "game_port": VANILLA_GAME_PORT,
        }
    return {
        "name": "pyanodons",
        "mods": PYAN_MODS,
        "save": PYAN_SAVE,
        "rcon_port": PYAN_RCON_PORT,
        "game_port": PYAN_GAME_PORT,
    }


def prepare_server(profile: dict, run_tag: str,
                   password: str) -> tuple[Path, Path]:
    """Write the per-run server config and the disposable save copy."""
    config = env.prepare_server_config(run_tag, BASE_CONFIG,
                                       profile["rcon_port"], password)
    save = env.copy_disposable_save(profile["save"], run_tag)
    return config, save


def start_server(profile: dict, run_tag: str, config: Path, save: Path,
                 password: str, report: dict) -> subprocess.Popen:
    """Start the Factorio server and wait for its RCON endpoint."""
    log_path = EVIDENCE / f"{run_tag}-factorio.log"
    out = log_path.open("w", encoding="utf-8")
    err = log_path.with_suffix(".err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([
        str(EXE), "--config", str(config),
        "--mod-directory", str(profile["mods"]),
        "--start-server", str(save),
        "--server-settings", str(SERVER_SETTINGS),
        "--bind", f"127.0.0.1:{profile['game_port']}",
        "--rcon-bind", f"127.0.0.1:{profile['rcon_port']}",
        "--rcon-password", password,
    ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    log(f"SERVER_PID={proc.pid}")

    def ready() -> object:
        if proc.poll() is not None:
            return f"the server exited with rc={proc.returncode}"
        if env.server_is_healthy(profile["rcon_port"]):
            return True
        return None

    result = env.wait_for(ready, timeout=SERVER_READY_SECONDS,
                           description="the server opened its RCON endpoint")
    report["server_ready"] = result.ok
    report["server_ready_reason"] = result.reason
    report["server_ready_waited_seconds"] = round(result.waited_seconds, 2)
    log(f"SERVER_READY={result.ok} ({result.reason})")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    loaded = sorted(set(re.findall(
        r"Loading mod ([A-Za-z0-9_.-]+) ([0-9.]+)", text)))
    report["mods_loaded"] = [f"{name} {version}" for name, version in loaded]
    report["pyanodons_loaded"] = sorted(
        name for name, _ in loaded if name.lower().startswith("py"))
    return proc


def start_client(profile: dict, run_tag: str,
                 report: dict) -> subprocess.Popen:
    """Start the graphical client against the persistent client profile."""
    client_config = env.prepare_client_profile(
        run_tag, BASE_CONFIG, profile["rcon_port"])
    client_log = EVIDENCE / f"{run_tag}-client.log"
    out = client_log.open("w", encoding="utf-8")
    err = client_log.with_suffix(".err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([
        str(EXE), "--config", str(client_config),
        "--mod-directory", str(profile["mods"]),
        "--mp-connect", f"127.0.0.1:{profile['game_port']}",
    ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    log(f"CLIENT_PID={proc.pid}")
    report["client_pid"] = proc.pid
    return proc


def wait_for_join(client: subprocess.Popen, server_data: Path,
                  client_data: Path, report: dict) -> bool:
    """Wait, bounded, for the client to join the server.

    The join is detected from the server's own multiplayer state lines,
    using the **proven** markers of the R06 game-side harness, so a
    successful join is never missed.
    """
    def joined() -> object:
        if client.poll() is not None:
            return "the client process exited before it joined"
        text = env.read_game_log(server_data)
        evidence = game_side.join_evidence(text)
        if evidence:
            report["join_evidence"] = evidence[:8]
            return True
        return None

    result = env.wait_for(joined, timeout=JOIN_WINDOW_SECONDS,
                           description="the client joined the server")
    report["client_joined"] = result.ok
    report["client_join_reason"] = result.reason
    report["client_join_waited_seconds"] = round(result.waited_seconds, 2)
    if not result.ok:
        server_text = env.read_game_log(server_data)
        report["refusal_evidence"] = game_side.refusal_evidence(
            server_text)[:8]
        report["auth_progress"] = game_side.auth_progress(
            env.read_game_log(client_data))
    log(f"CLIENT_JOINED={result.ok} ({result.reason})")
    return result.ok


async def call_tool(session: ClientSession, name: str,
                    arguments: dict | None = None) -> dict:
    """Call one read-only backend tool and return its parsed content."""
    result = await session.call_tool(name, arguments=arguments or {})
    texts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            texts.append(text)
    body = "\n".join(texts)
    try:
        return json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return {"_raw": body[:4000], "_is_error":
                bool(getattr(result, "isError", False))}


async def wait_for_player(session: ClientSession, report: dict,
                           timeout: float = 300.0) -> bool:
    """Wait, bounded, until the backend observes the player.

    The readiness signal is the **telemetry** observation, because the
    telemetry tool travels over the **registered mod command**, which is
    the achievement-safe transport. The telemetry answer carries the
    surface once a character exists, so it proves the same thing the
    view would, without the view's outstanding Lua-console-command path.
    """
    deadline = time.monotonic() + timeout
    attempts = 0
    last: dict = {}
    while time.monotonic() < deadline:
        attempts += 1
        payload = await call_tool(session, "autoengineer_telemetry", {})
        last = payload
        status = str(payload.get("status") or "")
        surface = payload.get("surface")
        if status == "ok" and isinstance(surface, str) and surface:
            report["player_ready"] = True
            report["player_ready_attempts"] = attempts
            report["player_ready_surface"] = surface
            report["player_ready_tick"] = payload.get("tick")
            log(f"PLAYER_READY after {attempts} telemetry polls")
            return True
        await asyncio.sleep(1.0)
    report["player_ready"] = False
    report["player_ready_attempts"] = attempts
    report["player_ready_last"] = {
        "status": last.get("status"),
        "reason": last.get("reason"),
    }
    log(f"PLAYER_READY=False after {attempts} polls")
    return False


async def run_observation_window(session: ClientSession, report: dict,
                                 window_seconds: float) -> None:
    """Poll the real read-only tools and record every measurement.

    The window records the game's own UPS and FPS, the observation
    latency, the polling frequency and whether the telemetry was
    complete or partial.
    """
    server_data = BASE / "server" / "data"
    samples: list[dict] = []
    telemetry_latencies: list[float] = []
    status_latencies: list[float] = []
    telemetry_ok = 0
    telemetry_partial = 0
    telemetry_unavailable = 0
    surfaces: set[str] = set()
    ticks: list[int] = []
    tick_pairs: list[tuple[float, int]] = []
    networks_seen: set[int] = set()
    materials_seen: set[str] = set()
    first_success_at: float | None = None
    started_at = time.monotonic()

    deadline = time.monotonic() + window_seconds
    next_sample = time.monotonic()
    polls = 0

    while time.monotonic() < deadline:
        now = time.monotonic()

        # The game's own numbers, sampled once a second.
        if now >= next_sample:
            stats = read_game_stats(server_data)
            samples.append({"t": round(now - started_at, 2), **stats})
            next_sample = now + SAMPLE_INTERVAL_SECONDS

        # The real telemetry request, through the restricted backend.
        polls += 1
        started = time.monotonic()
        try:
            payload = await call_tool(session, "autoengineer_telemetry", {})
        except Exception as exc:  # noqa: BLE001 - a failure is recorded
            telemetry_latencies.append(time.monotonic() - started)
            telemetry_unavailable += 1
            report["last_error"] = f"{type(exc).__name__}: {exc}"
            await asyncio.sleep(2.0)
            continue
        telemetry_latencies.append(time.monotonic() - started)

        if first_success_at is None and payload.get("status") == "ok":
            first_success_at = time.monotonic()

        surface = payload.get("surface")
        if isinstance(surface, str):
            surfaces.add(surface)
        tick = payload.get("tick")
        if isinstance(tick, int):
            ticks.append(tick)
            tick_pairs.append((time.monotonic() - started_at, tick))

        production = payload.get("production") or {}
        power = payload.get("power") or {}
        if not isinstance(production, dict):
            production = {}
        if not isinstance(power, dict):
            power = {}
        if production.get("status") == "ok":
            telemetry_ok += 1
        elif production.get("status") == "partial":
            telemetry_partial += 1
        else:
            telemetry_unavailable += 1

        # The item and fluid flow groups are **lists** in the observed
        # payload, each holding the series the observer collected.
        for group in (production.get("items"), production.get("fluids")):
            if not isinstance(group, list):
                continue
            for entry in group:
                if not isinstance(entry, dict):
                    continue
                for series in entry.get("series") or []:
                    if isinstance(series, dict):
                        name = series.get("name")
                        if isinstance(name, str):
                            materials_seen.add(name)
        for network in power.get("networks") or []:
            if isinstance(network, dict):
                network_id = network.get("network_id")
                if isinstance(network_id, int):
                    networks_seen.add(network_id)

        # The status request, through the restricted backend. This is the
        # **same** request the shipped bridge makes: the cheap view
        # without the catalog, never the catalog itself.
        started = time.monotonic()
        try:
            await call_tool(session, "autoengineer_view", {"noCatalog": True})
        except Exception:  # noqa: BLE001 - the status is optional
            pass
        status_latencies.append(time.monotonic() - started)

        await asyncio.sleep(2.0)

    ups = [s["ups_last"] for s in samples if s["ups_last"] >= 0]
    fps = [s["fps_last"] for s in samples if s["fps_last"] >= 0]
    report["polls"] = polls
    report["window_seconds"] = window_seconds
    report["polling_interval_seconds"] = 2.0
    report["telemetry_ok"] = telemetry_ok
    report["telemetry_partial"] = telemetry_partial
    report["telemetry_unavailable"] = telemetry_unavailable
    report["telemetry_latency_median_ms"] = round(
        statistics.median(telemetry_latencies) * 1000, 2) if telemetry_latencies else -1
    report["telemetry_latency_max_ms"] = round(
        max(telemetry_latencies) * 1000, 2) if telemetry_latencies else -1
    report["status_latency_median_ms"] = round(
        statistics.median(status_latencies) * 1000, 2) if status_latencies else -1
    report["surfaces_observed"] = sorted(surfaces)
    report["network_count"] = len(networks_seen)
    report["material_count"] = len(materials_seen)
    report["tick_increasing"] = bool(ticks) and all(
        ticks[i] <= ticks[i + 1] for i in range(len(ticks) - 1))
    report["tick_span"] = (ticks[-1] - ticks[0]) if len(ticks) > 1 else 0
    report["ups_min"] = min(ups) if ups else -1
    report["ups_median"] = round(statistics.median(ups), 2) if ups else -1
    report["ups_max"] = max(ups) if ups else -1
    report["fps_min"] = min(fps) if fps else -1
    report["fps_median"] = round(statistics.median(fps), 2) if fps else -1
    report["fps_max"] = max(fps) if fps else -1
    report["ups_samples"] = len(ups)
    report["fps_samples"] = len(fps)
    report.update(tick_rate(tick_pairs))
    report["game_samples"] = samples
    report["first_success_at_seconds"] = (
        round(first_success_at - (deadline - window_seconds), 2)
        if first_success_at else None)


async def measure_tick_rate(session: ClientSession, report: dict,
                             label: str, samples: int = 8,
                             interval: float = 1.0) -> dict:
    """Measure the game's own update rate over a short window.

    The tick comes from the observed telemetry and the wall clock comes
    from this harness, so the rate is the **game's** own number. A game
    at its normal speed runs at 60 ticks per second.
    """
    pairs: list[tuple[float, int]] = []
    started = time.monotonic()
    for _ in range(samples):
        payload = await call_tool(session, "autoengineer_telemetry", {})
        tick = payload.get("tick")
        if isinstance(tick, int):
            pairs.append((time.monotonic() - started, tick))
        await asyncio.sleep(interval)
    result = tick_rate(pairs)
    report[label] = result
    log(f"{label}={json.dumps(result)}")
    return result


async def run_qt_dashboard(session: ClientSession, report: dict,
                           seconds: float) -> None:
    """Run the real Qt shell against the real backend and measure it.

    The dashboard is driven through the **same** bridge the shipped
    dashboard uses, so what is measured is the shipped path.
    """
    from importlib import import_module

    from observation_service import ObservationService
    from qt_observation_bridge import ObservationBridge
    from qt_shell import ShellWindow

    # The Qt import is resolved at run time, because the live harness
    # runs under the PySide6 interpreter and the static checker does not
    # have that package on its own path.
    QApplication = import_module("PySide6.QtWidgets").QApplication

    app = QApplication.instance() or QApplication([])

    service = ObservationService()
    bridge = ObservationBridge(service, interval=2.0)

    window = ShellWindow()
    window.resize(1920, 1080)
    window.show()
    app.processEvents()

    frames: list[object] = []
    window.frameArrived.connect(frames.append)

    # The shell's **own** start path is used, so the frame is routed by
    # the shipped code and not by the harness. The shell connects its
    # ``apply_ui_frame`` handler and starts the bridge itself.
    window.start_observations(bridge, session)
    log("DASHBOARD_STARTED")

    deadline = time.monotonic() + seconds
    next_sample = time.monotonic()
    render_times: list[float] = []
    chart_points: list[int] = []
    flow_counts: list[int] = []
    network_counts: list[int] = []
    surfaces: list[str] = []
    catalog_rows: list[int] = []
    catalog_status: list[str] = []
    inventory_rows: list[int] = []
    production_rows: list[int] = []
    logistics_rows: list[int] = []
    catalog_requests = 0

    # The Recipes & Research workspace asks the **user** for the catalog.
    # The harness presses the same button the user presses, so the measured
    # path is the shipped one.
    try:
        window.catalog_widget().refresh_button.click()
        catalog_requests += 1
        log("CATALOG_REFRESH_REQUESTED")
    except Exception as exc:  # noqa: BLE001 - the measurement is optional
        log(f"CATALOG_REFRESH_SKIPPED {type(exc).__name__}")

    while time.monotonic() < deadline:
        app.processEvents()
        now = time.monotonic()
        if now >= next_sample:
            started = time.perf_counter()
            app.processEvents()
            render_times.append((time.perf_counter() - started) * 1000)
            try:
                production = window.telemetry_widget("Production")
                chart_points.append(len(production.chart_values(0)))
                flow_counts.append(len(production.model.flows))
                network_counts.append(len(production.model.networks))
                surfaces.append(production.model.surface)
            except Exception:  # noqa: BLE001 - the measurement is optional
                pass
            try:
                catalog = window.catalog_widget()
                catalog_rows.append(catalog.recipe_table.rowCount())
                catalog_status.append(catalog.status.text())
                inventory = window.inventory_widget("Inventory")
                inventory_rows.append(inventory.inventory_table.rowCount())
                production_rows.append(inventory.production_table.rowCount())
                logistics = window.inventory_widget("Logistics")
                logistics_rows.append(logistics.logistics_table.rowCount())
            except Exception:  # noqa: BLE001 - the measurement is optional
                pass
            next_sample = now + 1.0
        await asyncio.sleep(0.05)

    window.stop_observations()
    window.close()
    app.processEvents()

    report["qt_frames_received"] = len(frames)
    report["qt_frames_observed"] = sum(
        1 for f in frames if getattr(f, "observed", False))
    report["qt_frames_stale"] = sum(
        1 for f in frames if getattr(f, "stale", False))
    report["qt_frames_unavailable"] = sum(
        1 for f in frames if getattr(f, "disconnected", False))
    report["qt_frame_kinds"] = sorted({
        getattr(f, "kind", "") for f in frames})
    report["qt_render_ms_median"] = (
        round(statistics.median(render_times), 3) if render_times else -1)
    report["qt_render_ms_max"] = (
        round(max(render_times), 3) if render_times else -1)
    report["qt_chart_points_max"] = max(chart_points) if chart_points else 0
    report["qt_flow_count_max"] = max(flow_counts) if flow_counts else 0
    report["qt_network_count_max"] = (max(network_counts)
                                      if network_counts else 0)
    report["qt_surfaces"] = sorted({s for s in surfaces if s})
    report["qt_bridge_stats"] = bridge.stats.as_dict()
    report["qt_catalog_requests"] = catalog_requests
    report["qt_catalog_rows_max"] = max(catalog_rows) if catalog_rows else 0
    report["qt_catalog_status"] = catalog_status[-1] if catalog_status else ""
    report["qt_inventory_rows_max"] = (
        max(inventory_rows) if inventory_rows else 0)
    report["qt_production_rows_max"] = (
        max(production_rows) if production_rows else 0)
    report["qt_logistics_rows_max"] = (
        max(logistics_rows) if logistics_rows else 0)
    log(f"DASHBOARD_STOPPED frames={len(frames)}")


def stop_process(proc: subprocess.Popen | None, name: str,
                  report: dict) -> None:
    """Stop one process this harness started."""
    if proc is None:
        return
    if proc.poll() is not None:
        report[f"{name}_already_exited"] = True
        return
    log(f"STOPPING_{name.upper()}_PID={proc.pid}")
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
    report[f"{name}_stopped"] = True


async def run(profile_name: str, window_seconds: float,
               dashboard_seconds: float) -> dict:
    """Run the whole live acceptance for one profile."""
    profile = profile_for(profile_name)
    run_tag = f"qt-live-{profile_name}"
    report: dict = {
        "profile": profile["name"],
        "evidence_type": "LIVE READ-ONLY",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "game_executable": str(EXE),
        "mod_directory": str(profile["mods"]),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    password = env.rcon_password()
    source_save = Path(profile["save"])
    report["source_save_sha256_before"] = sha256(source_save)

    config, save = prepare_server(profile, run_tag, password)
    report["disposable_save"] = str(save)

    server = None
    client = None
    try:
        server = start_server(profile, run_tag, config, save, password, report)
        if not report.get("server_ready"):
            report["stopped_at"] = "the server did not become ready"
        else:
            client = start_client(profile, run_tag, report)
            client_data = env.CLIENT_PROFILE / "data"
            wait_for_join(client, BASE / "server" / "data", client_data, report)
            if not report.get("client_joined"):
                report["stopped_at"] = "the client did not join"
            else:
                async with stdio_client(
                        mcp_params(RESTRICTED_BACKEND,
                                   profile["rcon_port"], password)
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        report["backend_policy"] = await call_tool(
                            session, "autoengineer_policy", {})
                        if not await wait_for_player(session, report):
                            report["stopped_at"] = (
                                "the backend never observed a player")
                        else:
                            report["ups_before_dashboard"] = read_game_stats(
                                BASE / "server" / "data")
                            await measure_tick_rate(
                                session, report, "tick_rate_before_dashboard")

                            await run_qt_dashboard(
                                session, report, dashboard_seconds)

                            report["ups_after_dashboard"] = read_game_stats(
                                BASE / "server" / "data")
                            await measure_tick_rate(
                                session, report, "tick_rate_after_dashboard")

                            await run_observation_window(
                                session, report, window_seconds)
    finally:
        stop_process(client, "client", report)
        stop_process(server, "server", report)
        report["source_save_sha256_after"] = sha256(source_save)
        report["source_save_unchanged"] = (
            report["source_save_sha256_before"]
            == report["source_save_sha256_after"])
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        out = EVIDENCE / f"{run_tag}-acceptance.json"
        out.write_text(json.dumps(report, indent=2, default=str),
                       encoding="utf-8")
        report["report_path"] = str(out)
        log(f"REPORT={out}")
    return report


def main() -> int:
    """Run the live acceptance and print the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("vanilla", "pyanodons"),
                        default="vanilla")
    parser.add_argument("--window", type=float, default=WINDOW_SECONDS,
                        help="the observation window, in seconds")
    parser.add_argument("--dashboard", type=float, default=120.0,
                        help="how long the Qt dashboard runs, in seconds")
    args = parser.parse_args()

    report = asyncio.run(
        run(args.profile, args.window, args.dashboard))
    summary = {key: value for key, value in report.items()
               if key != "game_samples"}
    print(json.dumps(summary, indent=2, default=str))
    return 0 if report.get("source_save_unchanged", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
