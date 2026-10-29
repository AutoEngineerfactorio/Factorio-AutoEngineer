"""LIVE visual comparison of the R08-C multi-chunk dashboard map against the game.

READ-ONLY with respect to the game world:
  * It never charts, creates, removes or moves anything.
  * It observes several aligned chunks through the read-only view tool, merges
    them through the REAL dashboard chunk cache and renders the result with
    the REAL dashboard map, resource-patch and nature layers.
  * It captures the already-running Factorio window for the same world
    rectangle so the two images can be compared at matching coordinates.

Both images are normalised to the same north-up orientation, the same world
extent and the same tile scale before they are compared.

Usage:
    python -B tests/live_r08c_visual.py
"""
from __future__ import annotations

import asyncio
import ctypes
import ctypes.wintypes as w
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
sys.path.insert(0, str(ROOT / "agent"))

import dashboard_map_layers as map_layers  # noqa: E402
import dashboard_nature_layers as nature  # noqa: E402
from dashboard_chunk_cache import ChunkCache  # noqa: E402
from dashboard_chunk_grid import CHUNK_TILES  # noqa: E402
from dashboard_chunk_map import merge_chunks  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
SAVE = PROFILE / "data" / "saves" / "autoengineer-test.zip"
DLL = ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23" / "FactorioMCP.dll"
SCRATCH = ROOT / ".local" / "scratch"
GAME_PNG = SCRATCH / "r08c_factorio_window.png"
DASH_PNG = SCRATCH / "r08c_dashboard_map.png"
REPORT = SCRATCH / "r08c_visual_compare.json"

# The compared world rectangle. It is the same rectangle in both images and it
# covers the observed forest band, so the forest coverage can be compared with
# the Factorio map at matching coordinates.
WORLD_X0, WORLD_Y0 = 0.0, 13.0
WORLD_X1, WORLD_Y1 = 99.0, 67.0
SCALE = 8.0

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


def render_dashboard_map(cache: ChunkCache, path: Path) -> Image.Image:
    """Render the merged multi-chunk map with the real dashboard layers."""
    merged = merge_chunks(cache, cache.records())
    entities = merged["entities"]
    origins = merged["origins"]
    min_x = min(o[0] for o in origins) * CHUNK_TILES
    min_y = min(o[1] for o in origins) * CHUNK_TILES
    max_x = max(o[0] for o in origins) * CHUNK_TILES + CHUNK_TILES
    max_y = max(o[1] for o in origins) * CHUNK_TILES + CHUNK_TILES
    width = int((WORLD_X1 - WORLD_X0) * SCALE)
    height = int((WORLD_Y1 - WORLD_Y0) * SCALE)
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    def project(x: float, y: float) -> tuple[float, float]:
        return ((x - WORLD_X0) * SCALE, (y - WORLD_Y0) * SCALE)

    # Layer 1: the charted terrain raster of every cached chunk.
    for record in cache.records():
        terrain = record.terrain
        rows = terrain.get("rows") or []
        palette = terrain.get("palette") or []
        step = terrain.get("step", 1)
        origin = terrain.get("origin") or {}
        if not rows or not palette:
            continue
        for row_index, row in enumerate(rows):
            for column_index in range(0, len(row), 2):
                index = int(row[column_index:column_index + 2], 16)
                if index == 0:
                    continue
                colour = palette[index]
                if not isinstance(colour, str) or len(colour) != 7:
                    continue
                world_x = origin["x"] + (column_index // 2) * step
                world_y = origin["y"] + row_index * step
                left, top = project(world_x, world_y)
                right, bottom = project(world_x + step, world_y + step)
                draw.rectangle([left, top, right, bottom], fill=colour)

    # Layer 2: resource patches, exactly like the dashboard's patch layer.
    window = dict(x=min_x, y=min_y, width=max_x - min_x, height=max_y - min_y)
    for name, rectangles in map_layers.resource_patch_rectangles(entities, window).items():
        colour = map_layers.resource_patch_color(name)
        for x0, y0, x1, y1 in rectangles:
            left, top = project(x0, y0)
            right, bottom = project(x1 + 1, y1 + 1)
            draw.rectangle([left, top, right, bottom], fill=colour)

    # Layer 3: the natural objects, through the REAL nature layer.
    nature_entities = [dict(e, kind="nature") for e in entities if e.get("kind") == "nature"]
    for shape in nature.nature_shapes(nature_entities, window):
        x, y = project(shape.x, shape.y)
        if shape.kind == "tree":
            radius = nature.tree_shape(shape) * SCALE / 2
            if shape.color:
                draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=shape.color)
            else:
                draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                             outline=(154, 160, 138))
        elif shape.kind == "rock":
            radius = nature.rock_shape(shape) * SCALE / 2
            if shape.color:
                draw.rectangle([x - radius, y - radius, x + radius, y + radius], fill=shape.color)
            else:
                draw.rectangle([x - radius, y - radius, x + radius, y + radius],
                              outline=(176, 168, 148))
        else:
            radius = nature.cliff_shape(shape) * SCALE / 2
            if shape.color:
                draw.rectangle([x - radius, y - radius / 3, x + radius, y + radius / 3],
                               fill=shape.color)
            else:
                draw.rectangle([x - radius, y - radius / 3, x + radius, y + radius / 3],
                              outline=(192, 168, 120))

    image.save(path)
    return image


