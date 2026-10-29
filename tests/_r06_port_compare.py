"""Compare the client join outcome of the successful and failed live runs.

Read-only. The successful run and the failures differ in the ports used and
in whether the client reached the auth server. This reports both.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"

RUNS = (
    "modded-live-r06c",
    "r06-game-side",
    "r06-game-side-b",
)


def main() -> int:
    for run in RUNS:
        print("=" * 74)
        print(run)
        report_path = EVIDENCE / f"{run}.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            print(f"  game_port = {report.get('game_port')}")
            print(f"  rcon_port = {report.get('rcon_port')}")
            print(f"  client_joined = {report.get('client_joined')}")
        server_log = EVIDENCE / f"{run}-factorio.log"
        client_log = EVIDENCE / f"{run}-client.log"
        for label, path in (("server", server_log), ("client", client_log)):
            if not path.is_file():
                print(f"  {label}: MISSING")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            auth = [
                line for line in text.splitlines()
                if "auth.factorio.com" in line or "api-login" in line
                or "user-server-key" in line
            ]
            refused = [
                line for line in text.splitlines() if "Refusing connection" in line
            ]
            print(f"  {label}_auth_calls = {len(auth)}")
            for line in auth:
                print(f"      | {line[:180]}")
            for line in refused:
                print(f"      | {line[:180]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
