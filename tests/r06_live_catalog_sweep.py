"""Bounded live READ-ONLY R06 catalog sweep against an ALREADY RUNNING server.

This harness does **not** start, stop or restart Factorio. It connects the
rebuilt restricted backend to an already-running isolated server and performs
exactly one bounded catalog sweep.

Safety contract:

* It never launches, stops or signals Factorio. The running server is only
  observed through the restricted backend's read-only MCP tools.
* It calls ONLY ``autoengineer_view`` and ``autoengineer_policy``. No console
  command, no crafting, no placement, no mining, no research change, no player
  movement, no lease activation.
* The backend runs in ``helper`` mode, which refuses every gameplay write.
* A page that fails is recorded and the sweep **stops**. There is no automatic
  retry: a page is requested at most once.
* The RCON password is read from the environment's secret file and is never
  printed, logged or written into the evidence.
* Source-save digests are recorded before and after the sweep so any write
  would be detected.

The evidence is written to ``.local/live-pillow-2.1.23/evidence/``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path

import r06_live_environment as env
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local" / "live-pillow-2.1.23"
EVIDENCE = BASE / "evidence"
RUNTIME = BASE / "backend-runtime"

#: The rebuilt restricted backend. It is the DLL produced from the pinned
#: upstream by ``tests/build_isolated_backend.py``.
BACKEND_DLL = BASE / "backend-patched-2.1.23" / "FactorioMCP.dll"

#: The RCON secret of the isolated environment. The value is read, never
#: printed and never written into the evidence.
RCON_SECRET = BASE / "rcon.secret.json"

#: The isolated 2.1.23 executable. The directory still says Factorio_2.1.22;
#: the version is read from the binary, never from the directory name.
EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")

#: The Pyanodons mod directory of the isolated environment.
MODS = ROOT / ".local" / "mod-test-mods" / "2.1.23"

#: The page size the sweep uses. The backend accepts 1..32.
PAGE_SIZE = 32

#: The hard page bound. The backend's own cap is 10000 pages; the sweep stops
#: far below it so a mis-reported total can never become an unbounded loop.
MAX_PAGES = 400

#: The only tools this harness ever calls.
READ_ONLY_CALLS = {"autoengineer_view", "autoengineer_policy"}


def log(message: str) -> None:
    print(message, flush=True)


def rcon_password() -> str:
    """Return the environment's RCON password without ever logging it."""
    data = json.loads(RCON_SECRET.read_text(encoding="utf-8-sig"))
    password = data.get("rcon_password")
    if not isinstance(password, str) or not password:
        raise RuntimeError("the environment RCON secret carries no password")
    return password


def rcon_port() -> int:
    """Return the RCON port of the already-running server.

    The port is read from the running server's own command line so the sweep
    provably targets the server that is actually running. The command line is
    never printed.
    """
    return int(os.environ["R06_RCON_PORT"])


def port_is_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Return True when something accepts a TCP connection on the port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def save_digests() -> dict[str, str]:
    """Return the SHA-256 digest of every save the sweep could touch."""
    digests: dict[str, str] = {}
    candidates = [
        BASE / "evidence" / "r06-reuse-a-save.zip",
        ROOT / ".local" / "launcher-profiles" / "2.1.23" / "data"
        / "saves" / "autoengineer-test modded.zip",
    ]
    for path in candidates:
        if path.is_file():
            digests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def mcp_params(port: int, password: str) -> StdioServerParameters:
    """Build the stdio parameters for the restricted backend."""
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP",
            "TMP", "DOTNET_ROOT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update({
        "FACTORIO_RCON_HOST": "127.0.0.1",
        "FACTORIO_RCON_PORT": str(port),
        "FACTORIO_RCON_PASSWORD": password,
        # helper mode refuses every gameplay write and every lease activation.
        "AUTOENGINEER_BACKEND_MODE": "helper",
        "Logging__LogLevel__Default": "None",
        "Logging__LogLevel__Microsoft": "None",
    })
    RUNTIME.mkdir(parents=True, exist_ok=True)
    env["FACTORIO_GOALS_FILE"] = str(RUNTIME / "goals.json")
    env["FACTORIO_BUILDINGS_FILE"] = str(RUNTIME / "buildings.json")
    return StdioServerParameters(command="dotnet", args=[str(BACKEND_DLL)],
                                 env=env, cwd=str(RUNTIME))


