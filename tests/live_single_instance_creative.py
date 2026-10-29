"""Live creative-item acceptance: one graphical Factorio host, disposable save.

Explicit-user-authorized test only. Creative Lua is sent to the COPIED save,
not the source. The first command may disable achievements in that disposable
session; normal AutoEngineer observation always uses registered commands.
Never starts a dedicated Factorio server or model process. Never kills any
process it did not launch. Evidence contains no secrets.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from launcher_services import Rcon  # noqa: E402
from qt_telemetry import build_model  # noqa: E402

EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")
MODS = EXE.parents[2] / "mods"
SOURCE_SAVE = ROOT / ".local/launcher-profiles/2.1.23/data/saves/autoengineer-test.zip"
SETTINGS = ROOT / ".local/launcher-profiles/2.1.23/server-settings.json"
PLAYER_DATA = ROOT / ".local/live-pillow-2.1.23/client-profile/data/player-data.json"
BASE = ROOT / ".local/live-single-instance-creative"
STAMP = time.strftime("%Y%m%d-%H%M%S")
WORK = BASE / STAMP
CREATIVE = (
    "local p=game.connected_players[1];"
    "if not p or not p.character then rcon.print('AE_CREATIVE_NO_PLAYER'); return end;"
    "local ok,err=pcall(function() "
    "local s=game.surfaces['ae-live-creative'] or game.create_surface('ae-live-creative',{});"
    "s.request_to_generate_chunks({0,0},2);s.force_generate_chunk_requests();"
    "p.teleport({0,0},s);"
    "local f=s.create_entity{name='stone-furnace',position={6,-5},force=p.force};"
    "if f then f.insert{name='iron-ore',count=80};f.insert{name='coal',count=80} end;"
    "local power=s.create_entity{name='electric-energy-interface',position={7,8},force=p.force};"
    "if power then power.power_production=10000000;power.power_usage=0 end;"
    "local pole=s.create_entity{name='medium-electric-pole',position={7,5},force=p.force};"
    "local ef=s.create_entity{name='electric-furnace',position={10,5},force=p.force};"
    "if ef then ef.insert{name='iron-ore',count=80} end;"
    "p.insert{name='iron-ore',count=5};p.insert{name='iron-plate',count=5};"
    "p.insert{name='coal',count=5};"
    "end);"
    "rcon.print(ok and 'AE_CREATIVE_OK' or ('AE_CREATIVE_ERROR:'..tostring(err)))"
)


def stamp(message: str) -> None:
    print(time.strftime("%H:%M:%S") + " " + message, flush=True)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def connect(port: int, secret: str, proc: subprocess.Popen, seconds: int = 120) -> Rcon:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise RuntimeError("Graphical host exited before RCON became available")
        try:
            return Rcon(port, secret)
        except (ConnectionError, TimeoutError, OSError, ValueError):
            time.sleep(1)
    raise RuntimeError("Graphical host did not expose loopback RCON")


def observe(rcon: Rcon, kind: str) -> dict:
    response = rcon.command("/autoengineer-observe " + kind)
    value = json.loads(response)
    if not isinstance(value, dict) or value.get("protocol") != 1:
        raise RuntimeError("Unexpected registered observation protocol")
    return value


def main() -> int:
    import psutil

    if list(p for p in psutil.process_iter(["name"])
            if (p.info.get("name") or "").lower() == "factorio.exe"):
        stamp("BLOCKED: an existing Factorio instance was detected")
        return 2
    for path in (EXE, MODS, SOURCE_SAVE, SETTINGS, PLAYER_DATA):
        if not path.exists():
            stamp("BLOCKED: isolated profile prerequisite missing: " + path.name)
            return 2
    WORK.mkdir(parents=True, exist_ok=False)
    private_mods = WORK / "mods"
    shutil.copytree(MODS, private_mods)
    source_telemetry = (ROOT / "factorio-mod/autoengineer-input_2.1.23"
                        / "observation_telemetry.lua")
    destination = private_mods / "autoengineer-input_2.1.23/observation_telemetry.lua"
    shutil.copy2(source_telemetry, destination)
    data = WORK / "data"
    data.mkdir()
    (data / "saves").mkdir()
    shutil.copy2(PLAYER_DATA, data / "player-data.json")
    save = data / "saves" / "creative-disposable.zip"
    shutil.copy2(SOURCE_SAVE, save)
    before = digest(SOURCE_SAVE)
    rcon_port = free_port()
    password = secrets.token_urlsafe(26)
    config = WORK / "host.ini"
    # Credentials remain in isolated config only. Never print or version them.
    config.write_text(
        "[path]\nread-data=" + str(EXE.parents[2] / "data").replace("\\", "/")
        + "\nwrite-data=" + str(data).replace("\\", "/")
        + "\n[other]\nlocal-rcon-socket=127.0.0.1:" + str(rcon_port)
        + "\nlocal-rcon-password=" + password
        + "\nenable-blueprint-storage-cloud-sync=false\n",
        encoding="utf-8",
    )
    report: dict = {
        "source_save_unchanged": False, "graphical_host": False,
        "headless_server_started": False, "creative_attempted": False,
        "creative_completed": False, "registered_health_passed": False,
        "telemetry_observations": 0, "live_flow_rows": 0,
        "live_electrical_networks": 0, "live_active_flows": 0,
        "live_generation_watts": 0, "qt_charts_tested": False,
        "tick_rates": [], "errors": [],
    }
    log = WORK / "factorio-private.log"
    proc = None
    connection = None
    try:
        with log.open("wb") as stream:
            proc = subprocess.Popen(
                [str(EXE), "--config", str(config), "--mod-directory", str(private_mods),
                 "--host", str(save), "--server-settings", str(SETTINGS),
                 "--fullscreen=false"],
                cwd=str(EXE.parent),
                stdout=stream, stderr=subprocess.STDOUT,
                creationflags=0,
            )
        stamp("Started one graphical host on disposable save")
        connection = connect(rcon_port, password, proc)
        report["graphical_host"] = True
        deadline = time.monotonic() + 140
        status = None
        while time.monotonic() < deadline:
            try:
                status = observe(connection, "status")
                if status.get("status") == "ok":
                    break
            except (ValueError, ConnectionError, OSError):
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Graphical host never reported a connected player")
        report["registered_health_passed"] = bool(connection.health().get("character"))
        stamp("Registered status and launcher health passed")
        start_tick, start_at = status["tick"], time.monotonic()
        time.sleep(6)
        after = observe(connection, "status")
        before_rate = (after["tick"] - start_tick) / (time.monotonic() - start_at)
        report["tick_rates"].append(round(before_rate, 2))
        stamp("Pre-creative tick rate: " + str(round(before_rate, 2)))

        # Verify the console gate using a HARMLESS read-only marker before
        # issuing the creative operation. Never retry a gameplay write whose
        # execution is uncertain.
        probe = "/c rcon.print('AE_CREATIVE_GATE_OK')"
        probe_first = connection.command(probe)
        report["console_probe_first"] = probe_first[:120]
        if "AE_CREATIVE_GATE_OK" not in probe_first:
            probe_second = connection.command(probe)
            report["console_probe_second"] = probe_second[:120]
            if "AE_CREATIVE_GATE_OK" not in probe_second:
                raise RuntimeError("Disposable creative console gate not confirmed")
        report["creative_attempted"] = True
        reply = connection.command("/c " + CREATIVE)
        report["creative_reply"] = reply[:200]
        report["creative_completed"] = "AE_CREATIVE_OK" in reply
        stamp("Disposable creative setup: " +
              ("confirmed" if report["creative_completed"] else "not confirmed"))
        status_after = observe(connection, "status")
        report["creative_surface"] = status_after.get("surface")
        report["post_creative_status"] = status_after.get("status")
        time.sleep(8)
        start = observe(connection, "status")
        started = time.monotonic()
        for _ in range(5):
            payload = observe(connection, "telemetry")
            if payload.get("status") != "ok":
                report["errors"].append(
                    "Telemetry " + str(payload.get("status")) + ": "
                    + str(payload.get("reason"))[:100])
                continue
            report["telemetry_observations"] += 1
            model = build_model(payload, tick=payload.get("tick"))
            if model.available:
                report["live_flow_rows"] = max(report["live_flow_rows"], len(model.flows))
                report["live_electrical_networks"] = max(
                    report["live_electrical_networks"], len(model.networks))
                report["live_active_flows"] = max(
                    report["live_active_flows"],
                    sum(row.output_per_minute > 0 or row.input_per_minute > 0
                        for row in model.flows))
                report["live_generation_watts"] = max(
                    report["live_generation_watts"],
                    sum(network.generation_watts for network in model.networks))
            else:
                report["errors"].append("Qt rejected live telemetry: " + model.reason)
            time.sleep(2)
        latest = observe(connection, "status")
        rate = (latest["tick"] - start["tick"]) / (time.monotonic() - started)
        report["tick_rates"].append(round(rate, 2))
        stamp("Post-creative observed tick rate: " + str(round(rate, 2)))
        # Replay an actual live frame through the Qt shell and render it.
        # This tests the real presentation boundary without polling the
        # game from a widget or touching any save.
        site_packages = ROOT / ".venv/Lib/site-packages"
        if str(site_packages) not in sys.path:
            sys.path.append(str(site_packages))
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        QApplication = import_module("PySide6.QtWidgets").QApplication
        from qt_observation_bridge import UiFrame
        from qt_shell import ShellWindow

        app = QApplication.instance() or QApplication([])
        window = ShellWindow()
        window.show()
        window.apply_ui_frame(UiFrame(
            kind="telemetry", value=payload, state="observed",
            tick=payload.get("tick"), age_seconds=0.0,
            detail="Observed from disposable graphical host",
        ))
        window.show_workspace("Electrical")
        app.processEvents()
        picture = window.grab()
        saved = picture.save(str(WORK / "qt-live-electrical.png"))
        window.close()
        app.processEvents()
        report["qt_charts_tested"] = bool(saved and not picture.isNull())
        stamp("Qt live model: flows=" + str(len(model.flows))
              + ", electric networks=" + str(len(model.networks)))
        if "--with-ai" in sys.argv:
            from live_ai_probe import run as run_ai_probe

            report["ai_benchmark"] = run_ai_probe(rcon_port, password, WORK)
            stamp("Local AI benchmark: " + report["ai_benchmark"]["status"])
    except Exception as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc)[:220])
        stamp("TEST BLOCKED: " + type(exc).__name__ + ": " + str(exc)[:160])
    finally:
        if connection is not None:
            connection.close()
        if proc is not None and proc.poll() is None:
            # Only the exact graphical host PID started by this harness.
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                report["errors"].append("Harness-owned host did not stop promptly")
        report["source_save_unchanged"] = digest(SOURCE_SAVE) == before
        (WORK / "result.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        stamp("Evidence: " + str(WORK / "result.json"))
    return 0 if (report["source_save_unchanged"]
                 and report["creative_completed"]
                 and report["registered_health_passed"]
                 and report["telemetry_observations"] > 0
                 and report["live_flow_rows"] > 0
                 and report["qt_charts_tested"]
                 and ("--with-ai" not in sys.argv or
                      report.get("ai_benchmark", {}).get("status") == "pass")
                 and not report["errors"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
