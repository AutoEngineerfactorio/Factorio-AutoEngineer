"""Offline check: how long is one published observer frame?

The dashboard reads the observer's stdout one character at a time and splits
any buffer longer than 1 MiB. If one published frame is longer than that,
the frame is cut in half and the dashboard can never parse it. This measures
the real frame length against the real split threshold.

Read-only with respect to the game.

Usage:
    python -B tests/_r08d_frame_size.py
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

# The dashboard's own split threshold, from autoengineer_dashboard.py.
SPLIT_THRESHOLD = 1048576


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
    lengths: list[int] = []
    first: str = ""

    def reader():
        nonlocal first
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            lengths.append(len(line))
            if not first:
                first = line
            if len(lengths) >= 5:
                break

    threading.Thread(target=reader, daemon=True).start()
    time.sleep(20)
    if proc.poll() is None:
        proc.terminate()
    log(f"FRAME_LENGTHS={lengths}")
    log(f"SPLIT_THRESHOLD={SPLIT_THRESHOLD}")
    if lengths:
        biggest = max(lengths)
        log(f"BIGGEST={biggest} EXCEEDS_THRESHOLD={biggest > SPLIT_THRESHOLD}")
        log(f"FRAGMENTS_AT_THRESHOLD={biggest // SPLIT_THRESHOLD + 1}")
    if first:
        log(f"FIRST_PREFIX={first[:40]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
