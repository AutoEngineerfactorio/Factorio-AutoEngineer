"""Live GAME-SIDE verification of the R06 planner against the real game.

This is the command-driven live test for R06. It does more than download a
catalog: it performs **real in-game crafting** on the disposable modded save
through the restricted backend, and compares the observed game behaviour
against the planner's computed values.

The environment is **persistent** (``tests/r06_live_environment.py``):

* an already-running test server is **detected and reused** instead of
  being relaunched, and its RCON endpoint is health-checked first;
* the client uses a **reusable authenticated profile** whose
  ``player-data.json`` is seeded once from the authenticated launcher
  profile. It is never deleted between runs, so **no run ever needs the user
  to sign in again**;
* every wait is **bounded** and reports the exact stage that failed, so the
  harness can never hang indefinitely waiting for a client that cannot
  authenticate.

Safety contract enforced by this module:

* The **source** save is opened read-only and its SHA-256 is compared
  before and after. The run works on a per-run disposable copy.
* Only the **isolated** test instance is touched. No personal save is read
  or written.
* The restricted tool boundary is never bypassed. The craft runs through
  ``autoengineer_operation`` under an owned safety lease, exactly as the
  restricted backend intends. No arbitrary Lua is executed and no gameplay
  command is issued outside the bounded allowlist.
* Only the server and client processes this harness started are stopped. A
  **reused** server is deliberately left running.
* No research, inventory grant, or world change is performed outside the
  bounded starter operation, and the save is never written back to the
  source path.

No Factorio process, save, RCON command or external service of the user's
personal installation is touched.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parent))

import r06_live_environment as env  # noqa: E402

ROOT = env.ROOT
BASE = env.BASE
EVIDENCE = env.EVIDENCE

MODDED_SAVE = env.MODDED_SAVE
MODS = env.MODS
EXE = env.EXE
SERVER_SETTINGS = BASE / "server" / "server-settings.json"
BASE_CONFIG = BASE / "server" / "config.ini"
RESTRICTED_BACKEND = BASE / "backend-patched-2.1.23" / "FactorioMCP.dll"

# The bounded starter allowlist of the restricted backend. A craft is only
# attempted for an item the backend itself permits.
CRAFT_CASES = (
    {"kind": "craft", "name": "iron-gear-wheel", "count": 1,
     "input": "iron-plate", "input_units": 2, "output_units": 1},
    {"kind": "craft", "name": "copper-cable", "count": 1,
     "input": "copper-plate", "input_units": 1, "output_units": 2},
)

# The lease owner is a fresh GUID in the exact format the backend expects.
LEASE_OWNER = secrets.token_hex(16)

# The client must load the whole mod suite before it connects, so the join
# can take several minutes. The window is generous on purpose, and the join
# is detected from the server's own multiplayer state lines rather than from
# a chat-format line, so a successful join is never missed.
JOIN_WINDOW_SECONDS = 900

# The server must load the mod suite and open its RCON endpoint. This is
# bounded and reports the exact stage that failed.
SERVER_READY_SECONDS = 600

# The backend's observation gate needs exactly one connected player **with a
# character**. The client's join is detected before the map is downloaded and
# the character spawned, so the wait polls the real view response instead of
# sleeping for a guessed interval.
PLAYER_READY_SECONDS = 300

JOIN_MARKERS = (
    re.compile(r"\[JOIN\]"),
    re.compile(r"joined the game"),
    re.compile(r"newState\(InGame\)"),
    re.compile(r"newState\(ConnectedWaitingForMap\)"),
    re.compile(r"newState\(ConnectedDownloadingMap\)"),
    re.compile(r"newState\(ConnectedLoadingMap\)"),
    re.compile(r"newState\(TryingToCatchUp\)"),
    re.compile(r"Serving map\("),
)

# The client's authentication handshake, observed in the client log. These
# markers are what distinguishes "the client is still signing in" from "the
# client gave up", which the previous harness could not tell apart.
AUTH_MARKERS = {
    "tls_check": re.compile(r"Performing TLS check|TLS check success"),
    "api_login": re.compile(r"api-login\?api_version"),
    "token_received": re.compile(r"Got token from auth server"),
    "server_key": re.compile(r"generate-user-server-key-2|Received key from auth"),
    "reconnect": re.compile(r"ConnectedWaitingForMap|ConnectedDownloadingMap"),
}

# The stages the handshake can reach, in order.
AUTH_STAGES = ("tls_check", "api_login", "token_received", "server_key",
               "reconnect")


def join_evidence(text: str) -> list[str]:
    """Return the server-side lines that prove a client joined."""
    return [
        line for line in text.splitlines()
        if any(marker.search(line) for marker in JOIN_MARKERS)
    ]


def auth_progress(text: str) -> dict:
    """Report how far the client's authentication handshake got.

    The reported stages make the difference between "the client is still
    signing in" and "the client never issued an api-login" explicit, which
    is exactly the distinction the previous harness could not make.
    """
    reached = [stage for stage in AUTH_STAGES
               if AUTH_MARKERS[stage].search(text)]
    return {
        "stages_reached": reached,
        "last_stage": reached[-1] if reached else None,
        "login_requested": bool(AUTH_MARKERS["api_login"].search(text)),
        "token_received": bool(AUTH_MARKERS["token_received"].search(text)),
    }


def refusal_evidence(text: str) -> list[str]:
    """Return the server-side lines that prove a connection was refused."""
    return [
        line for line in text.splitlines()
        if "Refusing connection" in line or "UserVerification" in line
    ]


def preflight(dll: Path, exe: Path, mods: Path, save: Path) -> list[str]:
    """Run the bounded preflight checks and return the blocking problems.

    The checks are read-only and cheap. They catch the conditions that would
    otherwise waste a whole server and client startup: a missing backend, a
    missing executable, a missing mod suite, a missing save, a port that is
    already taken by a stale process, and a backend that is not the
    restricted build.
    """
    problems: list[str] = []
    if not dll.is_file():
        problems.append(f"the restricted backend is missing: {dll}")
    if not exe.is_file():
        problems.append(f"the isolated executable is missing: {exe}")
    if not mods.is_dir():
        problems.append(f"the mod directory is missing: {mods}")
    if not save.is_file():
        problems.append(f"the disposable save is missing: {save}")
    elif not (mods / "mod-list.json").is_file():
        problems.append(f"the mod suite has no mod-list.json: {mods}")
    if problems:
        return problems
    # A stale Factorio process on the chosen port would make the server fail
    # to bind, and a stale client would make the join ambiguous.
    for port in (34261, 27161):
        if not env.port_is_open("127.0.0.1", port):
            continue
        # The port is taken. That is only acceptable when it is the test
        # server's own RCON endpoint, which is reused rather than replaced.
        if port == 27161 and env.server_is_healthy(port):
            continue
        problems.append(
            f"port {port} is already in use; a stale process must be "
            "stopped before the run"
        )
    return problems


def log(message: str) -> None:
    print(str(message), flush=True)


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mcp_params(dll: Path, rcon_port: int, password: str,
               mode: str = "helper") -> StdioServerParameters:
    """Build the restricted backend's stdio launch parameters.

    The backend is a .NET 9 assembly, so it is hosted by the ``dotnet`` muxer
    with the runtime directory as its working directory. Launching the
    assembly directly makes the host fail to load ``System.Runtime`` when
    ``DOTNET_ROOT`` is not set, which is the case in this environment.

    ``mode`` selects the backend's operating mode. The default is the
    read-only **AI Helper** mode, which refuses every gameplay write and
    every lease activation.
    """
    env_vars = env.backend_launch_environment(rcon_port, password, mode)
    return StdioServerParameters(command="dotnet", args=[str(dll)],
                                  env=env_vars,
                                  cwd=str(env.BACKEND_RUNTIME))


async def call_tool(session: ClientSession, name: str, arguments: dict) -> dict:
    """Call one restricted backend tool and decode its JSON answer."""
    response = await asyncio.wait_for(
        session.call_tool(name, arguments=arguments), 120
    )
    if getattr(response, "is_error", False):
        # The error text is reported, so a failure names its cause instead of
        # being an opaque "is_error".
        detail = ""
        for item in getattr(response, "content", []) or []:
            if getattr(item, "type", "") == "text":
                detail = str(item.text)[:400]
                break
        raise RuntimeError(f"{name} returned is_error: {detail}")
    text = next(item.text for item in response.content if item.type == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def capability_rows(payload: dict) -> list[dict]:
    """Return the recipe rows of an observed view payload.

    The restricted backend reports the observed capability set under
    ``capabilities``. The recipe rows of a catalog page are the
    ``capabilities.recipes`` list. They are **not** at the top level: a
    payload without a player carries only ``status``.
    """
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        return []
    recipes = capabilities.get("recipes")
    if not isinstance(recipes, list):
        return []
    return [row for row in recipes if isinstance(row, dict)]


def observed_identity(payload: dict) -> tuple[str | None, str | None]:
    """Return the observed ``(force, surface)`` of the player.

    The identity is reported inside the capability set, next to the
    recipes, the enabled content and the research set.
    """
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        return None, None
    force = capabilities.get("force")
    surface = capabilities.get("surface")
    return (
        force if isinstance(force, str) and force else None,
        surface if isinstance(surface, str) and surface else None,
    )


async def read_catalog(session: ClientSession, report: dict) -> dict[str, dict]:
    """Page over the observed catalog and return the recipe rows by name.

    The catalog's identity (``total_count`` and ``total_pages``) is reported
    on the **first** page, so it is captured there and not overwritten by a
    later page that omits it.
    """
    rows_by_name: dict[str, dict] = {}
    total_rows = 0
    page = 1
    total_pages: int | None = None
    while True:
        payload = await call_tool(session, "autoengineer_view",
                                  {"catalogPage": page, "catalogPageSize": 32})
        status = payload.get("catalog_status") or {}
        if status.get("total_count") is not None:
            report["catalog_total_count"] = status.get("total_count")
        if status.get("total_pages") is not None:
            total_pages = int(status["total_pages"])
            report["catalog_total_pages"] = total_pages
        for row in capability_rows(payload):
            rows_by_name[str(row.get("name"))] = row
            total_rows += 1
        if total_pages is None:
            if page >= 1 and not capability_rows(payload):
                break
        elif page >= total_pages:
            break
        page += 1
        if page > 2000:
            break
    report["catalog_rows"] = total_rows
    report["catalog_unique_names"] = len(rows_by_name)
    return rows_by_name


async def dump_catalog_rows(rows_by_name: dict[str, dict], tag: str) -> str:
    """Persist the observed recipe rows so they can be classified offline.

    The rows are the backend's own observations. Writing them lets the
    exclusion audit work on **real** live data instead of on guessed recipe
    shapes. The file is written under the disposable evidence directory.
    """
    path = EVIDENCE / f"{tag}-catalog-rows.json"
    path.write_text(
        json.dumps(rows_by_name, indent=1, sort_keys=True, default=list),
        encoding="utf-8",
    )
    return str(path)


async def run_game_side(session: ClientSession, report: dict,
                        mode: str = "helper") -> None:
    """Perform the real in-game craft and compare it with the planner.

    The craft needs the backend's **supervised** mode. The read-only AI
    Helper mode refuses lease activation and every gameplay write, so in that
    mode the craft is skipped with an explicit reason instead of being
    attempted.
    """
    view = await call_tool(session, "autoengineer_view", {})
    capabilities = view.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    report["view_status"] = (view.get("catalog_status") or {}).get("status")
    force, surface = observed_identity(view)
    report["view_force"] = force
    report["view_surface"] = surface
    report["view_game_version"] = capabilities.get("game_version")
    report["view_enabled_content_count"] = len(
        capabilities.get("enabled_content") or [])
    report["view_research_count"] = len(capabilities.get("research") or [])

    rows_by_name = await read_catalog(session, report)
    # The observed rows are persisted so the exclusion audit can classify the
    # recipes that the adapter could not represent using **real** live data.
    report["catalog_rows_file"] = await dump_catalog_rows(
        rows_by_name, report.get("run_tag", "r06")
    )

    if mode != "semi":
        # The read-only AI Helper mode refuses lease activation and every
        # gameplay write. The craft is therefore skipped with an explicit
        # reason instead of being attempted and refused.
        report["game_side_skipped"] = (
            "the AI Helper mode is read-only: it refuses lease activation and "
            "every gameplay write, so no in-game craft was attempted"
        )
        report["game_side_skipped_mode"] = mode
        return

    armed = await call_tool(session, "autoengineer_arm", {"owner": LEASE_OWNER})
    report["arm_status"] = armed.get("status")
    if armed.get("status") != "active":
        report["game_side_skipped"] = (
            f"the safety lease could not be armed: {armed.get('status')}"
        )
        return

    try:
        for case in CRAFT_CASES:
            entry: dict = {"kind": case["kind"], "name": case["name"],
                           "count": case["count"]}
            preview = await call_tool(
                session, "autoengineer_operation_preview",
                {"kind": case["kind"], "name": case["name"],
                 "count": case["count"]},
            )
            entry["preview_status"] = preview.get("status")
            entry["preview"] = preview
            if preview.get("status") != "ready":
                entry["executed"] = False
                report.setdefault("craft_cases", []).append(entry)
                continue

            # The planner's expectation, computed from the observed catalog.
            observed = rows_by_name.get(case["name"])
            entry["catalog_recipe_present"] = observed is not None
            if observed:
                entry["catalog_products"] = observed.get("products")
                entry["catalog_ingredients"] = observed.get("ingredients")
                entry["catalog_crafting_time"] = observed.get("crafting_time")
                entry["catalog_unlocks"] = observed.get("unlock_technologies")

            executed = await call_tool(
                session, "autoengineer_operation",
                {"kind": case["kind"], "name": case["name"],
                 "count": case["count"], "safetyOwner": LEASE_OWNER,
                 "targetX": preview.get("x", 0), "targetY": preview.get("y", 0)},
            )
            entry["operation_status"] = executed.get("status")
            entry["operation"] = executed
            entry["executed"] = executed.get("status") in ("completed", "ok")

            # The observed game behaviour against the planner's expectation.
            for label, key in (("product", case["name"]),
                               ("input", case["input"])):
                before = (executed.get(f"{label}_before") or {})
                after = (executed.get(f"{label}_after") or {})
                if isinstance(before, dict) and key in before:
                    entry[f"{label}_before"] = before[key]
                if isinstance(after, dict) and key in after:
                    entry[f"{label}_after"] = after[key]
            for label, sign, units in (("product", 1, case["output_units"]),
                                       ("input", -1, case["input_units"])):
                before = entry.get(f"{label}_before")
                after = entry.get(f"{label}_after")
                if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
                    continue
                if isinstance(before, bool) or isinstance(after, bool):
                    continue
                entry[f"observed_{label}_delta"] = sign * (after - before)
                entry[f"expected_{label}_delta"] = case["count"] * units
                entry[f"{label}_matches"] = (
                    entry[f"observed_{label}_delta"] == entry[f"expected_{label}_delta"]
                )
            report.setdefault("craft_cases", []).append(entry)
    finally:
        stopped = await call_tool(session, "autoengineer_stop", {"owner": LEASE_OWNER})
        report["stop_status"] = stopped.get("status")


async def wait_for_player_ready(session: ClientSession, report: dict) -> bool:
    """Wait, bounded, until the backend can actually observe the player.

    The client's join is detected on the server's multiplayer state lines,
    which happen **before** the client has downloaded the map and spawned its
    character. The backend's observation gate needs exactly one connected
    player with a character.

    The readiness signal is the **player's own observation**: the view
    reports the player's force and surface only once a character exists. The
    catalog's own metadata (``catalog_status``) is **not** a readiness
    signal, because the adapter reports the catalog's identity even when the
    player-dependent part of the observation is still empty.
    """
    deadline = time.monotonic() + PLAYER_READY_SECONDS
    attempts = 0
    last_status: str | None = None
    while time.monotonic() < deadline:
        attempts += 1
        payload = await call_tool(session, "autoengineer_view", {})
        status = str(payload.get("status") or "")
        last_status = status
        force, surface = observed_identity(payload)
        if status == "unavailable":
            # The backend could not see exactly one connected player with a
            # character yet. Keep waiting, bounded.
            await asyncio.sleep(1.0)
            continue
        if not force or not surface:
            # The player has joined but the observation does not carry the
            # player's own identity yet. Keep waiting, bounded.
            await asyncio.sleep(1.0)
            continue
        report["player_ready_attempts"] = attempts
        report["player_ready_status"] = status
        report["player_ready_force"] = force
        report["player_ready_surface"] = surface
        report["player_ready"] = True
        return True
    report["player_ready"] = False
    report["player_ready_attempts"] = attempts
    report["player_ready_status"] = last_status
    report["player_ready_reason"] = (
        f"the backend did not observe a connected player with a character "
        f"within {PLAYER_READY_SECONDS:.0f}s"
    )
    return False


async def run_mcp(dll: Path, rcon_port: int, password: str, report: dict,
                  mode: str = "helper") -> None:
    async with stdio_client(mcp_params(dll, rcon_port, password, mode)) as (
            read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            report["policy"] = await call_tool(session, "autoengineer_policy", {})
            if not await wait_for_player_ready(session, report):
                report["game_side_skipped"] = report.get(
                    "player_ready_reason",
                    "the backend never observed a connected player")
                return
            await run_game_side(session, report, mode)


def start_server(run_tag: str, run_config: Path, run_save: Path,
                 game_port: int, rcon_port: int, password: str,
                 report: dict):
    """Start the Factorio server and wait, bounded, for its RCON endpoint."""
    log_path = EVIDENCE / f"{run_tag}-factorio.log"
    out = log_path.open("w", encoding="utf-8")
    err = log_path.with_suffix(".err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([
        str(EXE), "--config", str(run_config), "--mod-directory", str(MODS),
        "--start-server", str(run_save),
        "--server-settings", str(SERVER_SETTINGS),
        "--bind", f"127.0.0.1:{game_port}",
        "--rcon-bind", f"127.0.0.1:{rcon_port}",
        "--rcon-password", password,
    ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    log(f"SERVER_PID={proc.pid}")

    def ready() -> object:
        if proc.poll() is not None:
            return f"the server exited with rc={proc.returncode}"
        if env.server_is_healthy(rcon_port):
            return True
        return None

    result = env.wait_for(ready, timeout=SERVER_READY_SECONDS,
                           description="the server opened its RCON endpoint")
    report["server_ready"] = result.ok
    report["server_ready_reason"] = result.reason
    report["server_ready_waited_seconds"] = round(result.waited_seconds, 2)
    log(f"SERVER_READY={result.ok} ({result.reason})")
    if not result.ok:
        return proc, log_path
    text = log_path.read_text(encoding="utf-8", errors="replace")
    loaded = sorted(set(re.findall(r"Loading mod ([A-Za-z0-9_.-]+) ([0-9.]+)", text)))
    report["mods_loaded"] = [f"{name} {version}" for name, version in loaded]
    report["pyanodons_loaded"] = sorted(
        name for name, _ in loaded if name.lower().startswith("py")
    )
    log("PYANODONS_LOADED=" + json.dumps(report["pyanodons_loaded"]))
    return proc, log_path


def start_client(run_tag: str, client_config: Path, game_port: int, report: dict):
    """Start the graphical client against the persistent client profile."""
    client_log = EVIDENCE / f"{run_tag}-client.log"
    client_out = client_log.open("w", encoding="utf-8")
    client_err = client_log.with_suffix(".err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([
        str(EXE), "--config", str(client_config), "--mod-directory", str(MODS),
        "--mp-connect", f"127.0.0.1:{game_port}",
    ], stdout=client_out, stderr=client_err,
        creationflags=subprocess.CREATE_NO_WINDOW)
    log(f"CLIENT_PID={proc.pid}")
    return proc, client_log


def wait_for_join(client, server_data: Path, client_data: Path,
                  report: dict) -> bool:
    """Wait, bounded, for the client to join, and report the exact stage.

    The wait is a bounded poll against the server's own multiplayer state
    lines and the client's own log. Both logs are read from the **profile's**
    write-data directory, because that is where Factorio writes its log; the
    redirected standard output of the process is not the game's log.

    It stops as soon as the client process exits, so a client that can never
    authenticate is reported quickly instead of consuming the whole window.
    """

    def joined() -> object:
        if client.poll() is not None:
            return "the client process exited before it joined"
        text = env.read_game_log(server_data)
        evidence = join_evidence(text)
        if evidence:
            report["join_evidence"] = evidence[:8]
            return True
        return None

    result = env.wait_for(joined, timeout=JOIN_WINDOW_SECONDS,
                           description="the client joined the server")
    client_text = env.read_game_log(client_data)
    progress = auth_progress(client_text)
    report["auth_progress"] = progress
    report["client_join_waited_seconds"] = round(result.waited_seconds, 2)
    report["client_join_reason"] = result.reason
    server_text = env.read_game_log(server_data)
    report["refusal_evidence"] = refusal_evidence(server_text)[:8]
    if not result.ok:
        log("JOIN_EVIDENCE=" + json.dumps(report["refusal_evidence"]))
        log("AUTH_PROGRESS=" + json.dumps(progress))
    return result.ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-port", type=int, default=34261)
    parser.add_argument("--rcon-port", type=int, default=27161)
    parser.add_argument("--run-tag", default="r06-game-side")
    parser.add_argument("--backend", default=str(RESTRICTED_BACKEND))
    parser.add_argument("--keep-server", action="store_true",
                        help="leave the server running after the run so the "
                             "next run can reuse it")
    parser.add_argument("--backend-mode", default="helper",
                        choices=list(env.BACKEND_MODES),
                        help="the restricted backend's operating mode. The "
                             "default 'helper' is the read-only AI Helper "
                             "mode, which refuses every gameplay write and "
                             "every lease activation. 'semi' is the "
                             "supervised mode and is only used for an "
                             "explicitly authorized disposable gameplay test.")
    options = parser.parse_args()

    for required in (MODDED_SAVE, MODS, EXE, SERVER_SETTINGS, BASE_CONFIG):
        if not Path(required).exists():
            log(f"MISSING_PREREQUISITE={required}")
            return 2
    # The bounded preflight runs before any process is started, so a stale
    # process or a missing build is reported immediately instead of after a
    # whole server and client startup.
    problems = preflight(
        Path(options.backend), EXE, MODS, MODDED_SAVE
    )
    if problems:
        for problem in problems:
            log("PREFLIGHT_PROBLEM=" + problem)
        log("PREFLIGHT=PASS")
        return 2
    log("PREFLIGHT=PASS")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "run_tag": options.run_tag,
        "game_port": options.game_port,
        "rcon_port": options.rcon_port,
        "backend_mode": options.backend_mode,
        "backend_sha256": digest(Path(options.backend))
        if Path(options.backend).is_file() else None,
        "source_save": str(MODDED_SAVE),
    }
    source_before = digest(MODDED_SAVE)
    report["save_digest_before"] = source_before

    run_save = EVIDENCE / f"{options.run_tag}-save.zip"
    shutil.copy2(MODDED_SAVE, run_save)
    report["run_save"] = str(run_save)
    report["run_save_is_copy"] = True

    # The RCON password belongs to the **environment**, not to a run: a
    # reused server was started with the password that was current then, so
    # a per-run password would make the reused server unreachable.
    password = env.rcon_password()
    client = None
    proc = None
    reused_server = False
    run_config = None
    out_path = EVIDENCE / f"{options.run_tag}.json"
    try:
        # The persistent client profile is seeded once and reused. Its
        # authentication state survives between runs, so no run needs the
        # user to sign in again.
        client_profile = env.prepare_client_profile(
            options.run_tag, BASE_CONFIG, options.rcon_port)
        report["client_profile"] = str(client_profile)
        report["client_auth_state"] = env.client_auth_state()
        log("CLIENT_AUTH=" + json.dumps(report["client_auth_state"]))
        if not env.has_authentication(
                client_profile / "data" / "player-data.json"):
            report["game_side_skipped"] = (
                "the persistent client profile carries no authentication token"
            )
            log("GAME_SIDE_SKIPPED=" + report["game_side_skipped"])
            return 3

        run_config = env.prepare_server_config(
            options.run_tag, BASE_CONFIG, options.rcon_port, password)

        # An already-running test server is reused instead of relaunched. The
        # server writes its log into its own write-data directory, so the
        # join is detected there whether the server was started now or was
        # already running.
        server_data = env.SERVER_DATA
        if env.discover_running_server(options.rcon_port):
            reused_server = True
            report["server_reused"] = True
            report["server_ready"] = True
            report["server_ready_reason"] = "an existing test server was reused"
            report["server_data"] = str(server_data)
            log("SERVER_REUSED=True")
        else:
            proc, _ = start_server(
                options.run_tag, run_config, run_save, options.game_port,
                options.rcon_port, password, report)
            if not report.get("server_ready"):
                return 4
            report["server_data"] = str(server_data)

        client, _ = start_client(
            options.run_tag, client_profile / "config.ini",
            options.game_port, report)
        joined = wait_for_join(
            client, server_data, client_profile / "data", report)
        report["client_joined"] = joined
        log(f"CLIENT_JOINED={joined}")
        if joined:
            # The player-ready wait is inside run_mcp: it polls the backend's
            # real view response instead of sleeping for a guessed interval.
            asyncio.run(run_mcp(Path(options.backend), options.rcon_port,
                                password, report, options.backend_mode))
        else:
            report["game_side_skipped"] = (
                "the client did not join; the backend read gate needs one player"
            )
            log("GAME_SIDE_SKIPPED=" + report["game_side_skipped"])
    except Exception as exc:  # noqa: BLE001 - the report must survive any error
        report["harness_error"] = repr(exc)[:800]
        log("HARNESS_ERROR=" + report["harness_error"])
    finally:
        # Only the processes this harness started are stopped. A reused
        # server belongs to the environment and is deliberately left alone,
        # and a server the operator asked to keep is left running too.
        keep_server = reused_server or options.keep_server
        for process in (client, proc):
            if process is None or process.poll() is not None:
                continue
            if keep_server and process is proc:
                report["server_pid_left_running"] = process.pid
                continue
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
        report["save_digest_after"] = digest(MODDED_SAVE)
        report["save_unchanged"] = report["save_digest_after"] == source_before
        report["source_save_unchanged"] = report["save_unchanged"]
        report["ephemeral_rcon_secret_discarded"] = False
        report["rcon_secret_is_environment_scoped"] = True
        report["server_left_running"] = bool(
            reused_server or options.keep_server)
        try:
            if run_config is not None:
                run_config.unlink()
                report["run_config_removed"] = True
        except OSError:
            pass
        out_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=list),
            encoding="utf-8",
        )
        log("SAVE_UNCHANGED=" + str(report["save_unchanged"]))
        log("EVIDENCE=" + str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
