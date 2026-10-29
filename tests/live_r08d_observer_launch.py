"""Run the dashboard observer with a live stdin pipe and visible output.

It runs the REAL observer module against the already running Factorio 2.1.23
with the launcher's own profile environment and keeps stdin open, exactly as
the dashboard does. Any failure is then visible in the console instead of
hidden inside a pipe.

It performs no gameplay action and never writes to the save.

Usage:
    python -B tests/live_r08d_observer_launch.py
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

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"
PATCHED_DLL = RUNTIME / "backend-patched-2.1.23" / "FactorioMCP.dll"
SECONDS = 25


def log(message: str) -> None:
    print(str(message), flush=True)


def main() -> int:
    text = CONFIG.read_text(encoding="utf-8")
    socket_match = re.search(r"local-rcon-socket=(\S+)", text)
    if socket_match is None:
        raise ValueError("local-rcon-socket not found in config")
    port = int(socket_match.group(1).rsplit(":", 1)[1])
    password_match = re.search(r"local-rcon-password=(\S+)", text)
    if password_match is None:
        raise ValueError("local-rcon-password not found in config")
    password = password_match.group(1)
    log(f"RCON_PORT={port}")

    agent_config = RUNTIME / "agent.config.r08d.json"
    agent_config.write_text(
        json.dumps(
            {
                "dotnet_command": "dotnet",
                "mcp_server_dll": str(PATCHED_DLL),
                "rcon_host": "127.0.0.1",
                "rcon_port": port,
                "llm_api_url": "http://127.0.0.1:8083/v1",
                "llm_model": "FrogNano-4B",
            }
        ),
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
        env=env,
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    lines: list[str] = []

    def reader():
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip())
            if len(lines) > 40:
                break

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    time.sleep(SECONDS)
    if proc.poll() is None:
        proc.terminate()
    log(f"EXIT={proc.poll()}")
    log(f"LINE_COUNT={len(lines)}")
    for line in lines[:6]:
        log("  " + line[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
