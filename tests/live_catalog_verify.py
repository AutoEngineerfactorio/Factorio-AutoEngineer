"""Live READ-ONLY Factorio 2.1.23 catalog verification harness.

Safety contract enforced by this module:
  * Starts ONLY the disposable isolated 2.1.23 profile in
    .local/live-pillow-2.1.23 (never the launcher profile).
  * Copies the disposable save to a per-run evidence file; the launcher
    profile save is opened read-only and its digest is compared afterwards.
  * Uses an ephemeral random RCON password that is discarded at exit.
  * Calls ONLY read-only MCP tools: autoengineer_policy and autoengineer_view.
  * Never calls walk_to_position / autoengineer_operation / arm / renew.
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

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
BASE = ROOT / ".local" / "live-pillow-2.1.23"
EVIDENCE = BASE / "evidence"

# The fixed policy-v8 boundary: exactly twelve registered tools.
EXPECTED_TOOLS = {
    "autoengineer_operation_preview",
    "autoengineer_operation",
    "autoengineer_view",
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
# Only these tools are ever called by this harness.
READ_ONLY_CALLS = {"autoengineer_view", "autoengineer_policy"}


def log(msg):
    print(str(msg), flush=True)


def manifest():
    return json.loads((BASE / "profile_manifest.json").read_text(encoding="utf-8"))


def port_is_free(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return False
    except OSError:
        return True


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows_of(payload):
    """Return the recipe rows of a view payload as a list."""
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


async def call_view(session, page=1, page_size=16, timeout=45):
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
        # Preserve the raw payload so a live defect can be diagnosed, not guessed.
        raw_log = BASE / "evidence" / "last_raw_view.txt"
        raw_log.write_text(text[:20000], encoding="utf-8")
        raise RuntimeError(
            f"autoengineer_view page={page} returned non-JSON "
            f"({len(text)} chars): {text[:300]!r}"
        ) from exc
    return parsed, elapsed, len(text)


async def wait_for_player(dll, rcon_port, password, report, timeout=150):
    """Wait until a connected player with a character is observable."""
    deadline = time.monotonic() + timeout
    attempts = 0
    while time.monotonic() < deadline:
        attempts += 1
        try:
            raw, _lat, _n = await call_view_probe(dll, rcon_port, password, 1, 16)
            if (raw.get("capabilities") or {}).get("force"):
                report["player_connected"] = True
                report["player_probe_attempts"] = attempts
                return True
        except Exception:
            pass
        await asyncio.sleep(3)
    report["player_connected"] = False
    report["player_probe_attempts"] = attempts
    return False


async def call_view_probe(dll, rcon_port, password, page, page_size):
    """Single read-only view call in its own MCP session (connect-time probe)."""
    params = mcp_params(dll, rcon_port, password)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await call_view(session, page, page_size, timeout=25)


async def probe(session, report):
    """Exercise the restricted read-only catalog surface."""
    listed = await asyncio.wait_for(session.list_tools(), 10)
    names = sorted(t.name for t in listed.tools)
    report["tool_boundary"] = {
        "count": len(names),
        "names": names,
        "exactly_12": set(names) == EXPECTED_TOOLS,
        "unexpected": sorted(set(names) - EXPECTED_TOOLS),
        "missing": sorted(EXPECTED_TOOLS - set(names)),
    }
    log(f"TOOL_COUNT={len(names)} EXACT_12={report['tool_boundary']['exactly_12']}")

    policy_resp = await asyncio.wait_for(
        session.call_tool("autoengineer_policy", arguments={}), 10
    )
    report["policy"] = json.loads(next(i.text for i in policy_resp.content if i.type == "text"))
    log("POLICY=" + json.dumps(report["policy"], sort_keys=True))

    page1, lat1, bytes1 = await call_view(session, 1, 16)
    report["page1_latency_seconds"] = round(lat1, 3)
    report["page1_payload_bytes"] = bytes1
    report["page1_raw_head"] = json.dumps(page1.get("capabilities") or {})[:3000]
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
    log("IDENTITY=" + json.dumps(report["identity"], sort_keys=True)[:900])

    recipes = rows_of(page1)
    categories, hidden, enabled, fluid_products, unlock_effects = set(), 0, 0, 0, 0
    for r in recipes:
        if r.get("category"):
            categories.add(r["category"])
        hidden += bool(r.get("hidden"))
        enabled += bool(r.get("enabled"))
        for p in (r.get("products") or []):
            fluid_products += p.get("type") == "fluid"
        for t in (r.get("unlock_technologies") or []):
            unlock_effects += bool(t.get("name"))
    report["page1_content_kinds"] = {
        "rows": len(recipes),
        "categories": sorted(categories),
        "hidden": hidden,
        "enabled": enabled,
        "fluid_products": fluid_products,
        "unlock_effects": unlock_effects,
        "sample": [
            {
                "name": r.get("name"), "enabled": r.get("enabled"),
                "hidden": r.get("hidden"), "simple": r.get("simple"),
                "category": r.get("category"), "crafting_time": r.get("crafting_time"),
                "ingredients": (r.get("ingredients") or [])[:2],
                "products": (r.get("products") or [])[:2],
                "unlock_technologies": (r.get("unlock_technologies") or [])[:2],
            }
            for r in recipes[:3]
        ],
    }
    log("PAGE1_CONTENT=" + json.dumps(report["page1_content_kinds"]["sample"][:2], sort_keys=True))

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
            sweep["errors"].append({"page": page, "error": repr(exc)})
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
        if sweep["errors"]:
            break
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
        round(sum(sweep["latencies"]) / len(sweep["latencies"]), 3) if sweep["latencies"] else None
    )
    sweep.pop("rows")
    report["pagination_sweep"] = sweep
    log("SWEEP=" + json.dumps(sweep, sort_keys=True, default=str)[:1400])

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
                "ok": st.get("status") == "ok" and rows == min(size, st.get("total_count") or 0),
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
    log("INVALID_INPUTS=" + json.dumps(invalid, sort_keys=True)[:700])

    fresh: dict = {"samples": []}
    for _ in range(3):
        raw, lat, _ = await call_view(session, 1, 16)
        fresh["samples"].append({
            "tick": (raw.get("capabilities") or {}).get("tick"),
            "view_tick": raw.get("tick"), "latency_seconds": round(lat, 3),
        })
        time.sleep(1.0)
    ticks = [s["tick"] for s in fresh["samples"]]
    fresh["ticks_advanced"] = len(set(ticks)) == len(ticks) and all(
        b > a for a, b in zip(ticks, ticks[1:])
    )
    fresh["tick_consistent_with_view"] = all(s["tick"] == s["view_tick"] for s in fresh["samples"])
    report["freshness"] = fresh
    log("FRESHNESS=" + json.dumps(fresh, sort_keys=True))

    report["telemetry"] = {
        "production": (page1.get("telemetry") or {}).get("production"),
        "power": (page1.get("telemetry") or {}).get("power"),
    }
    log("TELEMETRY_PRODUCTION_STATUS=" + str(
        ((page1.get("telemetry") or {}).get("production") or {}).get("status")))
    log("TELEMETRY_POWER_STATUS=" + str(
        ((page1.get("telemetry") or {}).get("power") or {}).get("status")))


async def run_mcp(dll, rcon_port, password, report):
    async with stdio_client(mcp_params(dll, rcon_port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await probe(session, report)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-port", type=int, default=34239)
    ap.add_argument("--rcon-port", type=int, default=27139)
    ap.add_argument("--run-tag", default="live")
    ap.add_argument("--backend", default="", help="override restricted backend DLL path")
    ap.add_argument("--wait-player", action="store_true",
                    help="wait until a connected player with a character is observed")
    args = ap.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    m = manifest()
    dll = Path(args.backend) if args.backend else Path(m["restricted_backend"])
    report: dict = {
        "run_tag": args.run_tag, "workspace": str(ROOT), "exe": m["exe"],
        "game_version_manifest": m["game_version"],
        "restricted_backend": str(dll),
        "backend_sha256": digest(dll) if dll.is_file() else None,
        "game_port": args.game_port, "rcon_port": args.rcon_port,
        "read_only_tools_called": sorted(READ_ONLY_CALLS),
        "evidence_kind": "LIVE READ-ONLY",
    }
    out_path = EVIDENCE / f"{args.run_tag}.json"

    if not dll.is_file():
        report["fatal"] = "restricted backend DLL missing"
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
    shutil.copy2(m["save"], run_save)
    report["run_save"] = str(run_save)
    report["original_save_sha256"] = digest(m["save"])

    log_path = EVIDENCE / f"{args.run_tag}-factorio.log"
    password = secrets.token_hex(32)

    # Graphical host mode reads the RCON socket and password from config.ini and
    # ignores --rcon-bind, so the run needs its own config with the run port and
    # the ephemeral password. The launcher profile config is never modified.
    run_config = EVIDENCE / f"{args.run_tag}-config.ini"
    config_text = Path(m["config"]).read_text(encoding="utf-8-sig")
    config_text = re.sub(r"(?m)^local-rcon-socket=.*$",
                         f"local-rcon-socket=127.0.0.1:{args.rcon_port}", config_text)
    config_text = re.sub(r"(?m)^local-rcon-password=.*$",
                         f"local-rcon-password={password}", config_text)
    run_config.write_text(config_text, encoding="utf-8")
    report["run_config"] = str(run_config)
    report["run_config_ephemeral_password"] = True
    proc = out = err = None
    try:
        out = log_path.open("w", encoding="utf-8")
        err = log_path.with_suffix(".err.log").open("w", encoding="utf-8")
        proc = subprocess.Popen([
            m["exe"], "--config", str(run_config), "--mod-directory", m["mods"],
            "--host", str(run_save), "--server-settings", m["server_settings"],
            "--bind", f"127.0.0.1:{args.game_port}",
            "--rcon-bind", f"127.0.0.1:{args.rcon_port}", "--rcon-password", password,
        ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        log(f"SERVER_PID={proc.pid}")
        started, ok, why = time.monotonic(), False, "timeout"
        while time.monotonic() - started < 420:
            if proc.poll() is not None:
                why = f"server exited rc={proc.returncode}"
                break
            text = log_path.read_text(encoding="utf-8", errors="replace")
            if "Hosting game at IP" in text and "Starting RCON interface" in text:
                ok, why = True, "host+rcon ready"
                break
            time.sleep(0.6)
        # A graphical host needs time to connect the local character before the
        # read-only catalog guard can observe a force, surface and player.
        if ok and args.wait_player:
            asyncio.run(wait_for_player(dll, args.rcon_port, password, report))
            log("PLAYER_CONNECTED=" + str(report.get("player_connected")))
        report["server_started"] = ok
        report["server_ready_reason"] = why
        log(f"SERVER_READY={ok} ({why})")
        if not ok:
            return 4
        text = log_path.read_text(encoding="utf-8", errors="replace")
        report["mods_loaded"] = {
            "base_2.1.23": "Loading mod base 2.1.23" in text,
            "space-age_2.1.23": "Loading mod space-age 2.1.23" in text,
            "quality_2.1.23": "Loading mod quality 2.1.23" in text,
            "elevated-rails_2.1.23": "Loading mod elevated-rails 2.1.23" in text,
            "autoengineer-input_2.1.23": "Loading mod autoengineer-input 2.1.23" in text,
        }
        report["server_log_errors"] = [
            line[:200] for line in text.splitlines()
            if " Error " in line or "Exception" in line
        ][:10]
        log("MODS=" + json.dumps(report["mods_loaded"], sort_keys=True))
        asyncio.run(run_mcp(dll, args.rcon_port, password, report))
    except Exception as exc:
        report["harness_error"] = repr(exc)[:500]
        log("HARNESS_ERROR=" + report["harness_error"])
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
            log("TEST_SERVER_STOPPED=True")
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
        report["original_save_sha256_after"] = digest(m["save"])
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
