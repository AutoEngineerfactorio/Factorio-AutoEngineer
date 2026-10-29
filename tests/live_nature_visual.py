"""LIVE visual comparison of the dashboard nature map against the real game.

READ-ONLY with respect to the game world:
  * It never charts, creates, removes or moves anything.
  * It only captures the already-running Factorio window and renders the
    dashboard map from the live observation that the read-only observer
    already produced.
  * It writes images and a JSON report under .local/scratch/.

What it compares, at the same world coordinates:
  * The Factorio in-game map (window capture).
  * The AutoEngineer dashboard map rendered by the REAL nature layer from the
    SAME live observation, including the terrain raster, the resource patches
    and the natural objects.

The dashboard map is rendered here with the real ``dashboard_view`` drawing
code and the real ``dashboard_nature_layers`` classification, so the image is
what the dashboard would draw for that observation.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
sys.path.insert(0, str(ROOT / "agent"))

import dashboard_map_layers as map_layers  # noqa: E402
import dashboard_nature_layers as nature  # noqa: E402

SCRATCH = ROOT / ".local" / "scratch"
EVIDENCE = SCRATCH / "live_nature_evidence.json"
GAME_PNG = SCRATCH / "r08_factorio_window.png"
DASH_PNG = SCRATCH / "r08_dashboard_map.png"
REPORT = SCRATCH / "r08_visual_compare.json"

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


def window_title(handle):
    buf = ctypes.create_unicode_buffer(400)
    user32.GetWindowTextW(handle, buf, 400)
    return buf.value


def find_window(prefix):
    found = []

    def callback(handle, _lparam):
        title = window_title(handle)
        if title.startswith(prefix) and user32.IsWindowVisible(handle):
            found.append((handle, title))
        return True

    proto = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user32.EnumWindows(proto(callback), 0)
    return found


def capture_window(handle, path):
    """Capture a window with PrintWindow so a background window works too.

    A minimised window has no drawable area, so it is restored for the
    capture and minimised again afterwards. Only the window state changes; no
    game state is touched.
    """
    was_iconic = bool(user32.IsIconic(handle))
    if was_iconic:
        # SW_RESTORE
        user32.ShowWindow(handle, 9)
        user32.SetForegroundWindow(handle)
        time.sleep(1.5)
    try:
        rect = w.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            raise RuntimeError("GetWindowRect failed")
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise RuntimeError("window has no visible area")
        hdc = user32.GetWindowDC(handle)
        mem_dc = gdi32.CreateCompatibleDC(hdc)
        bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
        gdi32.SelectObject(mem_dc, bitmap)
        # 2 = PW_RENDERFULLCONTENT
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
    finally:
        if was_iconic:
            # SW_MINIMIZE
            user32.ShowWindow(handle, 6)


def render_dashboard_map(observation, path, width=1100, height=800):
    """Render the dashboard map for the live observation at 1:1 world scale."""
    terrain = observation.get("terrain", {})
    entities = terrain.get("entities", [])
    origin = terrain.get("origin", {"x": 0, "y": 0})
    player = observation.get("position") or {"x": 0, "y": 0}

    # 1:1 world-tile scale, centred on the player, like the dashboard's 1:1
    # zoom option.
    scale = 6.0
    centre_x = player["x"]
    centre_y = player["y"]

    def project(x, y):
        return (width / 2 + (x - centre_x) * scale,
                height / 2 + (y - centre_y) * scale)

    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Layer 1: the charted terrain raster, using the observed tile colours.
    rows = terrain.get("rows") or []
    palette = terrain.get("palette") or []
    step = terrain.get("step", 2)
    if rows and palette:
        for row_index, row in enumerate(rows):
            for column_index, pair in enumerate(range(0, len(row), 2)):
                index = int(row[pair:pair + 2], 16)
                if index == 0:
                    continue
                colour = palette[index]
                if not isinstance(colour, str) or len(colour) != 7:
                    continue
                world_x = origin["x"] + column_index * step
                world_y = origin["y"] + row_index * step
                left, top = project(world_x, world_y)
                right, bottom = project(world_x + step, world_y + step)
                draw.rectangle([left, top, right, bottom], fill=colour)

    # Layer 2: resource patches, exactly like the dashboard's patch layer.
    window = dict(x=origin["x"], y=origin["y"], width=256, height=256)
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
            radius = nature.tree_shape(shape) * scale / 2
            if shape.color:
                draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                             fill=shape.color)
            else:
                draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                             outline=(154, 160, 138))
        elif shape.kind == "rock":
            radius = nature.rock_shape(shape) * scale / 2
            if shape.color:
                draw.rectangle([x - radius, y - radius, x + radius, y + radius],
                               fill=shape.color)
            else:
                draw.rectangle([x - radius, y - radius, x + radius, y + radius],
                               outline=(176, 168, 148))
        else:
            radius = nature.cliff_shape(shape) * scale / 2
            if shape.color:
                draw.rectangle([x - radius, y - radius / 3, x + radius, y + radius / 3],
                               fill=shape.color)
            else:
                draw.rectangle([x - radius, y - radius / 3, x + radius, y + radius / 3],
                               outline=(192, 168, 120))

    # Layer 5: the player marker.
    px, py = project(centre_x, centre_y)
    draw.polygon([(px, py - 8), (px + 6, py + 6), (px - 6, py + 6)], fill=(94, 215, 245))

    image.save(path)
    return image


def main():
    report = {
        "evidence_type": "LIVE READ-ONLY",
        "gameplay_performed": False,
        "screenshots": {},
    }
    if not EVIDENCE.is_file():
        report["status"] = "no_observation"
        report["error"] = f"missing {EVIDENCE}"
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    observation = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    # The evidence file wraps the observation; the view payload is the
    # "observation" key produced by the live harness.
    view = observation.get("observation") or observation

    game_windows = find_window("Factorio:")
    report["game_windows"] = [{"handle": h, "title": t} for h, t in game_windows]
    if not game_windows:
        report["status"] = "no_game_window"
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 3
    handle = game_windows[0][0]
    game_image = capture_window(handle, GAME_PNG)
    report["screenshots"]["factorio_window"] = {
        "path": str(GAME_PNG),
        "size": list(game_image.size),
    }

    dash_image = render_dashboard_map(view, DASH_PNG)
    report["screenshots"]["dashboard_map"] = {
        "path": str(DASH_PNG),
        "size": list(dash_image.size),
    }

    terrain = view.get("terrain", {}) if isinstance(view, dict) else {}
    entities = terrain.get("entities", [])
    nature_entities = [dict(e, kind="nature") for e in entities if e.get("kind") == "nature"]
    shapes = nature.nature_shapes(nature_entities)
    report["status"] = "ok"
    report["player"] = view.get("position") if isinstance(view, dict) else None
    report["surface"] = view.get("surface") if isinstance(view, dict) else None
    report["tick"] = view.get("tick") if isinstance(view, dict) else None
    report["nature_count"] = len(nature_entities)
    report["nature_coloured"] = sum(1 for s in shapes if s.color)
    report["nature_uncoloured"] = sum(1 for s in shapes if s.color is None)
    report["nature_painted_white"] = sum(1 for s in shapes if s.color == "#ffffff")
    report["nature_colour_histogram"] = {}
    for shape in shapes:
        key = str(shape.color)
        report["nature_colour_histogram"][key] = \
            report["nature_colour_histogram"].get(key, 0) + 1
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
