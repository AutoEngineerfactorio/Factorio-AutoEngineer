"""Offline check: push a real published frame through the real view update.

It captures one published observer frame and calls the REAL dashboard view's
``update_frame`` with a headless stand-in for the Tk canvas, so a failure in
the view is reported with its exact exception instead of being reduced to
"observation unavailable" by the dashboard's broad handler.

Read-only with respect to the game.

Usage:
    python -B tests/_r08d_view_frame.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"
PATCHED_DLL = RUNTIME / "backend-patched-2.1.23" / "FactorioMCP.dll"


def log(message: str) -> None:
    print(str(message), flush=True)


def main() -> int:
    from dashboard_feed import parse_frame

    text = CONFIG.read_text(encoding="utf-8")
    socket_match = re.search(r"local-rcon-socket=(\S+)", text)
    if socket_match is None:
        raise ValueError("local-rcon-socket not found in config")
    socket_value = socket_match.group(1)
    port = int(socket_value.rsplit(":", 1)[1])
    password_match = re.search(r"local-rcon-password=(\S+)", text)
    if password_match is None:
        raise ValueError("local-rcon-password not found in config")
    password = password_match.group(1)

    agent_config = RUNTIME / "agent.config.r08d.json"
    agent_config.write_text(
        json.dumps({
            "dotnet_command": "dotnet",
            "mcp_server_dll": str(PATCHED_DLL),
            "rcon_host": "127.0.0.1",
            "rcon_port": port,
            "llm_api_url": "http://127.0.0.1:8083/v1",
            "llm_model": "FrogNano-4B",
        }),
        encoding="utf-8",
    )
    env = dict(
        os.environ,
        AUTOENGINEER_CONFIG=str(agent_config),
        AUTOENGINEER_HOME=str(RUNTIME),
        FACTORIO_RCON_PASSWORD=password,
        AUTOENGINEER_MODE="helper",
    )
    proc = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "agent" / "dashboard_observer.py")],
        env=env, cwd=str(ROOT),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    frame_text = ""

    def reader():
        nonlocal frame_text
        assert proc.stdout is not None
        for line in proc.stdout:
            frame_text = line.rstrip("\n")
            break

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + 20
    while not frame_text and time.monotonic() < deadline:
        time.sleep(0.2)
    if proc.poll() is None:
        proc.terminate()
    if not frame_text:
        log("NO_FRAME")
        return 1

    frame = parse_frame(frame_text)
    if frame is None:
        log("PARSE_FRAME_NONE")
        return 1
    log(f"FRAME_OK status={frame.get('status')}")

    # Drive the real view logic without a display.
    from dashboard_view import LiveView

    view = LiveView.__new__(LiveView)
    view.last = None
    view.received = None
    view.available = False
    view.offset = {"x": 0.0, "y": 0.0}
    view.icons = {}
    view.quality_icons = {}
    view.slot_hits = {}
    view.slot_nodes = {}
    view._inventory_layout = None
    view._inventory_fingerprint = None
    view._inventory_status_base = ""
    view.viewport_sender = None
    view._last_viewport_request = None
    view.status = MagicMock()
    view.zoom = MagicMock()
    view.zoom.get.return_value = "128"
    view.layers = {k: MagicMock() for k in (
        "resource", "nature", "building", "enemy", "history", "goals", "grid",
        "player_name", "pollution", "electric", "logistics", "turrets",
        "stations", "tags",
    )}
    for layer in view.layers.values():
        layer.get.return_value = True
    view.overlay_entries = {}
    view.overlay_menu = MagicMock()
    view.inventory = MagicMock()
    view.draw = MagicMock()
    view.canvas = MagicMock()
    view.canvas.winfo_width.return_value = 1400
    view.canvas.winfo_height.return_value = 900

    try:
        view.update_frame(frame)
        log("VIEW_UPDATE_OK")
        log(f"  last_is_none={view.last is None}")
        log(f"  available={view.available}")
    except Exception:
        log("VIEW_UPDATE_FAILED")
        log(traceback.format_exc())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
