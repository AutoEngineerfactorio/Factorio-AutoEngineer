"""Report whether the launcher profile matches the running test server.

Only the **presence and length** of secret-bearing values is reported, never
a value. This is a read-only check.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"


def main() -> int:
    ini_path = PROFILE / "config.ini"
    text = ini_path.read_text(encoding="utf-8")
    socket = re.search(r"(?m)^local-rcon-socket=127\.0\.0\.1:(\d+)\s*$", text)
    password = re.search(r"(?m)^local-rcon-password=([^\s]+)\s*$", text)
    print(f"launcher_socket={socket.group(1) if socket else None}")
    print(f"launcher_password_len={len(password.group(1)) if password else 0}")

    secret_path = RUNTIME / "rcon.secret.json"
    if secret_path.is_file():
        data = json.loads(secret_path.read_text(encoding="utf-8"))
        live = data.get("rcon_password", "")
        print(f"live_password_len={len(live)}")
        print(f"passwords_match={bool(password) and password.group(1) == live}")

    # The live server's own config records the port it actually listens on.
    live_ini = RUNTIME / "server" / "config.ini"
    if live_ini.is_file():
        live_text = live_ini.read_text(encoding="utf-8")
        live_socket = re.search(
            r"(?m)^local-rcon-socket=127\.0\.0\.1:(\d+)\s*$", live_text)
        live_password = re.search(
            r"(?m)^local-rcon-password=([^\s]+)\s*$", live_text)
        print(f"server_config_socket={live_socket.group(1) if live_socket else None}")
        print(f"server_config_password_len={len(live_password.group(1)) if live_password else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
