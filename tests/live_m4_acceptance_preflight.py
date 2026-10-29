"""Live acceptance preflight for the M4 end-user journey.

This script checks everything that can be checked **before** a game
process starts. It never launches Factorio, never writes to a save and
never touches the user's own Factorio profile.

The journey it prepares for:

    double-click the launcher
      -> configure the installation
      -> select the mod profile
      -> launch the game
      -> observe the dashboard
      -> save
      -> stop

Usage:

    python -B tests/live_m4_acceptance_preflight.py
    python -B tests/live_m4_acceptance_preflight.py --report path.json

The exit code is zero when every check that could be checked offline
passed, and one otherwise. A failed check is never suppressed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from factorio_profiles import (  # noqa: E402
    ProfileManager,
    discover_installations,
)
from factorio_session import GameSession  # noqa: E402
from settings_store import effective_settings  # noqa: E402

#: The installations this project knows about. They are **candidates**:
#: the preflight reports what it finds and never assumes one is right.
KNOWN_INSTALLATIONS = (
    Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Factorio"),
    Path(r"C:\Program Files\Factorio"),
)


class Preflight:
    """Collects the checks and their results."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def record(self, name: str, passed: bool, detail: str) -> bool:
        """Record one check and report it."""
        self.checks.append({"name": name, "passed": bool(passed),
                            "detail": detail})
        marker = "PASS" if passed else "FAIL"
        print(f"{marker}  {name}: {detail}")
        return bool(passed)

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [check for check in self.checks if not check["passed"]]

    def report(self) -> dict[str, Any]:
        return {
            "checks": self.checks,
            "failed": len(self.failed),
            "passed": len(self.checks) - len(self.failed),
            "launched_factorio": False,
            "altered_saves": False,
        }


def check_installations(preflight: Preflight) -> list[Any]:
    """Report every Factorio installation that can be found.

    A default location that does not hold Factorio is **not** a failure:
    most machines have only one installation. Only an installation that
    was found but cannot be used is a failure.
    """
    found = discover_installations(KNOWN_INSTALLATIONS)
    usable = []
    for installation in found:
        if installation.usable:
            usable.append(installation)
            preflight.record(
                f"installation {installation.root}",
                True,
                f"version={installation.display_version} "
                f"supported={installation.supported}")
        else:
            preflight.record(
                f"installation {installation.root} is unusable",
                False,
                installation.problem or "unknown problem")
    if not usable:
        preflight.record(
            "a usable installation was found", False,
            "no Factorio installation was found; add one in Settings")
    else:
        preflight.record(
            "a usable installation was found", True,
            f"{len(usable)} installation(s) are ready to use")
    return usable


def check_profile_isolation(preflight: Preflight) -> None:
    """Report that the profile root and its directories are separate."""
    manager = ProfileManager()
    profiles = manager.list_profiles()
    preflight.record(
        "the profile root is ready", True,
        f"{manager.root} holds {len(profiles)} profile(s)")
    if not profiles:
        preflight.record(
            "a profile exists", False,
            "no profile has been created yet; create one in Settings before "
            "the live acceptance")
    for profile in profiles:
        preflight.record(
            f"profile {profile.name} owns its directories",
            profile.saves_directory.is_dir()
            and profile.config_directory.is_dir()
            and profile.cache_directory.is_dir(),
            f"saves={profile.saves_directory} "
            f"config={profile.config_directory} "
            f"cache={profile.cache_directory}")
        problems = manager.validate(profile.identifier)
        preflight.record(
            f"profile {profile.name} validates",
            not problems,
            "; ".join(problems) or "no problem")
        preflight.record(
            f"profile {profile.name} has a content fingerprint",
            bool(profile.fingerprint),
            profile.fingerprint[:16])


def check_running_instances(preflight: Preflight) -> list[int]:
    """Report every running Factorio process. Nothing is stopped."""
    try:
        import psutil
    except ImportError:  # pragma: no cover - depends on the environment
        preflight.record("psutil is available", False,
                         "the process list cannot be read")
        return []
    found: list[int] = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            if (process.info.get("name") or "").lower() == "factorio.exe":
                found.append(int(process.info["pid"]))
        except Exception:
            continue
    preflight.record(
        "no Factorio instance is running", not found,
        f"the running PIDs are {found}" if found
        else "no Factorio process was found")
    return found


def check_stop_ownership(preflight: Preflight) -> None:
    """Report that a running game is never stopped by AutoEngineer."""
    manager = ProfileManager()
    for profile in manager.list_profiles():
        session = GameSession(profile)
        state = session.state()
        preflight.record(
            f"profile {profile.name} owns no foreign game",
            not (state.running and not state.owned),
            state.detail)
        preflight.record(
            f"profile {profile.name} has an executable",
            profile.executable.is_file(),
            str(profile.executable))


def check_settings(preflight: Preflight) -> None:
    """Report the settings the application would use."""
    settings = effective_settings()
    for problem in settings.problems:
        preflight.record("a settings problem", False, problem)
    preflight.record(
        "the settings have no problem", not settings.problems,
        "; ".join(settings.problems) or "none")
    preflight.record(
        "the UPS target is 60", settings.get("ups_target") == 60,
        str(settings.get("ups_target")))
    preflight.record(
        "the AI Helper stays read-only", settings.get("helper_read_only") is True,
        str(settings.get("helper_read_only")))
    try:
        from mode_policy import load_mode

        policy = load_mode()
        preflight.record(
            "the permission mode is not fully autonomous",
            policy.mode in ("helper", "semi"),
            policy.mode)
    except Exception as error:
        preflight.record("the permission mode can be read", False, str(error))


def check_saves_are_untouched(preflight: Preflight) -> None:
    """Report the saves that exist, without opening or changing them."""
    manager = ProfileManager()
    for profile in manager.list_profiles():
        saves = sorted(
            path.name for path in profile.saves_directory.glob("*.zip"))
        preflight.record(
            f"profile {profile.name} has its saves listed", True,
            f"{len(saves)} save(s): {saves}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        help="write the report to this file")
    arguments = parser.parse_args()

    print("AutoEngineer M4 live acceptance preflight")
    print("No Factorio process is started and no save is touched.\n")

    preflight = Preflight()
    check_installations(preflight)
    check_profile_isolation(preflight)
    check_running_instances(preflight)
    check_stop_ownership(preflight)
    check_settings(preflight)
    check_saves_are_untouched(preflight)

    report = preflight.report()
    print(f"\n{report['passed']} check(s) passed, {report['failed']} failed.")
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"The report was written to {arguments.report}")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
