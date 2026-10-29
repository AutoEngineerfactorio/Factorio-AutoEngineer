"""The Qt map widget: the interactive factory map.

This widget paints the scene that :mod:`qt_map_scene` prepares and adds
the interaction a user expects from a map: drag to pan, wheel to zoom,
and a layer switch for each overlay.

Two properties matter for performance, and both are enforced here:

* **The scene is built once per observation, not once per paint.** The
  widget keeps the prepared scene and only re-projects it when the
  viewport, the window size or the layer switches change.
* **A repaint that would draw the same thing is skipped.** The widget
  keeps the last viewport cache key and compares it, so a timer tick
  that brings no new observation does not repaint the map.

The widget holds no transport. It renders what the chunk cache and the
observation coordinator already produced, and it never asks the game for
anything itself.
"""

from __future__ import annotations

import math
from importlib import import_module
from typing import Any, Mapping

from qt_map_scene import LAYERS, TOGGLEABLE_LAYERS, MapScene, build_scene
from qt_map_viewport import Viewport, nearest_zoom_level, zoom_level_label
from qt_theme import Palette

try:
    qt_core = import_module("PySide6.QtCore")
    qt_gui = import_module("PySide6.QtGui")
    qt_widgets = import_module("PySide6.QtWidgets")
except ImportError as exc:  # pragma: no cover - depends on the environment
    raise SystemExit(
        "Optional UI requires PySide6: python -m pip install PySide6") from exc

Qt = qt_core.Qt
QPoint = qt_core.QPoint
Signal = qt_core.Signal

QBrush = qt_gui.QBrush
QColor = qt_gui.QColor
QPainter = qt_gui.QPainter
QPen = qt_gui.QPen

QWidget = qt_widgets.QWidget

#: The zoom step of one mouse-wheel notch.
ZOOM_STEP = 1.25

#: The layers the widget draws in back-to-front order.
DRAW_ORDER = LAYERS


