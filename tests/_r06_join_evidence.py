"""Check whether the successful live run actually joined the server.

Read-only. The harness records ``client_joined`` by scanning the *server*
log for "Player .* joined". This reports every join-related line in the
server log of each run, so the recorded flag can be checked against the
actual evidence.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"

RUNS = ("modded-live-r06c", "r06-game-side", "r06-game-side-b")

JOIN_PATTERNS = (
    re.compile(r"\[JOIN\]"),
    re.compile(r"joined the game"),
    re.compile(r"Peer.*Connected", re.I),
    re.compile(r"stateChanged peerID.*newState\(InGame\)"),
    re.compile(r"Serving map\("),
)


def main() -> int:
    for run in RUNS:
        print("=" * 74)
        print(run)
        report_path = EVIDENCE / f"{run}.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            print(f"  recorded client_joined = {report.get('client_joined')}")
        server_log = EVIDENCE / f"{run}-factorio.log"
        if not server_log.is_file():
            print("  server log MISSING")
            continue
        lines = server_log.read_text(encoding="utf-8", errors="replace").splitlines()
        hits = 0
        for index, line in enumerate(lines):
            if any(pattern.search(line) for pattern in JOIN_PATTERNS):
                hits += 1
                print(f"  [{index}] {line[:200]}")
        print(f"  join_evidence_lines = {hits}")
        # The harness regex, applied to the same log.
        matched = any(re.search(r"Player .* joined", line) for line in lines)
        print(f"  harness_regex_PLAYER_joined_matches = {matched}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