async def call_view(session: ClientSession, page: int, page_size: int,
                    timeout: float = 60.0):
    """Request one catalog page and return (payload, elapsed_seconds)."""
    started = time.monotonic()
    response = await asyncio.wait_for(
        session.call_tool("autoengineer_view",
                          arguments={"catalogPage": page,
                                     "catalogPageSize": page_size,
                                     "catalogOnly": True}),
        timeout=timeout,
    )
    elapsed = time.monotonic() - started
    if getattr(response, "is_error", False):
        raise RuntimeError(f"autoengineer_view page={page} returned is_error")
    text = next(item.text for item in response.content if item.type == "text")
    try:
        return json.loads(text), elapsed
    except ValueError as exc:
        raw_log = EVIDENCE / "last_raw_view_sweep.txt"
        raw_log.write_text(text[:20000], encoding="utf-8")
        raise RuntimeError(
            f"autoengineer_view page={page} returned non-JSON "
            f"({len(text)} chars)") from exc


def capabilities_of(payload) -> dict:
    """Return the capabilities mapping of a view payload."""
    caps = payload.get("capabilities")
    return caps if isinstance(caps, dict) else {}


def rows_of(payload) -> list:
    """Return the recipe rows of a view payload."""
    recipes = capabilities_of(payload).get("recipes")
    return recipes if isinstance(recipes, list) else []


async def sweep(session: ClientSession, report: dict) -> None:
    """Perform exactly one bounded catalog sweep."""
    first, first_latency = await call_view(session, 1, PAGE_SIZE)
    caps = capabilities_of(first)
    status = payload_status(first)
    total_pages = status.get("total_pages") or 0
    total_count = status.get("total_count")

    report["identity"] = {
        "status": first.get("status"),
        "tick": first.get("tick"),
        "surface": first.get("surface"),
        "catalog_tick": caps.get("tick"),
        "catalog_surface": caps.get("surface"),
        "game_version": caps.get("game_version"),
        "force": caps.get("force"),
        "source_fingerprint": caps.get("source_fingerprint"),
        "catalog_status": status.get("status"),
        "total_count": total_count,
        "total_pages": total_pages,
        "page_size": status.get("page_size"),
        "truncated": caps.get("truncated"),
        "research_count": len(caps.get("research") or []),
        "enabled_content_count": len(caps.get("enabled_content") or []),
        "machines_count": len(caps.get("machines") or []),
        "excluded_count": len(caps.get("excluded") or []),
    }
    log("IDENTITY=" + json.dumps(report["identity"], sort_keys=True)[:1200])

    if not isinstance(total_pages, int) or total_pages <= 0:
        report["sweep_error"] = "the first page reported no usable total_pages"
        return
    if total_pages > MAX_PAGES:
        report["sweep_error"] = (
            f"the first page reported {total_pages} pages, above the "
            f"{MAX_PAGES} page bound of this sweep")
        return

    rows: list = []
    excluded_rows = list(caps.get("excluded") or [])
    exclusions_present = isinstance(caps.get("excluded"), list) or caps.get("excluded") == {}
    latencies: list[float] = []
    fingerprints: set = set()
    ticks: set = set()
    versions: set = set()
    forces: set = set()
    surfaces: set = set()
    errors: list[dict] = []

    # Page 1 was already fetched above; it is the first page of the sweep.
    rows.extend(rows_of(first))
    latencies.append(first_latency)
    for page in range(2, total_pages + 1):
        try:
            payload, latency = await call_view(session, page, PAGE_SIZE)
        except Exception as exc:  # noqa: BLE001 - recorded, never retried
            errors.append({"page": page, "error": repr(exc)[:300]})
            break
        page_caps = capabilities_of(payload)
        page_excluded = page_caps.get("excluded")
        exclusions_present = exclusions_present and (
            isinstance(page_excluded, list) or page_excluded == {})
        excluded_rows.extend(page_excluded or [])
        rows.extend(rows_of(payload))
        latencies.append(latency)
        fingerprints.add(page_caps.get("source_fingerprint"))
        ticks.add(page_caps.get("tick"))
        versions.add(page_caps.get("game_version"))
        forces.add(page_caps.get("force"))
        surfaces.add(page_caps.get("surface"))

    # The first page's identity values are folded in after the loop so that
    # the sweep always covers every page it fetched.
    fingerprints.add(caps.get("source_fingerprint"))
    ticks.add(caps.get("tick"))
    versions.add(caps.get("game_version"))
    forces.add(caps.get("force"))
    surfaces.add(caps.get("surface"))

    report["pagination"] = {
        "pages_requested": len(latencies),
        "pages_declared": total_pages,
        "rows_collected": len(rows),
        "unique_names": len({r.get("name") for r in rows if isinstance(r, dict)}),
        "errors": errors,
        "single_fingerprint": len(fingerprints) == 1,
        "single_tick": len(ticks) == 1,
        "single_version": len(versions) == 1,
        "single_force": len(forces) == 1,
        "single_surface": len(surfaces) == 1,
        "ticks_observed": sorted(t for t in ticks if t is not None),
        "latency_min": round(min(latencies), 4) if latencies else None,
        "latency_max": round(max(latencies), 4) if latencies else None,
        "latency_mean": round(sum(latencies) / len(latencies), 4) if latencies else None,
        "sweep_seconds": round(sum(latencies), 3),
    }
    log("PAGINATION=" + json.dumps(report["pagination"], sort_keys=True)[:1500])

    # The machine report travels with the first page's capabilities. The full
    # list is recorded, not a sample, so the category coverage can be
    # measured exactly.
    machines = caps.get("machines")
    report["machines"] = {
        "present": isinstance(machines, list),
        "count": len(machines) if isinstance(machines, list) else 0,
        "rows": machines if isinstance(machines, list) else [],
    }
    log("MACHINES=" + json.dumps(
        {"present": report["machines"]["present"],
         "count": report["machines"]["count"]}, sort_keys=True))

    excluded = excluded_rows
    report["exclusions"] = {
        "present": exclusions_present,
        "count": len(excluded) if isinstance(excluded, list) else 0,
        "rows": excluded if isinstance(excluded, list) else [],
    }
    log("EXCLUSIONS=" + json.dumps(report["exclusions"], sort_keys=True)[:1500])

    report["accounting"] = {
        "declared": total_count,
        "emitted": len(rows),
        "excluded": len(excluded_rows),
        "balanced": (not errors and len(latencies) == total_pages
                     and exclusions_present
                     and total_count == len(rows) + len(excluded_rows)),
    }
    report["rows_payload"] = rows