class MapWidget(QWidget):
    """The interactive factory map."""

    #: Emitted when the visible viewport changed and new chunks are needed.
    viewportChanged = Signal(object)
    #: Emitted when the user asked for a different surface.
    surfaceRequested = Signal(str)

    def __init__(self, viewport: Viewport | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(480, 320)
        self.setMouseTracking(True)
        # The widget paints every pixel itself in ``paintEvent``. Qt must
        # not also fill the background, because the automatic fill happens
        # *after* the paint event and would wipe everything the painter
        # drew. ``WA_OpaquePaintEvent`` tells Qt that the widget covers
        # its whole area, so the automatic fill is skipped.
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._viewport = viewport or Viewport()
        self._scene: MapScene | None = None
        self._raster_images: list[tuple[float, float, Any]] = []
        self._merged_map: Mapping[str, Any] | None = None
        self._player: Mapping[str, Any] | None = None
        self._layers = {name: True for name in LAYERS}
        self._last_key: tuple | None = None
        self._drag_origin: QPoint | None = None
        self._drag_viewport: Viewport | None = None
        self._painted = 0
        self._skipped = 0

    # -- the observed content -------------------------------------------

    def set_map(self, merged_map: Mapping[str, Any] | None,
                player: Mapping[str, Any] | None = None) -> None:
        """Show a new observed map.

        The scene is rebuilt here, once, so the paint event only has to
        project and draw it.
        """
        self._raster_images.clear()
        rasters = merged_map.get("rasters") if isinstance(merged_map, Mapping) else None
        if isinstance(rasters, list):
            for raster in rasters[:64]:
                try:
                    if not isinstance(raster, dict):
                        continue
                    origin, rows, palette = raster["origin"], raster["rows"], raster["palette"]
                    x, y = origin["x"], origin["y"]
                    if (type(x) not in (int, float) or type(y) not in (int, float)
                            or not math.isfinite(x) or not math.isfinite(y)):
                        continue
                    if (not isinstance(rows, list) or len(rows) != 64
                            or not isinstance(palette, list) or not 1 <= len(palette) <= 256
                            or any(not isinstance(row, str) or len(row) != 128 for row in rows)):
                        continue
                    if any(not isinstance(c, str) or len(c) != 7 or not c.startswith("#") for c in palette):
                        continue
                    colors = [bytes.fromhex(color[1:]) for color in palette]
                    indexes = b"".join(bytes.fromhex(row) for row in rows)
                    if len(indexes) != 4096 or any(len(color) != 3 for color in colors):
                        continue
                    pixels = b"".join(colors[index] for index in indexes)
                    image = qt_gui.QImage(pixels, 64, 64, qt_gui.QImage.Format_RGB888).copy()
                    self._raster_images.append((float(x), float(y), image))
                except (KeyError, TypeError, ValueError, IndexError):
                    continue
        self._merged_map = merged_map
        self._player = player
        self._scene = build_scene(
            merged_map, player=player,
            pixels_per_tile=self._pixels_per_tile(),
            layers=self._layers)
        self._last_key = None
        self.update()

    @property
    def scene(self) -> MapScene | None:
        """The prepared scene, or ``None`` before the first observation."""
        return self._scene

    @property
    def viewport(self) -> Viewport:
        """The viewport the map shows."""
        return self._viewport

    def set_viewport(self, viewport: Viewport) -> None:
        """Move the map to another viewport."""
        self._viewport = viewport
        self._scene = build_scene(
            self._merged_map, player=self._player,
            pixels_per_tile=self._pixels_per_tile(),
            layers=self._layers)
        self._last_key = None
        self.viewportChanged.emit(viewport)
        self.update()

    # -- the layers -------------------------------------------------------

    def set_layer(self, name: str, enabled: bool) -> None:
        """Switch one layer on or off."""
        if name not in self._layers:
            raise KeyError(f"Unknown map layer: {name!r}")
        if self._layers[name] == enabled:
            return
        self._layers[name] = enabled
        if self._scene is not None:
            self._scene.layers[name] = enabled
        self._last_key = None
        self.update()

    def toggle_layer(self, name: str) -> bool:
        """Switch one layer and return its new state."""
        self.set_layer(name, not self._layers[name])
        return self._layers[name]

    def layer_enabled(self, name: str) -> bool:
        """Whether one layer is switched on."""
        return self._layers.get(name, True)

    @property
    def toggleable_layers(self) -> tuple[str, ...]:
        """The layers a user may switch."""
        return TOGGLEABLE_LAYERS

    # -- geometry ---------------------------------------------------------

    def _pixels_per_tile(self) -> float:
        """The screen pixels per world tile at the current size."""
        width = max(1, self.width())
        height = max(1, self.height())
        return self._viewport.pixels_per_tile(width, height)

    def _project(self, x: float, y: float) -> tuple[float, float]:
        """Project a world position onto the widget."""
        return self._viewport.project(
            x, y, max(1, self.width()), max(1, self.height()))

    # -- interaction ------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        """Start a pan drag."""
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_origin = event.position().toPoint()
        self._drag_viewport = self._viewport
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        """Pan the map while the mouse is held down."""
        if self._drag_origin is None or self._drag_viewport is None:
            super().mouseMoveEvent(event)
            return
        position = event.position().toPoint()
        delta = position - self._drag_origin
        if delta.isNull():
            return
        self._drag_origin = position
        self._viewport = self._drag_viewport.panned(
            float(delta.x()), float(delta.y()),
            max(1, self.width()), max(1, self.height()))
        self._drag_viewport = self._viewport
        self._last_key = None
        self.viewportChanged.emit(self._viewport)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        """End a pan drag."""
        self._drag_origin = None
        self._drag_viewport = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        """Zoom the map around the cursor."""
        steps = event.angleDelta().y() / 120.0
        if not steps:
            super().wheelEvent(event)
            return
        factor = ZOOM_STEP ** steps
        position = event.position()
        self._viewport = self._viewport.zoomed(
            factor, max(1, self.width()), max(1, self.height()),
            position.x(), position.y())
        self._last_key = None
        self.viewportChanged.emit(self._viewport)
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        """Centre the map on the double-clicked position."""
        x, y = self._viewport.unproject(
            event.position().x(), event.position().y(),
            max(1, self.width()), max(1, self.height()))
        self._viewport = self._viewport.centred_on(x, y)
        self._last_key = None
        self.viewportChanged.emit(self._viewport)
        self.update()

    # -- painting ---------------------------------------------------------

    def _cache_key(self) -> tuple:
        """Return the key that identifies what would be drawn."""
        content = self._scene.fingerprint() if self._scene is not None else None
        return self._viewport.cache_key(
            max(1, self.width()), max(1, self.height()), content)

    def paintEvent(self, event) -> None:
        """Draw the scene.

        The paint event always paints. The redraw is skipped **before** a
        repaint is requested, in :meth:`refresh`, where the widget can
        compare the cache key and decide that nothing changed. Deciding
        inside the paint event would be wrong: a paint event for a fresh
        target - a render into an image, or a region exposed by another
        window - would then draw nothing at all.
        """
        self._last_key = self._cache_key()
        self._painted += 1

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(Palette.WINDOW))
        if self._scene is None:
            painter.setPen(QColor(Palette.TEXT_MUTED))
            painter.drawText(15, 25, "Waiting for observed map data")
            painter.end()
            return

        scale = self._pixels_per_tile()
        if self._layers.get("terrain", True):
            for x, y, image in self._raster_images:
                px, py = self._project(x, y)
                painter.drawImage(qt_core.QRectF(px, py, 64 * scale, 64 * scale), image)
        for kind in DRAW_ORDER:
            if not self._layers.get(kind, True):
                continue
            for primitive in self._scene.by_layer(kind):
                self._draw_primitive(painter, primitive, scale)
        painter.end()

    def refresh(self) -> bool:
        """Request a repaint only when something actually changed.

        Returns whether a repaint was requested. A timer tick that
        brings no new observation, and a viewport that has not moved,
        cost nothing.
        """
        key = self._cache_key()
        if key == self._last_key:
            self._skipped += 1
            return False
        self.update()
        return True

    def _draw_primitive(self, painter: QPainter, primitive, scale: float) -> None:
        """Draw one primitive of the scene."""
        x, y = self._project(primitive.x, primitive.y)
        if primitive.kind == "terrain":
            side = max(1.0, scale)
            painter.fillRect(
                int(x), int(y), int(side) + 1, int(side) + 1,
                QColor(primitive.color))
            return
        if primitive.kind == "resource":
            painter.fillRect(
                int(x), int(y),
                max(1, int(primitive.width * scale)),
                max(1, int(primitive.height * scale)),
                QColor(primitive.color))
            return
        if primitive.kind == "building":
            if primitive.is_symbol:
                radius = max(2.0, primitive.radius * scale)
                painter.setBrush(QBrush(QColor(primitive.color)))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(
                    QPoint(int(x), int(y)), int(radius), int(radius))
                return
            painter.fillRect(
                int(x), int(y),
                max(1, int(primitive.width)),
                max(1, int(primitive.height)),
                QColor(primitive.color))
            return
        if primitive.kind == "enemy":
            radius = max(3.0, primitive.radius)
            painter.setBrush(QBrush(QColor(primitive.color)))
            painter.setPen(QPen(QColor(primitive.outline or "#ffd9d0"), 2))
            painter.drawEllipse(
                QPoint(int(x), int(y)), int(radius), int(radius))
            return
        if primitive.kind == "player":
            radius = max(4.0, primitive.radius)
            painter.setBrush(QBrush(QColor(primitive.color)))
            painter.setPen(QPen(QColor(primitive.outline or "#101d20"), 1))
            painter.drawEllipse(
                QPoint(int(x), int(y)), int(radius), int(radius))
            return
        if primitive.kind == "nature":
            radius = max(1.0, primitive.radius * scale)
            painter.setBrush(QBrush(QColor(primitive.color)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                QPoint(int(x), int(y)), int(radius), int(radius))
            return
        if primitive.kind == "overlay":
            if primitive.outline:
                radius = max(1.0, primitive.radius * scale)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(primitive.outline), 1))
                painter.drawEllipse(
                    QPoint(int(x), int(y)), int(radius), int(radius))
            if primitive.width > 0 and primitive.height > 0:
                painter.fillRect(
                    int(x), int(y),
                    max(1, int(primitive.width * scale)),
                    max(1, int(primitive.height * scale)),
                    QColor(primitive.color))
            return

    # -- reporting --------------------------------------------------------

    @property
    def zoom_label(self) -> str:
        """The zoom level the map is at."""
        return zoom_level_label(self._viewport.radius)

    def zoom_to_level(self, radius: float) -> None:
        """Move to one of the offered zoom levels."""
        level = nearest_zoom_level(radius)
        self._viewport = Viewport(
            center_x=self._viewport.center_x, center_y=self._viewport.center_y,
            radius=level, surface=self._viewport.surface)
        self._last_key = None
        self.viewportChanged.emit(self._viewport)
        self.update()

    def stats(self) -> dict[str, Any]:
        """Return the widget's own counters for the diagnostics panel."""
        return {
            "painted": self._painted,
            "skipped": self._skipped,
            "primitives": len(self._scene.primitives) if self._scene else 0,
            "raster_chunks": len(self._raster_images),
            "zoom": self.zoom_label,
            "surface": self._viewport.surface,
            "partial": bool(self._scene.partial) if self._scene else False,
        }

    def visible_chunks(self, limit: int = 64) -> list[tuple[int, int]]:
        """Return the chunks the map currently shows.

        The list is bounded and nearest-first, so an observer that asks
        for them never receives an unbounded request and always receives
        the part of the factory the user is looking at.
        """
        return self._viewport.visible_chunks(
            max(1, self.width()), max(1, self.height()), limit=limit)


__all__ = ["DRAW_ORDER", "ZOOM_STEP", "MapWidget"]
