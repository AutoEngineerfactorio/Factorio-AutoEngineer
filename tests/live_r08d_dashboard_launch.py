"""Start the dashboard with the launcher's own profile environment.

This launches the REAL dashboard window against the already running
Factorio 2.1.23, with the freshly rebuilt patched backend, using exactly the
environment variables the launcher sets for a dashboard component:

* ``AUTOENGINEER_CONFIG``  - the private agent config with the DLL and port
* ``AUTOENGINEER_HOME``    - the profile runtime directory
* ``FACTORIO_RCON_PASSWORD`` - the profile's RCON password
* ``AUTOENGINEER_MODE``    - ``helper`` (read-only observation)

It starts no Factorio process, performs no gameplay action and never writes
to the save. It only starts the dashboard, which is a read-only observer.

Usage:
    python -B tests/live_r08d_dashboard_launch.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
LAUNCHER_JSON = PROFILE / "launcher.local.json"
SECRET = PROFILE / "rcon.secret.json"
CONFIG = PROFILE / "config.ini"
RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"
PATCHED_DLL = RUNTIME / "backend-patched-2.1.23" / "FactorioMCP.dll"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")


def log(message: str) -> None:
    print(str(message), flush=True)


def read_port() -> int:
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"local-rcon-socket=(\S+)", text)
    if not match:
        raise SystemExit("RCON socket not found in config.ini")
    return int(match.group(1).rsplit(":", 1)[1])


def read_password() -> str:
    if SECRET.is_file():
        data = json.loads(SECRET.read_text(encoding="utf-8-sig"))
        for key in ("password", "rcon_password", "secret"):
            if isinstance(data.get(key), str) and data[key]:
                return data[key]
    # The graphical-host profile keeps the password in config.ini.
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"local-rcon-password=(\S+)", text)
    if not match:
        raise SystemExit("RCON password not found")
    return match.group(1)


def main() -> int:
    if not PATCHED_DLL.is_file():
        log(f"MISSING_PATCHED_DLL={PATCHED_DLL}")
        return 2
    profile = json.loads(LAUNCHER_JSON.read_text(encoding="utf-8-sig"))
    port = read_port()
    password = read_password()
    log(f"RCON_PORT={port}")
    log(f"PATCHED_DLL={PATCHED_DLL} bytes={PATCHED_DLL.stat().st_size}")

    agent_config = RUNTIME / "agent.config.r08d.json"
    agent_config.write_text(
        json.dumps(
            {
                "dotnet_command": profile.get("dotnet_command", "dotnet"),
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
        AUTOENGINEER_WORLD=profile.get("world_id", "autoengineer-isolated-2.1.23"),
    )
    proc = subprocess.Popen(
        [str(PYTHONW), "-u", str(ROOT / "agent" / "autoengineer_dashboard.py")],
        env=env,
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log(f"DASHBOARD_PID={proc.pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
