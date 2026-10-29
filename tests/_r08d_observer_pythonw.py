"""Offline check: run the observer exactly as the dashboard spawns it.

The dashboard spawns the observer with ``pythonw.exe -u dashboard_observer.py``,
a piped stdin, a piped stdout and the dashboard's own environment. This
reproduces that exactly and reports what the observer publishes, so a failure
is visible instead of hidden inside the dashboard's pipe.

Read-only with respect to the game.

Usage:
    python -B tests/_r08d_observer_pythonw.py
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
PYTHONW = Path(sys.executable).with_name("pythonw.exe")


def log(message: str) -> None:
    print(str(message), flush=True)


def main() -> int:
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
        [str(PYTHONW), "-u", str(ROOT / "agent" / "dashboard_observer.py")],
        env=env,
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    log(f"OBSERVER_PID={proc.pid} exe={PYTHONW}")
    lines: list[str] = []

    def reader():
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line.rstrip())
            if len(lines) >= 5:
                break

    threading.Thread(target=reader, daemon=True).start()
    time.sleep(20)
    alive = proc.poll() is None
    log(f"ALIVE_AFTER_20S={alive} LINES={len(lines)}")
    if alive:
        proc.terminate()
    for line in lines[:5]:
        log("  " + line[:260])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
