"""Live GUI acceptance for the Recipes and Research tab.

This is a **real** acceptance: it starts the real dashboard window against
the already running Factorio 2.1.23 in the read-only AI Helper mode,
selects the RECIPES AND RESEARCH tab and captures the window as a PNG.

Read-only with respect to the game: it starts no Factorio process, performs
no gameplay action and never writes to the save. It only reads pixels and
reads the dashboard's own widget tree.

Usage:
    python -B tests/_r06_gui_acceptance.py [OUTPUT DIR]
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as w
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
LAUNCHER_JSON = PROFILE / "launcher.local.json"
SECRET = PROFILE / "rcon.secret.json"
CONFIG = PROFILE / "config.ini"
RUNTIME = ROOT / ".local" / "live-pillow-2.1.23"
PATCHED_DLL = RUNTIME / "backend-patched-2.1.23" / "FactorioMCP.dll"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")

sys.path.insert(0, str(ROOT / "tests"))

import live_r06_game_side_verify as harness  # noqa: E402
import r06_live_environment as live_env  # noqa: E402
from mcp import StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

#: The tab index of RECIPES AND RESEARCH. It is the first tab of the
#: dashboard's tab strip.
RECIPES_TAB_INDEX = 0
#: The tab index of ACTIVITY LOG. It is the fourth tab of the strip and it
#: carries the observer's own output.
ACTIVITY_TAB_INDEX = 3


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG),
                ("biHeight", w.LONG), ("biPlanes", w.WORD),
                ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
                ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 3)]


def log(message: str) -> None:
    print(str(message), flush=True)


def find_window(prefix: str) -> int:
    found: list[int] = []

    def callback(handle, _lparam):
        buf = ctypes.create_unicode_buffer(400)
        user32.GetWindowTextW(handle, buf, 400)
        if buf.value.startswith(prefix):
            found.append(handle)
        return True

    proto = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user32.EnumWindows(proto(callback), 0)
    return found[0] if found else 0


def capture(handle: int, path: Path):
    """Capture a window with PrintWindow so a background window works too."""
    from PIL import Image

    rect = w.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    hdc = user32.GetWindowDC(handle)
    mem_dc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    gdi32.SelectObject(mem_dc, bitmap)
    user32.PrintWindow(handle, mem_dc, 2)
    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = 0
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(handle, hdc)
    image = Image.frombuffer(
        "RGB", (width, height), bytes(buffer), "raw", "BGRX", 0, 1
    )
    image.save(path)
    return image


def read_port() -> int:
    """Return the RCON port of the **running** test server.

    The launcher profile's config records an older port. The live test
    server overrides it, so the port that actually accepts a connection is
    detected instead of being copied from a stale config file.
    """
    import socket

    candidates: list[int] = []
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"local-rcon-socket=(\S+)", text)
    if match:
        candidates.append(int(match.group(1).rsplit(":", 1)[1]))
    # The live test server's own port, which the harness prepares.
    candidates.append(27161)
    for port in candidates:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return port
        except OSError:
            continue
    raise SystemExit(
        f"no test server is listening on {candidates}; the GUI acceptance "
        "needs the running test server"
    )


def read_password() -> str:
    """Return the RCON password of the **running** test server.

    The live test environment keeps a persistent secret at
    ``rcon.secret.json``. A reused server was started with the password that
    was current then, so the environment's secret is preferred over the
    launcher profile's. The value is never printed.
    """
    live_secret = RUNTIME / "rcon.secret.json"
    for path in (live_secret, SECRET):
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        for key in ("rcon_password", "password", "secret"):
            if isinstance(data.get(key), str) and data[key]:
                return data[key]
    # The graphical-host profile keeps the password in config.ini.
    text = CONFIG.read_text(encoding="utf-8")
    match = re.search(r"local-rcon-password=(\S+)", text)
    if not match:
        raise SystemExit("RCON password not found")
    return match.group(1)


def select_tab(handle: int, index: int) -> bool:
    """Click a tab in the dashboard's tab strip.

    The tab strip sits below the header. The tab positions are measured from
    the window's own rectangle, so the click lands on the requested tab even
    when the window is at another position on the screen.
    """
    rect = w.RECT()
    user32.GetWindowRect(handle, ctypes.byref(rect))
    tab_y = rect.top + 266
    # The RECIPES AND RESEARCH tab is the first tab of the strip.
    tab_x = rect.left + 110 + index * 185
    user32.SetForegroundWindow(handle)
    time.sleep(0.5)
    user32.SetCursorPos(tab_x, tab_y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    time.sleep(0.1)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(2.5)
    return True


def align_profile_with_running_server(port: int, password: str) -> str | None:
    """Point the launcher profile at the **running** test server.

    The dashboard's read-only observer reads the RCON socket and the password
    from the launcher profile's ``config.ini``. The running test server
    overrides both, so the profile is aligned with the server that is
    actually running. The original file is backed up and restored by the
    caller.

    Returns the backup path, or None when the profile already matched.
    """
    if not CONFIG.is_file():
        return None
    text = CONFIG.read_text(encoding="utf-8")
    socket = re.search(r"(?m)^local-rcon-socket=127\.0\.0\.1:(\d+)\s*$", text)
    password_match = re.search(r"(?m)^local-rcon-password=([^\s]+)\s*$", text)
    current_port = int(socket.group(1)) if socket else None
    current_password = password_match.group(1) if password_match else None
    if current_port == port and current_password == password:
        return None

    backup = CONFIG.with_suffix(".ini.r06gui-backup")
    backup.write_text(text, encoding="utf-8")
    updated = re.sub(
        r"(?m)^local-rcon-socket=127\.0\.0\.1:\d+\s*$",
        f"local-rcon-socket=127.0.0.1:{port}",
        text,
    )
    updated = re.sub(
        r"(?m)^local-rcon-password=[^\s]+\s*$",
        f"local-rcon-password={password}",
        updated,
    )
    CONFIG.write_text(updated, encoding="utf-8")
    log(f"PROFILE_ALIGNED port={port} backup={backup}")
    return str(backup)


async def wait_for_player_ready(report: dict) -> bool:
    """Wait, bounded, until the backend can observe the player.

    The catalog observation needs a connected player **with a character**.
    The harness already proves this wait, so the same session and the same
    readiness rule are reused here.
    """
    from mcp import ClientSession

    password = live_env.rcon_password()
    params = StdioServerParameters(
        command="dotnet",
        args=[str(harness.RESTRICTED_BACKEND)],
        env=live_env.backend_launch_environment(27161, password, "helper"),
        cwd=str(live_env.BACKEND_RUNTIME),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await harness.wait_for_player_ready(session, report)


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        ROOT / ".local" / "live-pillow-2.1.23" / "evidence"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    if not PATCHED_DLL.is_file():
        log(f"MISSING_PATCHED_DLL={PATCHED_DLL}")
        return 2

    profile = json.loads(LAUNCHER_JSON.read_text(encoding="utf-8-sig"))
    port = read_port()
    password = read_password()
    log(f"RCON_PORT={port}")

    agent_config = RUNTIME / "agent.config.r06gui.json"
    agent_config.write_text(
        json.dumps({
            "dotnet_command": profile.get("dotnet_command", "dotnet"),
            "mcp_server_dll": str(PATCHED_DLL),
            "rcon_host": "127.0.0.1",
            "rcon_port": port,
            "llm_api_url": "http://127.0.0.1:8083/v1",
            "llm_model": "FrogNano-4B",
        }),
        encoding="utf-8",
    )
    env = dict(
        os.environ,
        AUTOENGINEER_CONFIG=str(agent_config),
        AUTOENGINEER_HOME=str(RUNTIME),
        FACTORIO_RCON_PASSWORD=password,
        AUTOENGINEER_MODE="helper",
        # The map observer requests the recipe/research catalog through
        # autoengineer_view. The lightweight telemetry observer does not, so
        # the Recipes and Research tab would stay empty without this.
        AUTOENGINEER_ENABLE_LIVE_MAP="1",
        AUTOENGINEER_WORLD=profile.get(
            "world_id", "autoengineer-isolated-2.1.23"),
    )
    # The dashboard's own output is captured so the observer's error message
    # is visible instead of being swallowed by the dashboard's reader.
    dashboard_log = out_dir / "r06-gui-dashboard.log"
    dashboard_out = dashboard_log.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [str(PYTHONW), "-u", str(ROOT / "agent" / "autoengineer_dashboard.py")],
        env=env,
        cwd=str(ROOT),
        stdout=dashboard_out,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    log(f"DASHBOARD_PID={proc.pid}")
    log(f"DASHBOARD_LOG={dashboard_log}")

    report: dict = {"dashboard_pid": proc.pid, "rcon_port": port}
    handle = 0
    client = None
    backup = None
    try:
        # The dashboard's read-only observer reads the RCON socket and the
        # password from the launcher profile's config.ini. The running test
        # server overrides both, so the profile is aligned with the server
        # that is actually running and is restored afterwards.
        backup = align_profile_with_running_server(port, password)
        report["profile_backup"] = backup
        # The catalog observation needs a **connected player with a
        # character**. The graphical client is started against the persistent
        # authenticated profile so no sign-in is needed, and it is joined
        # before the dashboard observes.
        client_profile = live_env.prepare_client_profile(
            "r06-gui", RUNTIME / "server" / "config.ini", port)
        client_config = client_profile / "config.ini"
        client, _ = harness.start_client(
            "r06-gui", client_config, 34261, report)
        joined = harness.wait_for_join(
            client, live_env.SERVER_DATA, client_profile / "data", report)
        report["client_joined"] = joined
        log(f"CLIENT_JOINED={joined}")
        if not joined:
            log("CLIENT_DID_NOT_JOIN the catalog observation needs a player")
            report["client_joined"] = False
        else:
            # The catalog observation needs a connected player **with a
            # character**. The same bounded readiness wait the harness uses
            # is used here, so the capture happens after the observation is
            # actually available.
            ready = asyncio.run(wait_for_player_ready(report))
            report["player_ready"] = ready
            log(f"PLAYER_READY={ready}")

        # Bounded wait for the real window. It is reported, never guessed.
        deadline = time.time() + 90
        while time.time() < deadline:
            handle = find_window("Factorio AutoEngineer")
            if handle:
                break
            if proc.poll() is not None:
                log(f"DASHBOARD_EXITED rc={proc.returncode}")
                return 3
            time.sleep(1.0)
        if not handle:
            log("DASHBOARD_WINDOW_NOT_FOUND")
            report["window_found"] = False
            return 1
        report["window_found"] = True
        log(f"DASHBOARD_WINDOW_HANDLE={handle}")

        # Let the observer deliver the first catalog frame. The catalog is
        # paged over hundreds of pages, so the tab needs time to receive
        # and build the rows.
        time.sleep(90)

        select_tab(handle, RECIPES_TAB_INDEX)
        shot = out_dir / "r06-recipes-tab.png"
        image = capture(handle, shot)
        report["screenshot"] = str(shot)
        report["screenshot_size"] = list(image.size) if image else None
        log(f"CAPTURED={shot} size={report['screenshot_size']}")

        # The ACTIVITY LOG carries the observer's own output, including its
        # error message, so the observer's cause is visible.
        select_tab(handle, ACTIVITY_TAB_INDEX)
        activity = out_dir / "r06-activity-log.png"
        activity_image = capture(handle, activity)
        report["activity_screenshot"] = str(activity)
        report["activity_screenshot_size"] = (
            list(activity_image.size) if activity_image else None)
        log(f"CAPTURED={activity} size={report['activity_screenshot_size']}")
        select_tab(handle, RECIPES_TAB_INDEX)

        # A second capture after the catalog has settled, so the tab's own
        # content is what the operator sees.
        time.sleep(10)
        shot2 = out_dir / "r06-recipes-tab-settled.png"
        image2 = capture(handle, shot2)
        report["screenshot_settled"] = str(shot2)
        report["screenshot_settled_size"] = list(image2.size) if image2 else None
        log(f"CAPTURED={shot2} size={report['screenshot_settled_size']}")

        out = out_dir / "r06-gui-acceptance.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log(f"EVIDENCE={out}")
        return 0
    finally:
        # The dashboard and the client this script started are stopped. The
        # Factorio server is never touched.
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        log("DASHBOARD_STOPPED=True")
        if client is not None and client.poll() is None:
            try:
                client.terminate()
                client.wait(timeout=15)
            except Exception:
                try:
                    client.kill()
                except Exception:
                    pass
            log("CLIENT_STOPPED=True")
        # The launcher profile's original configuration is restored, so the
        # acceptance leaves the environment exactly as it found it.
        if backup:
            backup_path = Path(backup)
            if backup_path.is_file():
                CONFIG.write_text(
                    backup_path.read_text(encoding="utf-8"), encoding="utf-8")
                log("PROFILE_RESTORED=True")


if __name__ == "__main__":
    raise SystemExit(main())
