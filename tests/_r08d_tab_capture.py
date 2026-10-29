"""Capture one tab of the running dashboard window.

It finds the real dashboard window, selects a named tab and captures the
window, so the operator can read the Activity Log or another tab directly
from the running application rather than from a synthetic render.

Read-only with respect to the game: it only reads pixels.

Usage:
    python -B tests/_r08d_tab_capture.py [TAB INDEX] [OUTPUT PNG]
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".local" / "scratch"

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
    from PIL import Image

    rect = w.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
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


def main() -> int:
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else SCRATCH / "r08d_dashboard_tab.png"
    handle = find_window("Factorio AutoEngineer")
    if not handle:
        print("DASHBOARD_WINDOW_NOT_FOUND")
        return 1
    # Click the tab: the tab strip sits at a fixed height below the window top.
    rect = w.RECT()
    user32.GetWindowRect(handle, ctypes.byref(rect))
    tab_y = rect.top + 270
    tab_x = rect.left + 300 + index * 175
    user32.SetForegroundWindow(handle)
    user32.SetCursorPos(tab_x, tab_y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(2)
    image = capture(handle, out)
    print(f"CAPTURED={out} size={image.size if image else None}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
