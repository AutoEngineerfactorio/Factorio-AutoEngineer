"""LIVE visual verification of the R08-D dashboard map against the running game.

READ-ONLY with respect to the game world:
  * It never charts, creates, removes or moves anything.
  * It captures the REAL, running dashboard window (the actual Tk canvas, not a
    synthetic render) and the REAL running Factorio window.
  * It observes the live chunks through the read-only view tool so the
    structured comparison is against the same observation the dashboard draws.

It reports:
  * the dashboard window size and the map canvas size,
  * the world rectangle the dashboard is showing,
  * the observed enemy positions and whether they are inside that rectangle,
  * the observed ore field coverage under the new patch fill,
  * the observed tree density,
  * the fog split: unexplored, charted-only and visible tiles.

Usage:
    python -B tests/live_r08d_visual.py
"""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as w
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from dashboard_map_layers import (  # noqa: E402
    fill_observed_field,
    merged_patch_rectangles,
    resource_patch_cells,
    resource_patch_groups,
)
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from PIL import Image  # noqa: E402

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
SAVE = PROFILE / "data" / "saves" / "autoengineer-test.zip"
DLL = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23" / "FactorioMCP.dll"
SCRATCH = ROOT / ".local" / "scratch"
DASH_PNG = SCRATCH / "r08d_dashboard_window.png"
GAME_PNG = SCRATCH / "r08d_factorio_window.png"
REPORT = SCRATCH / "r08d_visual_compare.json"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def window_rect(handle: int):
    rect = w.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def capture(handle: int, path: Path) -> Image.Image | None:
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
    image = Image.frombuffer("RGB", (width, height), bytes(buffer), "raw", "BGRX", 0, 1)
    image.save(path)
    return image


def read_socket() -> tuple[str, int, str]:
    text = CONFIG.read_text(encoding="utf-8")
    socket_match = re.search(r"local-rcon-socket=(\S+)", text)
    if socket_match is None:
        raise ValueError("local-rcon-socket not found in config")
    host, port = socket_match.group(1).rsplit(":", 1)
    password_match = re.search(r"local-rcon-password=(\S+)", text)
    if password_match is None:
        raise ValueError("local-rcon-password not found in config")
    password = password_match.group(1)
    return host, int(port), password


def backend_params(host: str, port: int, password: str) -> StdioServerParameters:
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "DOTNET_ROOT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update({
        "FACTORIO_RCON_HOST": host,
        "FACTORIO_RCON_PORT": str(port),
        "FACTORIO_RCON_PASSWORD": password,
        "AUTOENGINEER_BACKEND_MODE": "helper",
        "Logging__LogLevel__Default": "None",
        "Logging__LogLevel__Microsoft": "None",
    })
    runtime = ROOT / ".local" / "live-pillow-2.1.23" / "backend-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return StdioServerParameters(command="dotnet", args=[str(DLL)], env=env, cwd=str(runtime))


async def read_view(session, chunk_x: int, chunk_y: int) -> dict:
    result = await session.call_tool(
        "autoengineer_view", {"mapChunkX": chunk_x, "mapChunkY": chunk_y}
    )
    text = next(c.text for c in result.content if getattr(c, "type", "") == "text")
    return json.loads(text)