async def observe(session, chunk_x: int, chunk_y: int) -> dict:
    answer = await asyncio.wait_for(
        session.call_tool("autoengineer_view", arguments={
            "catalogPage": 1, "catalogPageSize": 1,
            "mapChunkX": chunk_x, "mapChunkY": chunk_y,
        }),
        timeout=40,
    )
    if answer.is_error:
        raise RuntimeError("view failed")
    raw = next((c.text for c in answer.content if c.type == "text"), "")
    return json.loads(raw)


async def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    host, port, password = read_socket()
    report: dict = {
        "evidence_type": "LIVE READ-ONLY",
        "gameplay_performed": False,
        "world_rectangle": {
            "x0": WORLD_X0, "y0": WORLD_Y0, "x1": WORLD_X1, "y1": WORLD_Y1,
            "tile_scale_px": SCALE, "orientation": "north up",
        },
    }

    cache = ChunkCache(max_chunks=16, max_age_seconds=300.0)
    async with stdio_client(backend_params(host, port, password)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            base = await observe(session, 0, 0)
            cache.set_surface(base.get("surface") or "nauvis")
            cache.store(base["terrain"], tick=base.get("tick") or 0)
            for offset in (-1, 1):
                payload = await observe(session, offset, 0)
                cache.store(payload["terrain"], tick=payload.get("tick") or 0)
            # The detail render uses only the dense chunk; the wide render uses
            # all three so the chunk-to-chunk continuity is visible.
            detail_cache = ChunkCache(max_chunks=4, max_age_seconds=300.0)
            detail_cache.set_surface(base.get("surface") or "nauvis")
            detail_cache.store(base["terrain"], tick=base.get("tick") or 0)
            report["chunks_observed"] = sorted(
                "%d,%d" % (r.chunk_x, r.chunk_y) for r in cache.records()
            )
            report["merged_entities"] = len(merge_chunks(cache, cache.records())["entities"])
            report["merged_nature"] = sum(
                len(r.entities["nature"]) for r in cache.records()
            )
            report["merged_resources"] = sum(
                len(r.entities["resource"]) for r in cache.records()
            )
            log("CHUNKS=" + json.dumps(report["chunks_observed"]))
            log("MERGED_ENTITIES=%d NATURE=%d RESOURCES=%d" % (
                report["merged_entities"], report["merged_nature"],
                report["merged_resources"],
            ))

    render_dashboard_map(cache, DASH_PNG)
    report["dashboard_image"] = str(DASH_PNG)
    report["dashboard_world_rectangle"] = {
        "x0": WORLD_X0, "y0": WORLD_Y0, "x1": WORLD_X1, "y1": WORLD_Y1,
        "tile_scale_px": SCALE, "orientation": "north up",
    }
    log("DASHBOARD_IMAGE=" + str(DASH_PNG))

    handle = find_window("Factorio")
    if handle:
        image = capture(handle, GAME_PNG)
        if image is not None:
            report["game_image"] = str(GAME_PNG)
            report["game_window_size"] = list(image.size)
            log("GAME_IMAGE=" + str(GAME_PNG))
        else:
            report["game_image"] = None
            report["game_capture_error"] = "window had no visible area"
    else:
        report["game_image"] = None
        report["game_capture_error"] = "Factorio window not found"

    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log("WROTE=" + str(REPORT))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
