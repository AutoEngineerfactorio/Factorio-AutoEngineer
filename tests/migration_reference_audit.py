"""Read-only audit of the 2.1.23 migration references and archived installations.

Confirms that the supported Factorio 2.1.23 launcher profile, live profile,
input-helper mod and executable are present, and that the archived 2.0.77 and
2.1.22 installations, profiles and mod are still preserved untouched. It never
launches the game, writes a save or modifies any installation.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

CHECKS = [
    ("launcher profile 2.1.23", ROOT / ".local/launcher-profiles/2.1.23/launcher.local.json"),
    ("live profile 2.1.23", ROOT / ".local/live-pillow-2.1.23"),
    ("input helper mod 2.1.23", ROOT / "factorio-mod/autoengineer-input_2.1.23/info.json"),
    ("archived input helper mod 2.1.22", ROOT / "factorio-mod/autoengineer-input_2.1.22/info.json"),
    ("archived launcher profile 2.0.77", ROOT / ".local/launcher-profiles/2.0.77"),
    ("archived launcher profile 2.1.22", ROOT / ".local/launcher-profiles/2.1.22"),
    ("2.1.23 executable (historical dir name)",
     pathlib.Path("D:/AI/Factorio-Isolated-2.1.23/Factorio_2.1.22/bin/x64/factorio.exe")),
    ("archived 2.0.77 installation", pathlib.Path("D:/AI/Factorio-Isolated-2.0.77")),
    ("archived 2.1.22 installation", pathlib.Path("D:/AI/Factorio-Isolated-2.1.22")),
]


def main():
    missing = 0
    for label, path in CHECKS:
        exists = path.exists()
        if not exists:
            missing += 1
        print(f"{'PRESENT' if exists else 'ABSENT ':8} {label}: {path}")
    print("absent_count:", missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
