"""Diagnose the game-side run's client join.

Read-only. Reports the server-side reason the client was refused.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"

TOKENS = (
    "Hosting game", "Starting RCON", "Refusing connection",
    "UserVerification", "ConnectionRequest", "JOIN", "api-login",
    "generate-user-server-key", "TLS check", "auth.factorio.com",
)


def main() -> int:
    for name in (
        "r06-game-side-factorio.log",
        "r06-game-side-client.log",
    ):
        path = EVIDENCE / name
        print("=" * 72)
        print(name, "exists=" + str(path.is_file()))
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if any(token in line for token in TOKENS):
                print("  | " + line[:220])
    return 0


if __name__ == "__main__":
    sys.exit(main())
