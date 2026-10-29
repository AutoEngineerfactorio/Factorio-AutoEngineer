"""Phase 1 probe: report the live server's actual state without credentials.

Reports only the presence and length of secret-bearing values, never the
value itself. This is a read-only probe; it never starts or stops a process.
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / ".local" / "live-pillow-2.1.23"


def probe_ports(ports) -> dict:
    result = {}
    for port in ports:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                result[port] = "open"
        except Exception as exc:  # noqa: BLE001 - report the class only
            result[port] = f"closed:{type(exc).__name__}"
    return result


def main() -> int:
    secret_path = LIVE / "rcon.secret.json"
    if secret_path.exists():
        secret = json.loads(secret_path.read_text(encoding="utf-8"))
        print(f"rcon_secret_present=True rcon_password_len={len(secret.get('rcon_password', ''))}")
    else:
        print("rcon_secret_present=False")

    profile = LIVE / "client-profile" / "data" / "player-data.json"
    if profile.exists():
        data = json.loads(profile.read_text(encoding="utf-8"))
        token = data.get("service-token", "")
        user = data.get("service-username", "")
        print(f"client_profile_present=True token_len={len(token)} username_len={len(user)}")
    else:
        print("client_profile_present=False")

    ports = probe_ports((27161, 27109, 34261, 27015))
    for port, state in ports.items():
        print(f"port_{port}={state}")

    server_log = LIVE / "server-profile" / "factorio-current.log"
    if not server_log.exists():
        candidate = LIVE / "server-profile"
        logs = sorted(candidate.glob("*.log")) if candidate.exists() else []
        print(f"server_profile_log_present=False candidates={[p.name for p in logs[-3:]]}")
    else:
        lines = server_log.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"server_profile_log_present=True lines={len(lines)}")
        for line in lines[-12:]:
            print("  LOG " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
