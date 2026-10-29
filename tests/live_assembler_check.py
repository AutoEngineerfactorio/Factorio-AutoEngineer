"""Live check: the Python catalog assembler against the real 2.1.23 game.

Reads all catalog pages from the running isolated game through the restricted
backend and runs the production assembler (agent/catalog_assembly.py) on them.

Expected: the assembler FAILS CLOSED because the game tick advances while the
42 pages are read. That is the designed behaviour, not a defect: a catalog
assembled across different ticks is not a single consistent snapshot.

Read-only: only autoengineer_view and autoengineer_policy are called.
"""
import asyncio
import json
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
sys.path.insert(0, str(ROOT / "agent"))

from catalog_assembly import (  # noqa: E402
    PAGE_SIZE,
    CatalogAssemblyError,
    assemble_catalog,
)

BASE = ROOT / ".local" / "live-pillow-2.1.23"
EVIDENCE = BASE / "evidence"
BACKEND = BASE / "backend-patched-2.1.23" / "FactorioMCP.dll"

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


def log(m):
    print(str(m), flush=True)


def rows_of(payload) -> list:
    """Return the recipe rows of a view payload as a list."""
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        return []
    recipes = capabilities.get("recipes")
    return recipes if isinstance(recipes, list) else []


def mcp_params(rcon_port, password):
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
    return StdioServerParameters(command="dotnet", args=[str(BACKEND)], env=env, cwd=str(runtime))


import os  # noqa: E402
import re  # noqa: E402


async def run(rcon_port, password):
    async with stdio_client(mcp_params(rcon_port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Poll inside one session until the connected character appears.
            deadline = time.monotonic() + 150
            first_raw = {}
            while time.monotonic() < deadline:
                response = await asyncio.wait_for(
                    session.call_tool(
                        "autoengineer_view",
                        arguments={"catalogPage": 1, "catalogPageSize": PAGE_SIZE},
                    ),
                    timeout=45,
                )
                text = next(i.text for i in response.content if i.type == "text")
                first_raw = json.loads(text)
                if rows_of(first_raw):
                    break
                await asyncio.sleep(4)
            rows = rows_of(first_raw)
            log("PAGE1_ROWS=" + str(len(rows)))
            log("PAGE1_TOTAL=" + str((first_raw.get("catalog_status") or {}).get("total_count")))
            if not rows:
                return "no_player", "page one had no catalog rows yet"
            started = time.monotonic()
            try:
                assembled = await assemble_catalog(session, first_raw)
            except CatalogAssemblyError as exc:
                log("ASSEMBLER_FAILED_CLOSED=" + str(exc))
                log("ASSEMBLER_ELAPSED_S=" + str(round(time.monotonic() - started, 2)))
                return "failed_closed", str(exc)
            log("ASSEMBLER_SUCCEEDED rows=" + str(len(rows_of(assembled))))
            log("ASSEMBLER_ELAPSED_S=" + str(round(time.monotonic() - started, 2)))
            return "assembled", str(len(rows_of(assembled)))


def main():
    m = json.loads((BASE / "profile_manifest.json").read_text(encoding="utf-8"))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_save = EVIDENCE / "assembler-check-save.zip"
    shutil.copy2(m["save"], run_save)
    password = secrets.token_hex(32)
    log_path = EVIDENCE / "assembler-check-factorio.log"
    game_port, rcon_port = 34265, 27165

    run_config = EVIDENCE / "assembler-check-config.ini"
    text = Path(m["config"]).read_text(encoding="utf-8-sig")
    text = re.sub(r"(?m)^local-rcon-socket=.*$",
                  f"local-rcon-socket=127.0.0.1:{rcon_port}", text)
    text = re.sub(r"(?m)^local-rcon-password=.*$",
                  f"local-rcon-password={password}", text)
    run_config.write_text(text, encoding="utf-8")

    out = log_path.open("w", encoding="utf-8")
    err = log_path.with_suffix(".err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([
        m["exe"], "--config", str(run_config), "--mod-directory", m["mods"],
        "--host", str(run_save), "--server-settings", m["server_settings"],
        "--bind", f"127.0.0.1:{game_port}",
    ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    outcome: dict = {"result": None, "detail": None}
    try:
        started, ready = time.monotonic(), False
        while time.monotonic() - started < 420:
            if proc.poll() is not None:
                break
            body = log_path.read_text(encoding="utf-8", errors="replace")
            if "Hosting game at IP" in body and "Starting RCON interface" in body:
                ready = True
                break
            time.sleep(0.6)
        log("SERVER_READY=" + str(ready))
        if not ready:
            return 4
        # Wait for the connected character before reading the catalog. The
        # retry keeps one MCP session open so the player can connect.
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                result, detail = asyncio.run(run(rcon_port, password))
                if result == "no_player":
                    time.sleep(4)
                    continue
                outcome["result"] = result
                outcome["detail"] = detail
                break
            except Exception as exc:
                log("RETRY=" + repr(exc)[:200])
                time.sleep(4)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        out.close()
        err.close()
        for path in (run_save, run_config):
            try:
                path.unlink()
            except OSError:
                pass
        (EVIDENCE / "assembler-check.json").write_text(
            json.dumps(outcome, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
