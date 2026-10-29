"""Offline check: feed a real observer frame through the dashboard's parser.

It runs the REAL observer, captures one published frame and pushes it through
the REAL dashboard frame parsing and the REAL feed validation, so any
rejection is reported with the exact failing field instead of being hidden
behind "observation unavailable".

Read-only with respect to the game.

Usage:
    python -B tests/_r08d_frame_check.py
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"
PATCHED_DLL = RUNTIME / "backend-patched-2.1.23" / "FactorioMCP.dll"


def log(message: str) -> None:
    print(str(message), flush=True)


def main() -> int:
    from dashboard_feed import PREFIX

    text = CONFIG.read_text(encoding="utf-8")
    socket_match = re.search(r"local-rcon-socket=(\S+)", text)
    if socket_match is None:
        raise ValueError("local-rcon-socket not found in config")
    port = int(socket_match.group(1).rsplit(":", 1)[1])
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
    frames: list[str] = []
    other: list[str] = []

    def reader():
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith(PREFIX):
                frames.append(line.rstrip())
            else:
                other.append(line.rstrip())
            if len(frames) >= 3:
                break

    threading.Thread(target=reader, daemon=True).start()
    time.sleep(20)
    if proc.poll() is None:
        proc.terminate()

    log(f"FRAMES={len(frames)} OTHER={len(other)}")
    for line in other[:5]:
        log("  OTHER " + line[:300])
    if not frames:
        log("NO_FRAMES_CAPTURED")
        return 1

    raw_text = frames[-1]
    raw = json.loads(raw_text[len(PREFIX):])
    log(f"RAW_KEYS={sorted(raw.keys())}")

    # The dashboard parses the published frame with parse_frame().
    from dashboard_feed import parse_frame

    try:
        frame = parse_frame(raw_text)
        if frame is None:
            log("PARSE_FRAME_NONE")
            return 1
        log(f"PARSE_FRAME_OK status={frame.get('status')}")
        log(f"  position={frame.get('position')} surface={frame.get('surface')}")
        log(f"  terrain_present={'terrain' in frame}")
        log(f"  map_present={'map' in frame and frame['map'] is not None}")
        merged_map = frame.get("map")
        if isinstance(merged_map, dict):
            log(f"  map_entities={len(merged_map.get('entities') or [])}")
            kinds: dict[str, int] = {}
            for e in merged_map.get("entities") or []:
                kinds[e.get("kind")] = kinds.get(e.get("kind"), 0) + 1
            log(f"  map_kinds={kinds}")
        terrain = frame.get("terrain")
        if isinstance(terrain, dict):
            log(f"  terrain_keys={sorted(terrain.keys())}")
            log(f"  terrain_entities={len(terrain.get('entities') or [])}")
    except Exception:
        log("PARSE_FRAME_FAILED")
        log(traceback.format_exc())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
