"""Report the live-test paths the harness depends on (OFFLINE)."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE = ROOT / ".local" / "live-pillow-2.1.23"
OUT = ROOT / "memory" / "_p7_paths.txt"

lines = []
for relative in (
    "server/config.ini",
    "server/data/saves",
    "client-profile/data/player-data.json",
    "client-profile/config.ini",
    "rcon.secret.json",
    "evidence",
    "backend-patched-2.1.23/FactorioMCP.dll",
):
    path = LIVE / relative
    lines.append(f"{'OK ' if path.exists() else 'MISSING'} {path}")

lines.append("")
lines.append("--- live tree (2 levels) ---")
if LIVE.is_dir():
    for child in sorted(LIVE.iterdir()):
        lines.append(f"  {child.name}{'/' if child.is_dir() else ''}")

lines.append("")
lines.append("--- launcher profile ---")
launcher = ROOT / ".local" / "launcher-profiles" / "2.1.23"
if launcher.is_dir():
    for child in sorted(launcher.iterdir()):
        lines.append(f"  {child.name}{'/' if child.is_dir() else ''}")
    saves = launcher / "data" / "saves"
    if saves.is_dir():
        lines.append("  data/saves:")
        for save in sorted(saves.glob("*.zip")):
            lines.append(f"    {save.name} {save.stat().st_size}")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("written", OUT)
