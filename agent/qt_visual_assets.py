"""Small vector UI assets and explicit Windows font discovery for Qt."""
import math
import os
from importlib import import_module
from pathlib import Path
from typing import Any

_fonts_loaded = False


def install_fonts() -> None:
    global _fonts_loaded
    if _fonts_loaded:
        return
    gui=import_module("PySide6.QtGui")
    widgets=import_module("PySide6.QtWidgets")
    app=widgets.QApplication.instance()
    if app is None:
        return
    folder=Path(os.environ.get("WINDIR", "C:/Windows"))/"Fonts"
    for name in ("segoeui.ttf","segoeuib.ttf","seguisb.ttf","consola.ttf","seguisym.ttf","seguiemj.ttf"):
        path=folder/name
        if path.is_file():
            gui.QFontDatabase.addApplicationFont(str(path))
    app.setFont(gui.QFont("Segoe UI",10))
    _fonts_loaded=True


PATHS={
    "dashboard": '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
    "brain": '<path d="M12 4C7 0 2 5 5 9C0 12 4 19 8 18C8 23 12 22 12 19ZM12 4C17 0 22 5 19 9C24 12 20 19 16 18C16 23 12 22 12 19M7 7L10 9M17 7L14 9M6 14L10 12M18 14L14 12"/>',
    "blueprint": '<rect x="3" y="3" width="18" height="18"/><path d="M8 3V21M16 3V21M3 8H21M3 16H21"/>',
    "chart": '<path d="M3 20H22M4 17V11M9 17V7M14 17V3M19 17V8"/>',
    "research": '<path d="M9 3H15M10 3V9L4 19Q3 21 6 21H18Q21 21 20 19L14 9V3M8 14H16"/>',
    "inventory": '<rect x="3" y="8" width="18" height="13" rx="2"/><path d="M8 8V4H16V8M8 12V18M16 12V18"/>',
    "power": '<path d="M14 2L4 14H11L9 22L21 9H13Z"/>',
    "save": '<path d="M4 3H18L21 6V21H3V3ZM7 3V9H17V3M7 21V14H17V21"/>',
    "logs": '<path d="M5 2H15L20 7V22H4V2M15 2V8H20M8 12H16M8 16H16"/>',
    "map": '<path d="M3 5L9 2L15 5L21 2V19L15 22L9 19L3 22ZM9 2V19M15 5V22"/>',
    "logistics": '<path d="M2 6H15V17H2ZM15 10H20L23 14V17H15"/><circle cx="6" cy="19" r="2"/><circle cx="19" cy="19" r="2"/>',
    "play": '<path d="M8 4L20 12L8 20Z"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    "folder": '<path d="M2 6H9L12 9H22L20 21H2ZM2 6V3H10L13 6H21V9"/>',
    "refresh": '<path d="M20 8A8 8 0 1 0 20 17M20 2V8H14"/>',
    "bell": '<path d="M5 17H19L17 13V8A5 5 0 0 0 7 8V13ZM10 21H14"/>',
    "terminal": '<path d="M4 5L11 12L4 19M13 19H21"/>',
}


def icon(name: str, color: str = "#b8c1c7", size: int = 24) -> Any:
    gui=import_module("PySide6.QtGui")
    color=gui.QColor(color).name()
    if name in ("gear","settings"):
        points=[]
        for step in range(48):
            angle=step*math.pi/24
            radius=10 if step%6 in (1,2,3,4) else 8
            points.append(f"{12+radius*math.cos(angle):.2f},{12+radius*math.sin(angle):.2f}")
        body=f'<polygon points="{" ".join(points)}" fill="{color}" stroke="#34200a"/><circle cx="12" cy="12" r="5.5" fill="#10171b"/><circle cx="12" cy="12" r="3" fill="{color}"/>'
    else:
        body=PATHS.get(name,PATHS["dashboard"])
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>'
    pixmap=gui.QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"),"SVG")
    return gui.QIcon(pixmap)
