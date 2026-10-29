"""Offline check: how long does one map draw take with a real frame?

The dashboard draws the map on the Tk main thread. If one draw is slow the
window stops responding and the live frames pile up unread, which is what
"the dashboard does not update" looks like. This times the REAL draw path
with a REAL observed frame and the REAL canvas size.

Read-only with respect to the game.

Usage:
    python -B tests/_r08d_draw_timing.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
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
        raise ValueError("local-rcon-socket is missing from config.ini")
    port = int(socket_match.group(1).rsplit(":", 1)[1])
    password_match = re.search(r"local-rcon-password=(\S+)", text)
    if password_match is None:
        raise ValueError("local-rcon-password is missing from config.ini")
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
    frame = parse_frame(frame_text)
    if frame is None:
        log("PARSE_FRAME_NONE")
        return 1

    from dashboard_view import LiveView

    view = LiveView.__new__(LiveView)
    view.last = frame
    view.received = time.monotonic()
    view.available = True
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
    setattr(view, "map_image", None)
    view.__dict__["raster_key"] = None
    view.canvas = MagicMock()
    view.canvas.winfo_width.return_value = 1400
    view.canvas.winfo_height.return_value = 900

    calls = {"rect": 0, "oval": 0, "line": 0, "text": 0, "image": 0}

    def make(name):
        def _call(*args, **kwargs):
            calls[name] = calls.get(name, 0) + 1
            return MagicMock()
        return _call

    view.canvas.create_rectangle = make("rect")
    view.canvas.create_oval = make("oval")
    view.canvas.create_line = make("line")
    view.canvas.create_text = make("text")
    view.canvas.create_image = make("image")
    view.canvas.create_polygon = make("line")

    # The raster needs a Tk root for its PhotoImage; the entity drawing does
    # not, so it is timed separately.
    view.draw_raster = MagicMock()
    began = time.perf_counter()
    view.draw()
    elapsed = time.perf_counter() - began
    log(f"DRAW_SECONDS={elapsed:.3f}")
    log(f"CANVAS_CALLS={calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
