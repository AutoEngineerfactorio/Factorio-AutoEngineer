"""LIVE R10-A acceptance: the Qt dashboard under the creative blueprint stress.

This harness runs the **real** AutoEngineer stack against a **real** Factorio
2.1.23 full-Pyanodons graphical host while the creative fluid blueprint
factory is actively producing:

* the Factorio 2.1.23 graphical host with the full Pyanodons mod set and the
  ``autoengineer-input`` observation mod;
* the reviewed Pyanodons oxygen/nitrogen blueprint, placed several times;
* the creative fluid supply and drain that keeps the factory working;
* the local FrogNano model server and the AI Helper's read-only planning
  completions, gated on the observed UPS;
* the **Qt dashboard** on the **offscreen** platform, driven by the **real**
  observation path: the restricted C# backend over stdio, the shared
  observation coordinator, the observation bridge and the Qt shell;
* the Recipes & Research workspace's own **catalog** request, so the large
  Pyanodons catalog is read while the factory runs.

It measures the game's real UPS, the Factorio and model process memory, the
observation latency, the catalog latency, the render times and the AI
throughput.

Safety contract:

* the AI Helper and the dashboard stay **read-only**;
* the game runs at its **normal** speed; the speed is never overridden;
* the source save is opened **read-only**, copied to a disposable per-run
  file, and its SHA-256 is compared before and after;
* the RCON password is generated per run and never printed;
* only the processes this harness started are stopped.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tests"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import live_long_stress as stress  # noqa: E402
import live_py_creative_fluid as creative  # noqa: E402


def _tail(values: list[float]) -> dict:
    """Return the summary of one series of samples."""
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "average": round(statistics.fmean(values), 3),
        "median": round(statistics.median(values), 3),
        "minimum": round(min(values), 3),
        "maximum": round(max(values), 3),
    }


class DashboardRunner:
    """Runs the real Qt dashboard against the live game, in the background.

    The dashboard runs on the main GUI thread of its own process, with
    its own event loop and MCP session. It never blocks the game or model.
    """

    def __init__(self, rcon_port: int, password: str, work: Path):
        self.rcon_port = rcon_port
        self.password = password
        self.work = work
        self.thread: threading.Thread | None = None
        self.stop: Any = threading.Event()
        self._process: Any = None
        self.error: str | None = None
        self.frames = 0
        self.catalog_rows = 0
        self.catalog_status = ""
        self.inventory_rows = 0
        self.render_times: list[float] = []
        self.catalog_latencies: list[float] = []
        self.telemetry_latencies: list[float] = []
        self.bridge_stats: dict = {}
        self._result: dict = {}
        self.pillow_evidence: dict = {}
        self.process_metrics = {"peak_rss_mb": 0.0, "peak_cpu_percent": 0.0, "cpu_samples": 0}

    def start(self) -> None:
        """Start the dashboard thread."""
        from importlib import import_module

        context = import_module("multiprocessing").get_context("spawn")
        self.stop = context.Event()
        self._process = context.Process(target=_dashboard_child,
            args=(self.rcon_port, self.password, self.work, self.stop),
            name="r10a-dashboard", daemon=True)
        self._process.start()

    def _run(self) -> None:
        """Run the dashboard until the harness stops it."""
        try:
            asyncio.run(self._drive())
        except Exception as exc:  # noqa: BLE001 - the failure is reported
            self.error = f"{type(exc).__name__}: {str(exc)[:200]}"

    async def _drive(self) -> None:
        """Drive the real observation path and the real Qt shell."""
        from importlib import import_module

        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        from observation_service import ObservationService
        from qt_observation_bridge import ObservationBridge
        from qt_shell import ShellWindow

        QApplication = import_module("PySide6.QtWidgets").QApplication
        app = QApplication.instance() or QApplication([])

        # The backend connects to the game's RCON port when it starts. The
        # game may still be booting, so the port is awaited first. Without
        # this the backend dies with a connection error and the dashboard
        # never observes anything.
        if not await _wait_for_rcon(self.rcon_port):
            raise RuntimeError(
                f"the game's RCON port {self.rcon_port} never opened")

        params = _mcp_params(self.rcon_port, self.password)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if not await _wait_for_player(session):
                    raise RuntimeError("the backend never observed a player")
                service = ObservationService()
                bridge = ObservationBridge(service, interval=2.0)
                window = ShellWindow()
                window.resize(1920, 1080)
                window.show()
                app.processEvents()
                window.start_observations(bridge, session)

                # The Recipes & Research workspace asks for the catalog the
                # same way the user does. The Pyanodons catalog is the large
                # one, so its latency is the interesting measurement.
                catalog_started = time.perf_counter()
                window.catalog_widget().refresh_button.click()
                deadline = time.perf_counter() + 20
                while time.perf_counter() < deadline:
                    app.processEvents()
                    await asyncio.sleep(0.05)
                    if window.catalog_widget().recipe_table.rowCount():
                        break
                self.catalog_latencies.append(
                    round((time.perf_counter() - catalog_started) * 1000, 3))

                next_capture = 0.0
                process = import_module("psutil").Process(os.getpid())
                process.cpu_percent(None)
                next_process_sample = 0.0
                while not self.stop.is_set():
                    started = time.perf_counter()
                    app.processEvents()
                    self.render_times.append(
                        (time.perf_counter() - started) * 1000)
                    try:
                        catalog = window.catalog_widget()
                        self.catalog_rows = max(self.catalog_rows,
                                               catalog.recipe_table.rowCount())
                        self.catalog_status = catalog.status.text()
                        self.inventory_rows = max(
                            self.inventory_rows,
                            window.inventory_widget("Inventory")
                            .inventory_table.rowCount())
                    except Exception:  # noqa: BLE001 - the sample is optional
                        pass
                    if time.perf_counter() >= next_process_sample:
                        rss = process.memory_info().rss / (1024 * 1024)
                        cpu = process.cpu_percent(None)
                        self.process_metrics["peak_rss_mb"] = max(self.process_metrics["peak_rss_mb"], round(rss, 2))
                        self.process_metrics["peak_cpu_percent"] = max(self.process_metrics["peak_cpu_percent"], cpu)
                        self.process_metrics["cpu_samples"] += 1
                        next_process_sample = time.perf_counter() + 1
                    model = window.telemetry_widget("Production").model
                    if time.perf_counter() >= next_capture and model.available and model.networks:
                        from pillow_dashboard_evidence import capture

                        self.pillow_evidence = capture(window, self.work / "dashboard-populated.png")
                        snapshot = window.catalog_widget().snapshot
                        self.pillow_evidence["catalog_complete"] = bool(snapshot and snapshot.complete)
                        self.pillow_evidence["catalog_surface"] = snapshot.surface if snapshot else None
                        self.pillow_evidence["surface"] = model.surface
                        next_capture = time.perf_counter() + 60
                    await asyncio.sleep(0.25)

                self.frames = bridge.stats.as_dict().get("emitted", 0)
                self.bridge_stats = bridge.stats.as_dict()
                window.stop_observations()
                window.close()
                app.processEvents()

    def stop_and_report(self) -> dict:
        """Stop the dashboard and return its measurements."""
        self.stop.set()
        if self._process is not None:
            self._process.join(timeout=30)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=5)
                self.error = "Dashboard worker did not stop before its deadline"
            path = self.work / "dashboard.json"
            report: dict[str, Any]
            try:
                if path.stat().st_size > 1000000:
                    raise ValueError("Oversized dashboard report")
                report = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                report = {"error": self.error or "Dashboard child report unavailable"}
            report["worker_exit_code"] = self._process.exitcode
            report["worker_stopped"] = not self._process.is_alive()
            if self._process.exitcode != 0:
                report["error"] = report.get("error") or "Dashboard child exited unsuccessfully"
            path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            return report
        if self.thread is not None:
            self.thread.join(timeout=30)
        report = {
            "frames_emitted": self.frames,
            "bridge_stats": self.bridge_stats,
            "catalog_rows": self.catalog_rows,
            "catalog_status": self.catalog_status,
            "inventory_rows": self.inventory_rows,
            "catalog_latency_ms": _tail(self.catalog_latencies),
            "render_ms": _tail(self.render_times),
            "error": self.error,
            "pillow_evidence": self.pillow_evidence,
            "process_metrics": self.process_metrics,
            "render_scope": "Offscreen Qt event-processing time; not native client FPS or GPU measurement",
        }
        (self.work / "dashboard.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        return report


def dashboard_pass(report):
    image = report.get("pillow_evidence") or {}
    return bool(not report.get("error") and report.get("worker_exit_code") == 0
                and report.get("worker_stopped") is True and report.get("frames_emitted", 0) > 0
                and image.get("not_blank") and image.get("network_rows", 0) > 0
                and image.get("catalog_complete") and image.get("catalog_surface") == image.get("surface"))


def _dashboard_child(port, password, work, stop_event):
    """Entry point created by spawn: all Qt widgets stay on this main thread."""
    runner = DashboardRunner(port, password, work)
    runner.stop = stop_event
    runner._run()
    runner.stop_and_report()


def _mcp_params(rcon_port: int, password: str):
    """Return the stdio parameters of the restricted backend."""
    from mcp import StdioServerParameters
    from qt_live_acceptance import BASE, RESTRICTED_BACKEND, env

    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP",
            "TMP", "DOTNET_ROOT", "USERPROFILE", "APPDATA", "LOCALAPPDATA"}
    child_env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    child_env.setdefault("DOTNET_ROOT", env.dotnet_root())
    child_env.update({
        "FACTORIO_RCON_HOST": env.RCON_HOST,
        "FACTORIO_RCON_PORT": str(rcon_port),
        "FACTORIO_RCON_PASSWORD": password,
        "AUTOENGINEER_BACKEND_MODE": "helper",
        "Logging__LogLevel__Default": "None",
        "Logging__LogLevel__Microsoft": "None",
    })
    return StdioServerParameters(
        command="dotnet", args=[str(RESTRICTED_BACKEND)], env=child_env,
        cwd=str(BASE / "backend-runtime"))


async def _wait_for_rcon(port: int, timeout: float = 600.0) -> bool:
    """Wait until the game's RCON port accepts a connection.

    The backend connects to the RCON port when it starts and gives up if the
    port is not open yet. The game needs time to boot, so the port is
    awaited before the backend is started.
    """
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3):
                return True
        except OSError:
            await asyncio.sleep(2.0)
    return False


async def _wait_for_player(session, attempts: int = 120) -> bool:
    """Wait until the backend observes the connected player."""
    from qt_live_acceptance import call_tool

    for _ in range(attempts):
        payload = await call_tool(session, "autoengineer_telemetry", {})
        if payload.get("status") == "ok":
            return True
        await asyncio.sleep(1.0)
    return False


def _read_host_credentials(work: Path) -> tuple[int, str] | None:
    """Return the RCON port and password of a running stress host.

    The stress harness writes them into the host's private config. The file
    is harness-owned and the password is never printed or stored.
    """
    import configparser

    config = work / "host.private.ini"
    if not config.is_file():
        return None
    parser = configparser.ConfigParser(strict=False)
    try:
        parser.read(config, encoding="utf-8")
        socket = parser.get("other", "local-rcon-socket")
        password = parser.get("other", "local-rcon-password")
    except (configparser.Error, OSError):
        return None
    _, _, port = socket.rpartition(":")
    try:
        return int(port), password
    except ValueError:
        return None


def run(replicas: int, seconds: int) -> int:
    """Run the stress with the dashboard attached."""
    holder: dict = {}
    stop_original = stress.stop_owned
    # The run directories that existed before this run. The dashboard must
    # attach to the run this harness creates, not to an older one.
    before = {path.name for path in stress.OUTPUT.glob("py-*")}

    # The dashboard needs the RCON port and the password of the running
    # game, which the stress harness creates. A watcher thread picks them up
    # from the new run directory as soon as the host is configured.
    def watcher() -> None:
        """Wait for the new stress run directory and attach the dashboard."""
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            runs = sorted(stress.OUTPUT.glob("py-*"), key=lambda p: p.name)
            fresh = [path for path in runs if path.name not in before]
            if fresh:
                work = fresh[-1]
                credentials = _read_host_credentials(work)
                if credentials is not None:
                    runner = DashboardRunner(credentials[0], credentials[1],
                                            work)
                    runner.start()
                    holder["runner"] = runner
                    holder["work"] = work
                    return
            time.sleep(2)

    def stop_after_dashboard(proc):
        runner = holder.get("runner")
        if runner is not None and "stop_report" not in holder:
            holder["stop_report"] = runner.stop_and_report()
        stop_original(proc)

    stress.stop_owned = stop_after_dashboard
    thread = threading.Thread(target=watcher, daemon=True,
                               name="r10a-dashboard-watcher")
    thread.start()
    try:
        result = creative.run(replicas, seconds)
    finally:
        stress.stop_owned = stop_original
        runner = holder.get("runner")
        if runner is not None:
            report = holder.get("stop_report") or runner.stop_and_report()
            report["dashboard_pass"] = dashboard_pass(report)
            print("[dashboard] " + json.dumps(report, default=str), flush=True)
            work = holder.get("work")
            if work is not None:
                path = work / "result.json"
                if path.is_file():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data["dashboard"] = report
                    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return result if holder.get("runner") is not None and report.get("dashboard_pass") else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicas", type=int, default=4, choices=(1, 2, 3, 4))
    parser.add_argument("--seconds", type=int, default=300)
    parsed = parser.parse_args()
    raise SystemExit(run(parsed.replicas, parsed.seconds))
