"""Focused live probe: dump the exact autoengineer_view capability shape.

Starts the disposable 2.1.23 graphical host, waits for a connected player, and
prints the first catalog page verbatim (bounded) so the exact field names and
the reason for an empty or truncated recipe list can be inspected.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_catalog_verify import (  # noqa: E402
    EVIDENCE,
    call_view,
    manifest,
    mcp_params,
)
from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

ROOT_BACKEND = (
    Path(r"D:\AI\Factorio-AutoEngineer-Source\.local\live-pillow-2.1.23")
    / "backend-patched-2.1.23" / "FactorioMCP.dll"
)


async def run(dll, rcon_port, password):
    params = mcp_params(dll, rcon_port, password)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for page in (1, 2):
                raw, latency, size = await call_view(session, page, 16)
                caps = raw.get("capabilities") or {}
                status = raw.get("catalog_status") or {}
                print(f"--- PAGE {page} latency={latency:.3f}s bytes={size} ---")
                print("TOP_KEYS=" + json.dumps(sorted(raw.keys())))
                print("CAP_KEYS=" + json.dumps(sorted(caps.keys())))
                print("STATUS=" + json.dumps(status, sort_keys=True))
                print("CAP_SCALARS=" + json.dumps({
                    k: v for k, v in caps.items()
                    if not isinstance(v, (list, dict))
                }, sort_keys=True))
                recipes = caps.get("recipes")
                print("RECIPES_TYPE=" + type(recipes).__name__)
                print("RECIPES_LEN=" + str(len(recipes) if recipes is not None else None))
                if recipes:
                    print("RECIPE0=" + json.dumps(recipes[0], sort_keys=True)[:1200])
                research = caps.get("research")
                print("RESEARCH_TYPE=" + type(research).__name__)
                print("RESEARCH_LEN=" + str(len(research) if research is not None else None))


def main():
    m = manifest()
    fixed = ROOT_BACKEND if ROOT_BACKEND.is_file() else Path(m["restricted_backend"])
    dll = fixed
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_save = EVIDENCE / "shape-probe-save.zip"
    shutil.copy2(m["save"], run_save)
    password = secrets.token_hex(32)
    log_path = EVIDENCE / "shape-probe-factorio.log"
    game_port, rcon_port = 34251, 27151

    import re
    run_config = EVIDENCE / "shape-probe-config.ini"
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
        print("SERVER_READY=" + str(ready))
        if not ready:
            return 4
        asyncio.run(run(dll, rcon_port, password))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
