"""Run the dashboard's own read-only observer once and report its output.

This reproduces exactly what the dashboard's observer child does, so the
observer's own error message is visible instead of being swallowed by the
dashboard's reader thread.

It is read-only: the observer only calls the bounded display read.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"
PATCHED_DLL = RUNTIME / "backend-patched-2.1.23" / "FactorioMCP.dll"


def main() -> int:
    import json
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "tests"))
    import live_r06_game_side_verify as harness
    import r06_live_environment as live_env

    secret = json.loads(
        (RUNTIME / "rcon.secret.json").read_text(encoding="utf-8"))
    password = secret["rcon_password"]
    port = 27161

    # The observer reads the launcher profile's config, so it is aligned with
    # the running server for the duration of this probe.
    config_path = PROFILE / "config.ini"
    original = config_path.read_text(encoding="utf-8")
    backup = config_path.with_suffix(".ini.observer-probe-backup")
    backup.write_text(original, encoding="utf-8")
    aligned = re.sub(
        r"(?m)^local-rcon-socket=127\.0\.0\.1:\d+\s*$",
        f"local-rcon-socket=127.0.0.1:{port}", original)
    aligned = re.sub(
        r"(?m)^local-rcon-password=[^\s]+\s*$",
        f"local-rcon-password={password}", aligned)
    config_path.write_text(aligned, encoding="utf-8")

    try:
        # The catalog observation needs a connected player with a character,
        # so the graphical client is joined before the observer reads.
        client_profile = live_env.prepare_client_profile(
            "r06-observer", RUNTIME / "server" / "config.ini", port)
        report: dict = {}
        client, _ = harness.start_client(
            "r06-observer", client_profile / "config.ini", 34261, report)
        joined = harness.wait_for_join(
            client, live_env.SERVER_DATA, client_profile / "data", report)
        print(f"CLIENT_JOINED={joined}")

        env = dict(os.environ)
        env["AUTOENGINEER_MODE"] = "helper"
        env["AUTOENGINEER_ENABLE_LIVE_MAP"] = "1"
        env["FACTORIO_RCON_PASSWORD"] = password
        proc = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "agent" / "dashboard_observer.py")],
            env=env, cwd=str(ROOT / "agent"),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace",
        )
        try:
            out, _ = proc.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        print("---- OBSERVER OUTPUT ----")
        for line in (out or "").splitlines()[:40]:
            print(line[:400])
        print("---- END ----")
        if client.poll() is None:
            client.terminate()
        return 0
    finally:
        config_path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
        print("PROFILE_RESTORED=True")


if __name__ == "__main__":
    raise SystemExit(main())