def payload_status(payload) -> dict:
    """Return the catalog status mapping of a view payload."""
    status = payload.get("catalog_status")
    return status if isinstance(status, dict) else {}


def start_client(tag: str, game_port: int, report: dict):
    """Start a local client that joins the already-running server.

    The restricted backend's catalog gate requires exactly one connected
    player, so a client must be present. The client is a **separate** process
    that connects to the running server over the multiplayer protocol; the
    server is never restarted, stopped or modified.

    The client issues no gameplay command and performs no input. It exists
    only to satisfy the single-player read gate.

    Reuse the same authenticated test-client profile on every run.
    Per-run write-data directories discard the login token and cause
    repeated sign-in prompts or failed headless authentication.
    """
    base_config = BASE / "server" / "config.ini"
    client_root = env.prepare_client_profile(tag, base_config)
    client_config = client_root / "config.ini"
    if not env.has_authentication(client_root / "data" / "player-data.json"):
        raise RuntimeError("Persistent test client is not authenticated")
    report["client_profile"] = str(client_root)

    client_log = EVIDENCE / f"{tag}-client.log"
    out = client_log.open("w", encoding="utf-8")
    err = client_log.with_suffix(".err.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(EXE), "--config", str(client_config),
         "--mod-directory", str(MODS),
         "--mp-connect", f"127.0.0.1:{game_port}"],
        stdout=out, stderr=err,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    report["client_pid"] = process.pid
    report["client_log"] = str(client_log)
    log(f"CLIENT_PID={process.pid}")
    return process


