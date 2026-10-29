"""Offline check: replicate the dashboard's observer spawn and reader exactly.

It reproduces ``Dashboard.start_observer``'s exact Popen parameters and the
exact ``read_output`` loop, then reports what the dashboard would have
received. This isolates the last unverified link between the observer and
the dashboard.

Read-only with respect to the game.

Usage:
    python -B tests/_r08d_reader_replica.py
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from dashboard_feed import PREFIX, parse_frame  # noqa: E402
from session_safety import PROMPT  # noqa: E402

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
    # Exactly the dashboard's start_observer parameters, including the
    # hidden-window startup info.
    startup = subprocess.STARTUPINFO() if os.name == "nt" else None
    if startup:
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
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
        startupinfo=startup,
    )
    log(f"OBSERVER_PID={proc.pid}")

    q: queue.Queue = queue.Queue()

    def read_output():
        stdout = proc.stdout
        assert stdout is not None
        buffer = ""
        while True:
            ch = stdout.read(1)
            if ch == "":
                break
            buffer += ch
            if buffer.endswith(PROMPT):
                q.put(("line", buffer))
                buffer = ""
            elif ch == "\n":
                q.put(("line", buffer))
                buffer = ""
            elif len(buffer) > 1048576:
                q.put(("line", buffer))
                buffer = ""

    threading.Thread(target=read_output, daemon=True).start()

    deadline = time.monotonic() + 25
    received = []
    while time.monotonic() < deadline and len(received) < 3:
        try:
            kind, value = q.get(timeout=1.0)
        except queue.Empty:
            continue
        received.append(value)
    if proc.poll() is None:
        proc.terminate()
    log(f"RECEIVED_LINES={len(received)}")
    for index, value in enumerate(received):
        starts = value.startswith(PREFIX)
        log(f"  line {index}: len={len(value)} starts_with_prefix={starts}")
        if starts:
            try:
                frame = parse_frame(value)
                log(f"    PARSE_OK status={frame.get('status') if frame else None}")
            except Exception as exc:
                log(f"    PARSE_FAILED {type(exc).__name__}: {exc}")
        else:
            log(f"    head={value[:120]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
