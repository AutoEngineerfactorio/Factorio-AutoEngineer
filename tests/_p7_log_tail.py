"""Print the tail of the most recent Phase 7 server log (OFFLINE)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
evidence = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"
tag = sys.argv[1] if len(sys.argv) > 1 else ""
pattern = f"p7-{tag}*" if tag else "p7-*"

runs = sorted((p for p in evidence.glob(pattern) if p.is_dir()),
              key=lambda p: p.stat().st_mtime)
if not runs:
    print("NO RUN DIRECTORY")
    raise SystemExit(1)

run = runs[-1]
log = run / "server.log"
text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
lines = text.splitlines()
interesting = [
    line for line in lines
    if ("Error" in line or "error" in line or "Goodbye" in line
        or "rcon" in line.lower() or "RCON" in line
        or "Started" in line or "hosting" in line.lower()
        or "Player" in line or "join" in line.lower())
]
print(f"RUN={run}")
print(f"TOTAL_LINES={len(lines)}")
print("--- interesting lines (last 50) ---")
for line in interesting[-50:]:
    print(line)
print("--- last 15 lines ---")
for line in lines[-15:]:
    print(line)