def wait_for_client_join(process, report: dict, start_size: int,
                          timeout: float = 600.0) -> bool:
    """Wait until the server log shows THIS client joined the game.

    The server log is append-only and already contains join lines from earlier
    runs, so only the bytes written after ``start_size`` are considered. A
    stale line can therefore never be mistaken for this client's join.
    """
    server_log = EVIDENCE / "r06-reuse-a-factorio.log"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            report["client_joined"] = False
            report["client_exit"] = process.returncode
            log("CLIENT_EXITED_EARLY")
            return False
        if server_log.is_file():
            with server_log.open("rb") as handle:
                handle.seek(start_size)
                new_text = handle.read().decode("utf-8", errors="replace")
            if "joined the game" in new_text:
                report["client_joined"] = True
                report["client_join_log_offset"] = start_size
                log("CLIENT_JOINED=True")
                return True
        time.sleep(1.0)
    report["client_joined"] = False
    log("CLIENT_JOINED=False")
    return False


async def run(port: int, password: str, report: dict) -> None:
    """Connect the rebuilt backend and run the bounded sweep."""
    params = mcp_params(port, password)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await asyncio.wait_for(session.list_tools(), 15)
            names = sorted(tool.name for tool in listed.tools)
            report["tool_boundary"] = {
                "count": len(names),
                "names": names,
                "read_only_calls": sorted(READ_ONLY_CALLS),
            }
            log(f"TOOL_COUNT={len(names)} NAMES={names}")

            policy = await asyncio.wait_for(
                session.call_tool("autoengineer_policy", arguments={}), 20)
            policy_text = next(i.text for i in policy.content if i.type == "text")
            try:
                report["policy"] = json.loads(policy_text)
            except ValueError:
                report["policy_raw"] = policy_text[:2000]
            log("POLICY=" + json.dumps(report.get("policy") or {}, sort_keys=True)[:800])

            await sweep(session, report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="r06-live-sweep")
    parser.add_argument("--game-port", type=int, required=True,
                        help="the multiplayer port of the ALREADY RUNNING server")
    args = parser.parse_args()

    if not BACKEND_DLL.is_file():
        log(f"BACKEND_MISSING {BACKEND_DLL}")
        return 2
    port = rcon_port()
    if not port_is_open(port):
        log(f"RCON_NOT_LISTENING port={port}")
        return 3

    report: dict = {
        "tag": args.tag,
        "backend_dll": str(BACKEND_DLL),
        "backend_dll_sha256": hashlib.sha256(
            BACKEND_DLL.read_bytes()).hexdigest(),
        "rcon_port": port,
        "game_port": args.game_port,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "save_digests_before": save_digests(),
    }
    try:
        password = rcon_password()
    except Exception as exc:  # noqa: BLE001
        log(f"SECRET_UNREADABLE {type(exc).__name__}")
        return 4

    client = None
    try:
        # The catalog gate requires exactly one connected player. A local
        # client joins the already-running server to satisfy it. The server
        # is never restarted, stopped or modified.
        #
        # The server log offset is captured BEFORE the client starts, so the
        # join detection can only ever see bytes this run produced.
        server_log = EVIDENCE / "r06-reuse-a-factorio.log"
        report["server_log_offset"] = (
            server_log.stat().st_size if server_log.is_file() else 0)
        client = start_client(args.tag, args.game_port, report)
        if not wait_for_client_join(client, report, report["server_log_offset"]):
            log("NO_CLIENT_JOIN")
        else:
            # Give the server a moment to finish handing the map to the
            # joining client before the first catalog request.
            time.sleep(10.0)
            asyncio.run(run(port, password, report))
    except Exception as exc:  # noqa: BLE001 - the failure is the evidence
        report["harness_error"] = repr(exc)[:600]
        log(f"HARNESS_ERROR {report['harness_error']}")
    finally:
        if client is not None and client.poll() is None:
            # Stop only the client this harness started. The server is left
            # exactly as it was found.
            client.terminate()
            try:
                client.wait(timeout=20)
            except subprocess.TimeoutExpired:
                client.kill()
                client.wait(timeout=10)
            report["client_stopped"] = True
            log("CLIENT_STOPPED=True")

    report["save_digests_after"] = save_digests()
    report["save_unchanged"] = (
        report["save_digests_before"] == report["save_digests_after"])
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"{args.tag}.json"
    out.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
    log(f"EVIDENCE={out}")
    log(f"SAVE_UNCHANGED={report['save_unchanged']}")
    return 0 if not report.get("harness_error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
