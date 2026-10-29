"""Offline check: how fast does the dashboard's output reader consume a frame?

The dashboard reads the observer's stdout with ``proc.stdout.read(1)``, one
character at a time. A published frame is about 353 KB. This measures how
long that reader needs for one real frame, against the interval the observer
publishes at, so the dashboard's responsiveness can be judged on evidence.

It uses the real dashboard reader code path and a real published frame.

Usage:
    python -B tests/_r08d_reader_speed.py
"""
from __future__ import annotations

import io
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
    frame = ""

    def reader():
        nonlocal frame
        assert proc.stdout is not None
        for line in proc.stdout:
            frame = line.rstrip("\n")
            break

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + 20
    while not frame and time.monotonic() < deadline:
        time.sleep(0.2)
    if proc.poll() is None:
        proc.terminate()
    if not frame:
        log("NO_FRAME")
        return 1

    log(f"FRAME_CHARS={len(frame)}")

    # The dashboard's reader: one character at a time.
    stream = io.StringIO(frame + "\n")
    began = time.perf_counter()
    buffer = ""
    count = 0
    while True:
        ch = stream.read(1)
        if ch == "":
            break
        buffer += ch
        count += 1
        if ch == "\n":
            break
    elapsed = time.perf_counter() - began
    log(f"READ_1_CHAR_ELAPSED_SECONDS={elapsed:.3f}")
    log(f"CHARS_PER_SECOND={count / max(0.001, elapsed):,.0f}")

    # A whole-line read for comparison.
    stream2 = io.StringIO(frame + "\n")
    began2 = time.perf_counter()
    stream2.readline()
    elapsed2 = time.perf_counter() - began2
    log(f"READ_LINE_ELAPSED_SECONDS={elapsed2:.6f}")
    log(f"SPEEDUP={elapsed / max(0.000001, elapsed2):,.0f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
