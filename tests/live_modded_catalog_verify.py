"""Live READ-ONLY Factorio 2.1.23 MODDED (Pyanodons) catalog verification.

Safety contract enforced by this module:
  * Starts ONLY a headless server on 127.0.0.1 using a per-run config that
    carries an ephemeral random RCON password. The password is discarded at
    exit and the launcher profile config is never modified.
  * Copies the modded save to a per-run evidence file; the source save is
    opened read-only and its SHA-256 is compared before and after.
  * Calls ONLY the read-only MCP tools autoengineer_policy and
    autoengineer_view. It never calls walk_to_position, autoengineer_operation,
    autoengineer_arm or autoengineer_renew.
  * Never issues a gameplay command, never changes research, never grants
    items and never writes to the save.
  * Stops only the server process this harness started.

Evidence is written to .local/live-pillow-2.1.23/evidence/ as JSON.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import r06_live_environment as env
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
BASE = ROOT / ".local" / "live-pillow-2.1.23"
EVIDENCE = BASE / "evidence"

# The modded profile under test: the disposable modded save in the 2.1.23
# launcher profile, the Pyanodons mod directory and the isolated executable.
MODDED_SAVE = ROOT / ".local" / "launcher-profiles" / "2.1.23" / "data" / "saves" / "autoengineer-test modded.zip"
MODS = ROOT / ".local" / "mod-test-mods" / "2.1.23"
EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")
SERVER_SETTINGS = BASE / "server" / "server-settings.json"
BASE_CONFIG = BASE / "server" / "config.ini"
RESTRICTED_BACKEND = BASE / "backend-patched-2.1.23" / "FactorioMCP.dll"

# The restricted policy-v8 boundary: exactly thirteen registered tools.
EXPECTED_TOOLS = {
    "autoengineer_operation_preview",
    "autoengineer_operation",
    "autoengineer_view",
    "autoengineer_telemetry",
    "autoengineer_policy",
    "get_player_position",
    "scan_resources",
    "get_nearby_entities",
    "walk_to_position",
    "autoengineer_status",
    "autoengineer_arm",
    "autoengineer_renew",
    "autoengineer_stop",
}
READ_ONLY_CALLS = {"autoengineer_view", "autoengineer_policy"}


def log(msg):
    print(str(msg), flush=True)


def port_is_free(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return False
    except OSError:
        return True


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows_of(payload):
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        return []
    recipes = capabilities.get("recipes")
    return recipes if isinstance(recipes, list) else []


def mcp_params(dll, rcon_port, password):
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "DOTNET_ROOT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update({
        "FACTORIO_RCON_HOST": "127.0.0.1",
        "FACTORIO_RCON_PORT": str(rcon_port),
        "FACTORIO_RCON_PASSWORD": password,
        "AUTOENGINEER_BACKEND_MODE": "helper",
        "Logging__LogLevel__Default": "None",
        "Logging__LogLevel__Microsoft": "None",
    })
    runtime = BASE / "backend-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    env["FACTORIO_GOALS_FILE"] = str(runtime / "goals.json")
    env["FACTORIO_BUILDINGS_FILE"] = str(runtime / "buildings.json")
    return StdioServerParameters(command="dotnet", args=[str(dll)], env=env, cwd=str(runtime))


async def call_view(session, page=1, page_size=16, timeout=90):
    started = time.monotonic()
    response = await asyncio.wait_for(
        session.call_tool(
            "autoengineer_view",
            arguments={"catalogPage": page, "catalogPageSize": page_size},
        ),
        timeout=timeout,
    )
    elapsed = time.monotonic() - started
    if getattr(response, "is_error", False):
        raise RuntimeError(f"autoengineer_view page={page} returned is_error")
    text = next(item.text for item in response.content if item.type == "text")
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raw_log = EVIDENCE / "last_raw_view_modded.txt"
        raw_log.write_text(text[:20000], encoding="utf-8")
        raise RuntimeError(
            f"autoengineer_view page={page} returned non-JSON "
            f"({len(text)} chars): {text[:300]!r}"
        ) from exc
    return parsed, elapsed, len(text)


async def probe(session, report):
    listed = await asyncio.wait_for(session.list_tools(), 15)
    names = sorted(t.name for t in listed.tools)
    report["tool_boundary"] = {
        "count": len(names),
        "names": names,
        "exactly_13": set(names) == EXPECTED_TOOLS,
        "unexpected": sorted(set(names) - EXPECTED_TOOLS),
        "missing": sorted(EXPECTED_TOOLS - set(names)),
    }
    log(f"TOOL_COUNT={len(names)} EXACT_12={report['tool_boundary']['exactly_12']}")

    policy_resp = await asyncio.wait_for(
        session.call_tool("autoengineer_policy", arguments={}), 15
    )
    report["policy"] = json.loads(
        next(i.text for i in policy_resp.content if i.type == "text")
    )
    log("POLICY=" + json.dumps(report["policy"], sort_keys=True))

    page1, lat1, bytes1 = await call_view(session, 1, 16)
    report["page1_latency_seconds"] = round(lat1, 3)
    report["page1_payload_bytes"] = bytes1
    caps = page1.get("capabilities") or {}
    status = page1.get("catalog_status") or {}
    research_names = caps.get("research")
    research_names = research_names if isinstance(research_names, list) else []
    report["identity"] = {
        "status": page1.get("status"),
        "view_tick": page1.get("tick"),
        "view_surface": page1.get("surface"),
        "catalog_tick": caps.get("tick"),
        "catalog_surface": caps.get("surface"),
        "game_version": caps.get("game_version"),
        "force": caps.get("force"),
        "catalog_status": status.get("status"),
        "total_count": status.get("total_count"),
        "total_pages": status.get("total_pages"),
        "page_size": status.get("page_size"),
        "source_fingerprint": caps.get("source_fingerprint"),
        "truncated": caps.get("truncated"),
        "research_count": len(research_names),
        "research_sample": research_names[:8],
        "enabled_content": caps.get("enabled_content"),
    }
    log("IDENTITY=" + json.dumps(report["identity"], sort_keys=True)[:1200])

    recipes = rows_of(page1)
    categories, hidden, enabled, fluid_products, unlock_effects = set(), 0, 0, 0, 0
    multi_category = 0
    for r in recipes:
        if r.get("category"):
            categories.add(r["category"])
        hidden += bool(r.get("hidden"))
        enabled += bool(r.get("enabled"))
        if len(r.get("categories") or []) > 1:
            multi_category += 1
        for p in (r.get("products") or []):
            fluid_products += p.get("type") == "fluid"
        for t in (r.get("unlock_technologies") or []):
            unlock_effects += bool(t.get("name"))
    report["page1_content_kinds"] = {
        "rows": len(recipes),
        "categories": sorted(categories),
        "category_count": len(categories),
        "multi_category_rows": multi_category,
        "hidden": hidden,
        "enabled": enabled,
        "fluid_products": fluid_products,
        "unlock_effects": unlock_effects,
        "sample": [
            {
                "name": r.get("name"), "enabled": r.get("enabled"),
                "hidden": r.get("hidden"), "simple": r.get("simple"),
                "category": r.get("category"),
                "categories": r.get("categories"),
                "crafting_time": r.get("crafting_time"),
                "ingredients": (r.get("ingredients") or [])[:2],
                "products": (r.get("products") or [])[:2],
                "unlock_technologies": (r.get("unlock_technologies") or [])[:2],
            }
            for r in recipes[:3]
        ],
    }
    log("PAGE1_CONTENT=" + json.dumps(
        report["page1_content_kinds"]["sample"][:2], sort_keys=True)[:900])

    total_pages = status.get("total_pages") or 0
    sweep: dict = {
        "page_size": 16, "pages_fetched": 0, "rows": [], "latencies": [],
        "fingerprints": set(), "ticks": set(), "forces": set(), "surfaces": set(),
        "versions": set(), "research_sets": set(), "content_sets": set(), "errors": [],
    }
    for page in range(1, total_pages + 1):
        try:
            raw, lat, _ = await call_view(session, page, 16)
        except Exception as exc:
            sweep["errors"].append({"page": page, "error": repr(exc)[:300]})
            break
        sweep["pages_fetched"] += 1
        sweep["latencies"].append(round(lat, 3))
        c = raw.get("capabilities") or {}
        sweep["fingerprints"].add(c.get("source_fingerprint"))
        sweep["ticks"].add(c.get("tick"))
        sweep["forces"].add(c.get("force"))
        sweep["surfaces"].add(c.get("surface"))
        sweep["versions"].add(c.get("game_version"))
        sweep["research_sets"].add(json.dumps(c.get("research") or [], sort_keys=True))
        sweep["content_sets"].add(json.dumps(c.get("enabled_content") or [], sort_keys=True))
        sweep["rows"].extend(c.get("recipes") or [])
    names_seen = [r.get("name") for r in sweep["rows"]]
    sweep["rows_total"] = len(sweep["rows"])
    sweep["declared_total"] = status.get("total_count")
    sweep["unique_names"] = len(set(names_seen))
    sweep["duplicate_names"] = sorted({n for n in names_seen if names_seen.count(n) > 1})[:10]
    sweep["sorted_globally"] = names_seen == sorted(names_seen)
    for key, field in (("fingerprint", "fingerprints"), ("tick", "ticks"),
                        ("force", "forces"), ("surface", "surfaces"),
                        ("version", "versions"), ("research", "research_sets"),
                        ("content", "content_sets")):
        sweep["single_" + key] = len(sweep[field]) == 1
    sweep["ticks_observed"] = sorted(t for t in sweep["ticks"] if t is not None)
    sweep["latency_min"] = min(sweep["latencies"]) if sweep["latencies"] else None
    sweep["latency_max"] = max(sweep["latencies"]) if sweep["latencies"] else None
    sweep["latency_mean"] = (
        round(sum(sweep["latencies"]) / len(sweep["latencies"]), 3)
        if sweep["latencies"] else None
    )
    # Modded evidence: how much of the catalog is mod content rather than
    # vanilla. This is derived from the observed recipe names only.
    mod_prefixes = ("py-", "pymodpack", "space-exploration", "cargo-bays",
                    "cybersyn", "milestones", "flib", "timetools")
    mod_rows = [
        n for n in names_seen
        if isinstance(n, str) and n.startswith(mod_prefixes)
    ]
    sweep["modded_recipe_rows"] = len(mod_rows)
    sweep["modded_recipe_sample"] = sorted(mod_rows)[:12]
    sweep.pop("rows")
    report["pagination_sweep"] = sweep
    log("SWEEP=" + json.dumps(sweep, sort_keys=True, default=str)[:1600])

    sizes = {}
    for size in (1, 2, 32):
        try:
            raw, lat, nbytes = await call_view(session, 1, size)
            st = raw.get("catalog_status") or {}
            rows = len(rows_of(raw))
            sizes[str(size)] = {
                "status": st.get("status"), "total_count": st.get("total_count"),
                "total_pages": st.get("total_pages"), "rows": rows,
                "latency_seconds": round(lat, 3), "payload_bytes": nbytes,
                "ok": st.get("status") == "ok"
                and rows == min(size, st.get("total_count") or 0),
            }
        except Exception as exc:
            sizes[str(size)] = {"error": repr(exc)[:200]}
    report["page_sizes"] = sizes
    log("PAGE_SIZES=" + json.dumps(sizes, sort_keys=True))

    invalid = {}
    for label, page, size in (
        ("page_0", 0, 16), ("page_over_max", 10001, 16),
        ("size_0", 1, 0), ("size_33", 1, 33), ("page_over_total", 99999, 16),
    ):
        try:
            raw, lat, _ = await call_view(session, page, size)
            st = raw.get("catalog_status") or {}
            invalid[label] = {
                "returned": True, "status": st.get("status"),
                "latency_seconds": round(lat, 3),
                "rejected": st.get("status") in {"page_out_of_range", "catalog_limit"}
                or raw.get("status") != "ok",
            }
        except Exception as exc:
            invalid[label] = {
                "returned": False, "rejected": True,
                "error_type": type(exc).__name__, "error": repr(exc)[:200],
            }
    report["invalid_inputs"] = invalid
    log("INVALID_INPUTS=" + json.dumps(invalid, sort_keys=True)[:800])


async def run_mcp(dll, rcon_port, password, report):
    async with stdio_client(mcp_params(dll, rcon_port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await probe(session, report)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-port", type=int, default=34251)
    ap.add_argument("--rcon-port", type=int, default=27151)
    ap.add_argument("--run-tag", default="modded-live")
    ap.add_argument("--backend", default=str(RESTRICTED_BACKEND))
    ap.add_argument("--connect-client", action="store_true",
                    help="also start a local client that connects to the server so "
                         "the single-player read gate is satisfied")
    args = ap.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    dll = Path(args.backend)
    report: dict = {
        "run_tag": args.run_tag, "workspace": str(ROOT), "exe": str(EXE),
        "restricted_backend": str(dll),
        "backend_sha256": digest(dll) if dll.is_file() else None,
        "game_port": args.game_port, "rcon_port": args.rcon_port,
        "read_only_tools_called": sorted(READ_ONLY_CALLS),
        "evidence_kind": "LIVE READ-ONLY (MODDED / Pyanodons)",
        "source_save": str(MODDED_SAVE),
        "mods": str(MODS),
    }
    out_path = EVIDENCE / f"{args.run_tag}.json"

    for required, label in ((dll, "restricted backend DLL"), (EXE, "factorio.exe"),
                            (MODDED_SAVE, "modded save"), (MODS, "mod directory"),
                            (BASE_CONFIG, "base config"), (SERVER_SETTINGS, "server settings")):
        if not Path(required).is_file() and not Path(required).is_dir():
            report["fatal"] = f"{label} missing: {required}"
            out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            log("FATAL=" + report["fatal"])
            return 2
    for port in (args.game_port, args.rcon_port):
        if not port_is_free(port):
            report["fatal"] = f"port {port} already occupied"
            out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            log("FATAL=" + report["fatal"])
            return 3

    run_save = EVIDENCE / f"{args.run_tag}-save.zip"
    shutil.copy2(MODDED_SAVE, run_save)
    report["run_save"] = str(run_save)
    report["original_save_sha256"] = digest(MODDED_SAVE)

    log_path = EVIDENCE / f"{args.run_tag}-factorio.log"
    password = secrets.token_hex(32)

    # A headless server needs its own config with the run port and the
    # ephemeral password. The launcher profile config is never modified.
    run_config = EVIDENCE / f"{args.run_tag}-config.ini"
    config_text = Path(BASE_CONFIG).read_text(encoding="utf-8-sig")
    config_text = re.sub(r"(?m)^local-rcon-socket=.*$",
                         f"local-rcon-socket=127.0.0.1:{args.rcon_port}", config_text)
    config_text = re.sub(r"(?m)^local-rcon-password=.*$",
                         f"local-rcon-password={password}", config_text)
    run_config.write_text(config_text, encoding="utf-8")
    report["run_config"] = str(run_config)
    report["run_config_ephemeral_password"] = True

    proc = out = err = None
    client = client_out = client_err = None
    try:
        out = log_path.open("w", encoding="utf-8")
        err = log_path.with_suffix(".err.log").open("w", encoding="utf-8")
        proc = subprocess.Popen([
            str(EXE), "--config", str(run_config), "--mod-directory", str(MODS),
            "--start-server", str(run_save),
            "--server-settings", str(SERVER_SETTINGS),
            "--bind", f"127.0.0.1:{args.game_port}",
            "--rcon-bind", f"127.0.0.1:{args.rcon_port}", "--rcon-password", password,
        ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        log(f"SERVER_PID={proc.pid}")
        started, ok, why = time.monotonic(), False, "timeout"
        while time.monotonic() - started < 600:
            if proc.poll() is not None:
                why = f"server exited rc={proc.returncode}"
                break
            text = log_path.read_text(encoding="utf-8", errors="replace")
            if "Starting RCON interface" in text:
                ok, why = True, "rcon ready"
                break
            time.sleep(0.8)
        report["server_started"] = ok
        report["server_ready_reason"] = why
        log(f"SERVER_READY={ok} ({why})")
        if not ok:
            text = log_path.read_text(encoding="utf-8", errors="replace")
            report["server_log_tail"] = text[-3000:]
            return 4
        text = log_path.read_text(encoding="utf-8", errors="replace")
        loaded = sorted(set(re.findall(r"Loading mod ([A-Za-z0-9_.-]+) ([0-9.]+)", text)))
        report["mods_loaded"] = [f"{name} {version}" for name, version in loaded]
        report["mod_count_loaded"] = len(loaded)
        report["pyanodons_loaded"] = sorted(
            name for name, _ in loaded if name.lower().startswith("py")
        )
        log("MODS_LOADED=" + json.dumps(report["mods_loaded"], sort_keys=True)[:1400])
        report["server_log_errors"] = [
            line[:250] for line in text.splitlines()
            if " Error " in line or "Exception" in line
        ][:10]

        if args.connect_client:
            # The restricted backend only observes a single connected player.
            # A local client joins the disposable server so the read gate is
            # satisfied. The client issues no gameplay command.
            # The client needs its OWN write-data directory: sharing the
            # server's makes the game refuse to start with "Couldn't create
            # lock file".
            # Always use the authenticated persistent Pyanodons client.
            # Per-run client profiles discard the token and demand login.
            client_root = env.prepare_client_profile(args.run_tag, BASE_CONFIG)
            client_config = client_root / "config.ini"
            if not env.has_authentication(client_root / "data" / "player-data.json"):
                raise RuntimeError("Persistent Pyanodons client has no authentication")
            report["client_config"] = str(client_config)
            client_log = EVIDENCE / f"{args.run_tag}-client.log"
            client_out = client_log.open("w", encoding="utf-8")
            client_err = client_log.with_suffix(".err.log").open("w", encoding="utf-8")
            client = subprocess.Popen([
                str(EXE), "--config", str(client_config),
                "--mod-directory", str(MODS),
                "--mp-connect", f"127.0.0.1:{args.game_port}",
            ], stdout=client_out, stderr=client_err,
                creationflags=subprocess.CREATE_NO_WINDOW)
            log(f"CLIENT_PID={client.pid}")
            report["client_pid"] = client.pid
            joined = False
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                text = log_path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"Player .* joined", text):
                    joined = True
                    break
                if client.poll() is not None:
                    break
                time.sleep(1.0)
            report["client_joined"] = joined
            log(f"CLIENT_JOINED={joined}")
            if joined:
                time.sleep(8)

        asyncio.run(run_mcp(dll, args.rcon_port, password, report))
    except Exception as exc:
        report["harness_error"] = repr(exc)[:800]
        log("HARNESS_ERROR=" + report["harness_error"])
    finally:
        for process in (client, proc):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=15)
        if proc is not None:
            log("TEST_SERVER_STOPPED=True")
        for f in (out, err, client_out, client_err):
            if f:
                f.close()
        for f in (out, err):
            if f:
                f.close()
        try:
            run_save.unlink()
            report["run_save_removed"] = True
        except OSError:
            report["run_save_removed"] = False
        try:
            run_config.unlink()
            report["run_config_removed"] = True
        except OSError:
            report["run_config_removed"] = False
        # The authenticated client profile is reused between test runs.
        # Never delete or reset its token, even when this run fails.
        report["client_profile_preserved"] = True
        report["original_save_sha256_after"] = digest(MODDED_SAVE)
        report["original_save_unchanged"] = (
            report["original_save_sha256_after"] == report["original_save_sha256"]
        )
        report["ephemeral_rcon_secret_discarded"] = True
        out_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=list),
                            encoding="utf-8")
        log("EVIDENCE=" + str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