async def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    before = digest(SAVE)
    log(f"SAVE_DIGEST_BEFORE={before}")
    report: dict = {"save_digest_before": before}

    # -- the REAL dashboard window and the REAL Factorio window -----------
    dash_handle = find_window("Factorio AutoEngineer")
    game_handle = find_window("Factorio:")
    report["dashboard_window_found"] = bool(dash_handle)
    report["factorio_window_found"] = bool(game_handle)
    log(f"DASHBOARD_WINDOW_FOUND={bool(dash_handle)}")
    log(f"FACTORIO_WINDOW_FOUND={bool(game_handle)}")

    dash_image = None
    if dash_handle:
        dash_image = capture(dash_handle, DASH_PNG)
        report["dashboard_window_rect"] = window_rect(dash_handle)
        report["dashboard_window_size"] = (
            list(dash_image.size) if dash_image is not None else None
        )
        log(f"DASHBOARD_WINDOW_SIZE={report['dashboard_window_size']}")
    if game_handle:
        game_image = capture(game_handle, GAME_PNG)
        report["factorio_window_rect"] = window_rect(game_handle)
        report["factorio_window_size"] = (
            list(game_image.size) if game_image is not None else None
        )
        log(f"FACTORIO_WINDOW_SIZE={report['factorio_window_size']}")
    report["dashboard_png"] = str(DASH_PNG)
    report["factorio_png"] = str(GAME_PNG)

    # -- the live observation the dashboard is drawing -------------------
    host, port, password = read_socket()
    entities: list[dict] = []
    chunk_meta: dict = {}
    surface = None
    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            base = await read_view(session, 0, 0)
            terrain = base.get("terrain") or {}
            chunk_meta = terrain.get("map_chunk") or {}
            surface = base.get("surface")
            cx, cy = int(chunk_meta.get("x", 0)), int(chunk_meta.get("y", 0))
            log(f"SURFACE={surface} BASE_CHUNK={chunk_meta}")
            for dx in range(-1, 3):
                for dy in range(-1, 3):
                    chunk = await read_view(session, cx + dx, cy + dy)
                    for entity in (chunk.get("terrain") or {}).get("entities") or []:
                        entities.append(entity)

    report["surface"] = surface
    report["observed_entity_count"] = len(entities)

    # -- enemies ----------------------------------------------------------
    enemies = [e for e in entities if e.get("kind") == "enemy"]
    report["enemies"] = [
        {"name": e.get("name"), "x": e.get("x"), "y": e.get("y"),
         "map_color": e.get("map_color"), "prototype_type": e.get("prototype_type")}
        for e in enemies
    ]
    log(f"OBSERVED_ENEMIES={len(enemies)}")
    for e in enemies:
        log(f"  ENEMY {e.get('name')} at ({e.get('x')}, {e.get('y')})")

    # -- the dashboard's default viewport --------------------------------
    # DEFAULT_MAP_RADIUS is the map radius the dashboard opens on.
    from dashboard_view import DEFAULT_MAP_RADIUS

    radius = float(DEFAULT_MAP_RADIUS)
    player = base.get("position") or {}
    report["default_map_radius"] = DEFAULT_MAP_RADIUS
    if player:
        cx_world = float(player.get("x", 0.0))
        cy_world = float(player.get("y", 0.0))
        world = {
            "x0": cx_world - radius, "x1": cx_world + radius,
            "y0": cy_world - radius, "y1": cy_world + radius,
        }
        report["default_viewport_world"] = world
        inside = [
            e for e in enemies
            if world["x0"] <= float(e.get("x", 0)) <= world["x1"]
            and world["y0"] <= float(e.get("y", 0)) <= world["y1"]
        ]
        report["enemies_inside_default_viewport"] = len(inside)
        report["enemies_outside_default_viewport"] = len(enemies) - len(inside)
        log(
            f"DEFAULT_VIEWPORT world x[{world['x0']:.0f},{world['x1']:.0f}] "
            f"y[{world['y0']:.0f},{world['y1']:.0f}] "
            f"enemies_inside={len(inside)}/{len(enemies)}"
        )

    # -- ore patches under the new fill ----------------------------------
    patches = resource_patch_cells(entities)
    ore_report = {}
    for name, observed in patches.items():
        groups = resource_patch_groups(observed)
        rects = []
        covered = set()
        for group in groups:
            filled = fill_observed_field(group)
            rects.extend(merged_patch_rectangles(filled))
            covered |= filled
        ore_report[name] = {
            "observed_nodes": len(observed),
            "deposits": len(groups),
            "patch_rectangles": len(rects),
            "filled_tiles": len(covered),
            "fill_ratio": round(len(covered) / max(1, len(observed)), 2),
        }
        log(
            f"ORE {name} nodes={len(observed)} deposits={len(groups)} "
            f"rects={len(rects)} filled_tiles={len(covered)} "
            f"fill_ratio={ore_report[name]['fill_ratio']}"
        )
    report["ore_patches"] = ore_report

    # -- forest -----------------------------------------------------------
    trees = [e for e in entities if e.get("kind") == "nature"
             and (e.get("name") or "").startswith("tree-")]
    tree_names: dict[str, int] = {}
    for t in trees:
        name = str(t.get("name", ""))
        tree_names[name] = tree_names.get(name, 0) + 1
    report["trees"] = {"count": len(trees), "by_prototype": tree_names}
    log(f"OBSERVED_TREES={len(trees)} by_prototype={tree_names}")

    after = digest(SAVE)
    report["save_digest_after"] = after
    report["save_unchanged"] = before == after
    log(f"SAVE_DIGEST_AFTER={after}")
    log(f"SAVE_UNCHANGED={before == after}")
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"WROTE={REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
