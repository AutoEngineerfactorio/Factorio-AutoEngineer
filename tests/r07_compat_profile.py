"""Create the fresh disposable Factorio 2.1.23 profile for the R07 compat test.

This helper only writes a configuration file and empty directory scaffolding. It
never launches Factorio, never creates a save, never writes to an existing
profile and never touches a personal save. Running the game is the human
operator's action and needs their explicit approval.

The profile root is ``.local/r07-compat-2123``. It is inside the gitignored
``.local/`` tree, so the captured blueprint fixtures can never be committed.
"""

import argparse
import configparser
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_NAME = "r07-compat-2123"
PROFILE_ROOT = ROOT / ".local" / PROFILE_NAME
EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")
GAME_DATA = EXE.parents[2] / "data"
EXPECTED_VERSION = "2.1.23"


def build_config(profile_root: Path) -> configparser.ConfigParser:
    """Return a config.ini that isolates every writable path under the profile.

    ``write-data`` is redirected to the profile, so saves, script-output and
    the other writable game state land inside the disposable profile instead
    of the default Factorio user directory.
    """
    ini = configparser.ConfigParser(interpolation=None)
    ini["path"] = {
        "read-data": GAME_DATA.as_posix(),
        "write-data": (profile_root / "data").as_posix(),
    }
    ini["other"] = {
        # No blueprint cloud sync: a fixture must not leave the machine.
        "enable-blueprint-storage-cloud-sync": "false",
    }
    return ini


def verify_executable() -> str:
    """Confirm the executable reports the pinned 2.1.23 build. Fails closed."""
    import subprocess

    try:
        result = subprocess.run(
            [str(EXE), "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except OSError as exc:
        raise SystemExit(f"EXE_NOT_RUNNABLE: {EXE}: {exc}") from exc
    reported = (result.stdout + result.stderr).strip()
    expected = "2.1.23 (build 87750, win64, full)"
    if expected not in reported:
        raise SystemExit(f"UNEXPECTED_VERSION: expected {expected!r}, reported {reported!r}")
    return reported


def prepare() -> dict:
    """Create the disposable profile scaffolding. Idempotent and non-destructive."""
    if not EXE.exists():
        raise SystemExit(f"EXE_MISSING: {EXE}")
    reported = verify_executable()
    if PROFILE_ROOT.resolve() == ROOT:
        raise SystemExit("REFUSING: profile root resolves to the repository root")
    profile_root = PROFILE_ROOT
    data = profile_root / "data"
    saves = data / "saves"
    saves.mkdir(parents=True, exist_ok=True)
    (profile_root / "fixtures").mkdir(parents=True, exist_ok=True)

    cfg = profile_root / "config.ini"
    ini = build_config(profile_root)
    with cfg.open("w", encoding="utf-8") as handle:
        ini.write(handle, space_around_delimiters=False)

    manifest = {
        "profile": PROFILE_NAME,
        "purpose": "R07-B genuine export/import compatibility test (disposable)",
        "game_version": EXPECTED_VERSION,
        "version_reported": reported,
        "exe": str(EXE),
        "read_data": str(GAME_DATA),
        "write_data": str(data),
        "config": str(cfg),
        "saves_dir": str(saves),
        "fixtures_dir": str(profile_root / "fixtures"),
        "launch_command": (
            f'"{EXE}" --config "{cfg}"'
        ),
        "no_personal_save_touched": True,
        "gitignored": True,
    }
    (profile_root / "profile_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove the disposable profile first. Refuses if it is not the exact profile root.",
    )
    args = parser.parse_args()

    if args.reset:
        if PROFILE_ROOT.exists():
            if PROFILE_ROOT.name != PROFILE_NAME:
                raise SystemExit("REFUSING: unexpected profile directory name")
            shutil.rmtree(PROFILE_ROOT)
            print("RESET=True")

    manifest = prepare()
    print("PROFILE_READY=True")
    print("PROFILE_ROOT=" + str(PROFILE_ROOT))
    print("CONFIG=" + manifest["config"])
    print("FIXTURES=" + manifest["fixtures_dir"])
    print("LAUNCH=" + manifest["launch_command"])
    print("EXE=" + manifest["exe"])
    print("VERSION_REPORTED=" + manifest["version_reported"].splitlines()[0])
    print("NO_GAME_LAUNCHED=True")
    print("NO_SAVE_CREATED=True")


if __name__ == "__main__":
    main()
