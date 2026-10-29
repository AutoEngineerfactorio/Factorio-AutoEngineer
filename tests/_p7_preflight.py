"""R09 Phase 7 preflight: report the live-test starting state.

Read-only. It inspects the two test profiles, the disposable saves, the
installed mod and the authentication state. It starts no process and writes
no save.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "memory" / "_p7_preflight.json"

VANILLA_ROOT = pathlib.Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22")
LAUNCHER = ROOT / ".local" / "launcher-profiles" / "2.1.23"
LIVE = ROOT / ".local" / "live-pillow-2.1.23"
MOD_SOURCE = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"

PROFILES = {
    "vanilla-space-age": {
        "root": VANILLA_ROOT,
        "mods": VANILLA_ROOT / "mods" / "autoengineer-input_2.1.23",
        "config": VANILLA_ROOT / "config" / "config.ini",
        "player_data": VANILLA_ROOT / "data" / "player-data.json",
    },
    "pyanodons": {
        "root": LIVE,
        "mods": ROOT / ".local" / "mod-test-mods" / "2.1.23" / "autoengineer-input_2.1.23",
        "config": LIVE / "client-profile" / "config.ini",
        "player_data": LIVE / "client-profile" / "data" / "player-data.json",
    },
}

SAVE_DIRS = {
    "launcher": LAUNCHER / "data" / "saves",
    "live-server": LIVE / "server" / "data" / "saves",
    "vanilla": VANILLA_ROOT / "saves",
}


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def auth_state(path: pathlib.Path) -> dict:
    """Report whether a player-data file carries a token, without reading it.

    The Factorio ``player-data.json`` keeps the authentication state in the
    flat keys ``service-token`` and ``service-username``. Only the presence
    and the length are reported, so the token can never reach a report.
    """
    if not path.is_file():
        return {"present": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"present": True, "readable": False, "error": type(exc).__name__}
    token = data.get("service-token") if isinstance(data, dict) else None
    username = data.get("service-username") if isinstance(data, dict) else None
    return {
        "present": True,
        "readable": True,
        "has_token": bool(token),
        "token_length": len(token) if isinstance(token, str) else 0,
        "has_username": bool(username),
    }


def main() -> int:
    report: dict = {}

    # The Factorio executable and its version.
    exe = VANILLA_ROOT / "bin" / "x64" / "factorio.exe"
    report["executable"] = {"path": str(exe), "exists": exe.is_file()}
    if exe.is_file():
        try:
            info = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Item '{exe}').VersionInfo.FileVersion"],
                capture_output=True, text=True, check=False, timeout=60)
            report["executable"]["file_version"] = info.stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            report["executable"]["version_error"] = type(exc).__name__

    # The installed mod in each profile.
    source_files = sorted(p.name for p in MOD_SOURCE.iterdir() if p.is_file())
    report["mod_source_files"] = source_files
    for label, info in PROFILES.items():
        mods = info["mods"]
        entry: dict = {"mods_path": str(mods), "exists": mods.is_dir()}
        if mods.is_dir():
            installed = sorted(p.name for p in mods.iterdir()
                               if p.is_file() and not p.name.endswith(".bak"))
            entry["installed_files"] = installed
            entry["missing"] = [n for n in source_files if n not in installed]
            mismatched = []
            for name in source_files:
                target = mods / name
                if target.is_file() and digest(target) != digest(MOD_SOURCE / name):
                    mismatched.append(name)
            entry["content_mismatch"] = mismatched
        entry["auth"] = auth_state(info["player_data"])
        entry["config_present"] = info["config"].is_file()
        report[label] = entry

    # The disposable saves, with their checksums.
    saves: dict = {}
    for label, directory in SAVE_DIRS.items():
        if not directory.is_dir():
            saves[label] = {"exists": False, "path": str(directory)}
            continue
        listing = []
        for save in sorted(directory.glob("*.zip")):
            listing.append({
                "name": save.name,
                "bytes": save.stat().st_size,
                "sha256": digest(save),
            })
        saves[label] = {"exists": True, "path": str(directory), "saves": listing}
    report["saves"] = saves

    # The mod-list of each profile.
    for label, info in PROFILES.items():
        root = info["root"]
        for candidate in (root / "mod-list.json", root / "config" / "mod-list.json"):
            if candidate.is_file():
                try:
                    entries = json.loads(candidate.read_text(encoding="utf-8"))
                    mods = entries.get("mods", []) if isinstance(entries, dict) else []
                    selected = sorted(
                        str(m.get("name")) for m in mods
                        if isinstance(m, dict) and m.get("enabled"))
                    report.setdefault("mod_lists", {})[label] = {
                        "path": str(candidate),
                        "enabled": selected,
                        "autoengineer_enabled": "autoengineer-input" in selected,
                    }
                except (OSError, ValueError):
                    report.setdefault("mod_lists", {})[label] = {
                        "path": str(candidate), "unreadable": True}
                break

    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("written", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
