"""Read-only game-style map and inventory; never dispatches gameplay."""

import math
import time
import tkinter as tk
from tkinter import ttk

from dashboard_chunk_grid import CHUNK_TILES
from dashboard_icons import (
    all_icon_candidates,
    factorio_data_root,
    factorio_mods_root,
    icon_candidates,
    quality_icon_candidates,
)
from dashboard_inventory import (
    COUNT_SHADOW,
    COUNT_TEXT,
    QUALITY_BADGE_SIZE,
    SLOT_EMPTY_EDGE,
    SLOT_EMPTY_FILL,
    SLOT_FILLED_FILL,
    SLOT_HIGHLIGHT,
    SLOT_ICON,
    SLOT_PADDING,
    SLOT_SIZE,
    InventoryLayout,
    Slot,
    build_layout,
    changed_slots,
    inventory_columns,
    layout_fingerprint,
    quality_color,
    tooltip_text,
)
from dashboard_map_layers import (
    resource_patch_color,
    resource_patch_rectangles,
    shade_fog_color,
)
from dashboard_nature_layers import (
    RUNTIME_DEFAULT_CHART_COLOR,
    TREE_MIN_MARKER_PIXELS,
    cliff_shape,
    nature_fingerprint,
    nature_shapes,
    parse_map_color,
    rock_shape,
    tree_shape,
)
from factorio_theme import INSET

__all__ = [
    "DEFAULT_MAP_RADIUS",
    "build_layout",
    "changed_slots",
    "enemy_marker_color",
    "factorio_data_root",
    "icon_candidates",
    "inventory_columns",
    "inventory_fingerprint",
    "layout_fingerprint",
    "quality_color",
    "tooltip_text",
]

DEFAULT_MAP_RADIUS = "128"
"""Default map viewport radius in world tiles.

The map is the primary view, so it opens on a wide area rather than a
close-up patch. A 128-tile radius covers the observed 64x64 chunk grid
around the player, which is the area the observer caches and the area that
holds the currently visible enemies.
"""

ENEMY_MARKER_FALLBACK = "#d93030"
"""Marker colour for an enemy whose prototype chart colour was not observed."""


def enemy_marker_color(entity):
    """Return the colour to draw one observed enemy with.

    Factorio charts an enemy with the prototype's own ``enemy_map_color``.
    The observer reports that colour when the prototype defines one, so the
    observed colour is used when it is available.

    Factorio 2.1.23 returns pure white from the runtime chart-colour
    accessor for every prototype whose real chart colour it does not
    expose there, so white is rejected as "no authoritative colour" rather
    than painted. The fixed threat red is used only when the observer
    reported no usable colour at all.
    """
    if not isinstance(entity, dict):
        return ENEMY_MARKER_FALLBACK
    for key in ("enemy_map_color", "map_color"):
        observed = parse_map_color(entity.get(key))
        if observed is None or observed == RUNTIME_DEFAULT_CHART_COLOR:
            continue
        return observed
    return ENEMY_MARKER_FALLBACK


def viewport_radius(zoom, width, height):
    """1:1 means exactly one screen pixel per world tile (not game sprite parity)."""
    if zoom == "1:1":
        return max(1, min(width, height)) / 2
    return float(zoom)


def map_scale(width, height, radius):
    """Screen pixels per Factorio world tile for an orthographic map."""
    if width <= 0 or height <= 0 or radius <= 0 or not math.isfinite(radius):
        raise ValueError("Invalid map viewport or radius")
    return min(width, height) / (2 * radius)


def project(position, center, width, height, radius):
    scale = map_scale(width, height, radius)
    return width / 2 + (position["x"] - center["x"]) * scale, height / 2 + (
        position["y"] - center["y"]
    ) * scale


def unproject(x, y, center, width, height, radius):
    """Inverse of project; keeps hover/panning on the same world grid."""
    scale = map_scale(width, height, radius)
    return {
        "x": center["x"] + (x - width / 2) / scale,
        "y": center["y"] + (y - height / 2) / scale,
    }


def entity_screen_bounds(entity, x, y, pixels_per_tile):
    """Return observed axis-aligned footprint, or None if dimensions are absent.

    Direction is retained by the feed but not used to rotate arbitrary shapes:
    only an actual observed footprint may be represented at scale.
    """
    if "bounds" in entity:
        b = entity["bounds"]
        a, z = b["left_top"], b["right_bottom"]
        return tuple(
            (x if axis == "x" else y) + (point[axis] - entity[axis]) * pixels_per_tile
            for point, axis in ((a, "x"), (a, "y"), (z, "x"), (z, "y"))
        )
    if "width" not in entity or "height" not in entity:
        return None
    half_width = entity["width"] * pixels_per_tile / 2
    half_height = entity["height"] * pixels_per_tile / 2
    return (x - half_width, y - half_height, x + half_width, y + half_height)


def terrain_color(name):
    if "water" in name or "ocean" in name:
        return "#285d78"
    if "lava" in name:
        return "#a54b22"
    if "grass" in name:
        return "#59653b"
    if "sand" in name:
        return "#a79768"
    if "snow" in name or "ice" in name:
        return "#9facb4"
    if "concrete" in name or "stone-path" in name:
        return "#777b76"
    if "out-of-map" in name:
        return "#111416"
    return "#78694e"


def raster_pixels(terrain, center, width, height, radius):
    """Nearest-tile projection; no repeated oversized cell rectangles when zoomed out."""
    scale = min(width, height) / (2 * radius)
    rasters = terrain.get("rasters")
    if rasters:
        chunks = {}
        for raster in rasters:
            ox, oy = raster["origin"]["x"], raster["origin"]["y"]
            chunks[(int(ox) // 64, int(oy) // 64)] = (
                [bytes.fromhex(row) for row in raster["rows"]],
                [bytes.fromhex(color[1:]) for color in raster["palette"]],
            )
        world_xs = [math.floor(center["x"] + (x - width / 2) / scale) for x in range(width)]
        output = []
        cache = {}
        for y in range(height):
            wy = math.floor(center["y"] + (y - height / 2) / scale)
            if wy not in cache:
                pixels = []
                for wx in world_xs:
                    chunk = chunks.get((wx // 64, wy // 64))
                    if chunk is None:
                        pixels.append(b"\x00\x00\x00")
                    else:
                        rows, palette = chunk
                        pixels.append(palette[rows[wy % 64][wx % 64]])
                cache[wy] = b"".join(pixels)
            output.append(cache[wy])
        return b"".join(output)
    ox, oy = terrain["origin"]["x"], terrain["origin"]["y"]
    palette = [bytes.fromhex(c[1:]) for c in terrain["palette"]]
    rows = [bytes.fromhex(row) for row in terrain["rows"]]
    xs = [math.floor(center["x"] + (x - width / 2) / scale) - int(ox) for x in range(width)]
    output = []
    cache = {}
    for y in range(height):
        iy = math.floor(center["y"] + (y - height / 2) / scale) - int(oy)
        if iy not in cache:
            cache[iy] = (
                b"".join(palette[rows[iy][x]] if 0 <= x < 256 else b"\0\0\0" for x in xs)
                if 0 <= iy < 256
                else b"\0\0\0" * width
            )
        output.append(cache[iy])
    return b"".join(output)


def inventory_fingerprint(data, width):
    """Fingerprint only data affecting the slot rendering, not the game tick."""
    if data is None:
        return None
    return layout_fingerprint(build_layout(data, width))


def merged_terrain(data):
    """Return the merged multi-chunk map in the shape the layers expect.

    The map layers already know how to draw observed terrain, resource
    patches, natural objects, buildings and enemies. The merged map keeps
    the exact world coordinates of every observed entity, so the same
    layers draw a multi-chunk map without any new drawing code and
    without inventing anything.

    A frame without a merged map is an older observer and keeps its own
    single-window terrain.
    """
    if not isinstance(data, dict):
        return {}
    merged = data.get("map")
    if not isinstance(merged, dict):
        return data.get("terrain", {})
    entities = merged.get("entities") or []
    origins = merged.get("origins") or []
    if origins:
        min_x = min(origin[0] for origin in origins) * CHUNK_TILES
        min_y = min(origin[1] for origin in origins) * CHUNK_TILES
        max_x = max(origin[0] for origin in origins) * CHUNK_TILES + CHUNK_TILES
        max_y = max(origin[1] for origin in origins) * CHUNK_TILES + CHUNK_TILES
    else:
        min_x = min_y = max_x = max_y = 0
    terrain = dict(data.get("terrain") or {})
    terrain["entities"] = entities
    terrain["rasters"] = merged.get("rasters") or []
    terrain["origin"] = {"x": min_x, "y": min_y}
    terrain["width"] = max_x - min_x
    terrain["height"] = max_y - min_y
    terrain["partial"] = bool(merged.get("partial"))
    return terrain


class LiveView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.last: dict | None = None
        self.received: float | None = None
        self.available = False
        self.offset = {"x": 0, "y": 0}
        self.drag: tuple[int, int, dict] | None = None
        self.icons: dict[str, tk.PhotoImage | None] = {}
        self.quality_icons: dict[str, tk.PhotoImage | None] = {}
        self.slot_hits: dict[int, tuple[int, int, str]] = {}
        self.slot_nodes: dict[int, list[int]] = {}
        self._inventory_layout: InventoryLayout | None = None
        self._inventory_fingerprint: tuple | None = None
        self._inventory_status_base = ""
        # Set by the dashboard so the view can ask the observer to observe the
        # chunks it is currently showing. The call is advisory and read-only.
        self.viewport_sender = None
        self._last_viewport_request = None
        self.status = tk.StringVar(value="Connecting live observer (AI can remain stopped)")
        # Map-first default: the viewport shows a wide area so the observed
        # world reads like Factorio's own map instead of a close-up patch.
        # A 128-tile radius covers the whole 64x64 chunk grid the observer
        # caches around the player, including the chunks that hold the
        # currently visible enemies.
        self.zoom = tk.StringVar(value=DEFAULT_MAP_RADIUS)
        ttk.Label(self, textvariable=self.status, style="Muted.TLabel").pack(
            anchor="w", padx=8, pady=4
        )
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8)
        ttk.Label(controls, text="Radius:").pack(side="left")
        zoom = ttk.Combobox(
            controls,
            textvariable=self.zoom,
            values=["1:1", "24", "60", "128", "200", "320"],
            state="readonly",
            width=5,
        )
        zoom.pack(side="left", padx=6)
        zoom.bind("<<ComboboxSelected>>", lambda _: self.draw())
        ttk.Button(controls, text="Follow player", command=self.recenter).pack(side="left")
        ttk.Button(controls, text="−", width=3, command=lambda: self.change_zoom(1.25)).pack(
            side="left", padx=2
        )
        ttk.Button(controls, text="+", width=3, command=lambda: self.change_zoom(0.8)).pack(
            side="left", padx=2
        )
        self.pointer = tk.StringVar(value="Drag to pan · Wheel to zoom · North up")
        self.map_expanded = True
        ttk.Label(controls, textvariable=self.pointer, style="Muted.TLabel").pack(
            side="left", padx=8
        )
        self.expand_button = ttk.Button(controls, text="Expand map", command=self.toggle_map_expanded)
        self.expand_button.pack(side="right", padx=4)
        layers = ttk.Menubutton(controls, text="Map layers ▾")
        layers.pack(side="right")
        menu = tk.Menu(layers, tearoff=False)
        layers.configure(menu=menu)
        self.layers = {}
        for key, label in [
            ("resource", "Resource patches"),
            ("nature", "Trees and rocks"),
            ("building", "Buildings"),
            ("enemy", "Enemies"),
            ("history", "Visited areas and failed targets"),
            ("goals", "Objective and proposed route"),
            ("grid", "Chunk grid"),
            ("player_name", "Player marker label"),
        ]:
            self.layers[key] = tk.BooleanVar(value=key != "grid")
            menu.add_checkbutton(label=label, variable=self.layers[key], command=self.draw)
        menu.add_separator()
        self.overlay_menu = menu
        self.overlay_entries = {}
        for key, label in [
            ("pollution", "Pollution"),
            ("electric", "Electric supply and connections"),
            ("logistics", "Logistics and construction coverage"),
            ("turrets", "Turret nominal range"),
            ("stations", "Train stop names"),
            ("tags", "Map tags"),
        ]:
            self.layers[key] = tk.BooleanVar(value=False)
            menu.add_checkbutton(
                label=label + " — unavailable",
                variable=self.layers[key],
                command=self.draw,
                state="disabled",
            )
            self.overlay_entries[key] = (menu.index("end"), label)
        ttk.Label(
            self,
            text="Local chart window · Visible entities only · Turret circles show nominal range, not combat readiness.",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=8, pady=2)
        body = ttk.Panedwindow(self, orient="horizontal")
        self.map_inventory_panes = body
        body.pack(fill="both", expand=True, padx=8, pady=6)
        map_frame = ttk.Frame(body)
        body.add(map_frame, weight=8)
        # The map is the primary view: the canvas fills the pane it is given
        # instead of asking for a small fixed size.
        self.canvas = tk.Canvas(
            map_frame, background="#111416", highlightthickness=0, width=980, height=660
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: (self.draw(), self.request_viewport()))
        self.canvas.bind("<ButtonPress-1>", self.pan_start)
        self.canvas.bind("<B1-Motion>", self.pan_move)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Motion>", self.map_pointer)
        self.canvas.bind("<Double-Button-1>", lambda _: self.recenter())
        # The inventory is a secondary, compact pane: narrower and shorter
        # than the map, so it never competes with it for attention.
        inventory = ttk.Frame(body, width=300, padding=(6, 2))
        self.inventory_pane = inventory
        # Start map-first, like Factorio's remote view. The Show inventory
        # control restores this pane without losing its live contents.
        self.expand_button.configure(text="Show inventory")
        self.inventory_status = tk.StringVar(value="Player main inventory: waiting")
        ttk.Label(inventory, textvariable=self.inventory_status, style="Section.TLabel").pack(
            anchor="w"
        )
        self.item_hint = tk.StringVar(value="Hover a slot for item and quality · Read-only")
        ttk.Label(
            inventory, textvariable=self.item_hint, wraplength=280, style="Muted.TLabel"
        ).pack(anchor="w", pady=4)
        self.items = tk.Canvas(inventory, background=INSET, highlightthickness=0, width=286)
        self.items.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(inventory, orient="vertical", command=self.items.yview)
        scroll.pack(side="right", fill="y")
        self.items.configure(yscrollcommand=scroll.set)
        self.items.bind("<Configure>", lambda _: self.inventory())
        self.items.bind("<Motion>", self.hover)
        self.items.bind(
            "<MouseWheel>", lambda e: self.items.yview_scroll(-1 if e.delta > 0 else 1, "units")
        )
        self.icon_root = factorio_data_root()
        self.mods_root = factorio_mods_root()

    def toggle_map_expanded(self):
        """Offer full-width map without discarding the live inventory data."""
        if self.map_expanded:
            self.map_inventory_panes.add(self.inventory_pane, weight=1)
            self.map_expanded = False
            self.expand_button.configure(text="Expand map")
        else:
            self.map_inventory_panes.forget(self.inventory_pane)
            self.map_expanded = True
            self.expand_button.configure(text="Show inventory")
        self.draw()

    def recenter(self):
        self.offset = {"x": 0, "y": 0}
        self.request_viewport()
        self.draw()

    def viewport_bounds(self):
        """Return the world rectangle the map currently shows."""
        if self.last is None:
            return None
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 0 or height <= 0:
            return None
        player = self.last["position"]
        center = {k: player[k] + self.offset[k] for k in ("x", "y")}
        radius = viewport_radius(self.zoom.get(), width, height)
        scale = min(width, height) / (2 * radius)
        return {
            "center": center,
            "radius": {"x": width / (2 * scale), "y": height / (2 * scale)},
        }

    def request_viewport(self):
        """Ask the observer to observe the chunks this viewport shows.

        The request only names a world rectangle. It never asks the game to
        change anything, and it is skipped when the rectangle has not moved.
        """
        sender = self.viewport_sender
        if sender is None:
            return
        bounds = self.viewport_bounds()
        if bounds is None:
            return
        key = (
            round(bounds["center"]["x"], 1),
            round(bounds["center"]["y"], 1),
            round(bounds["radius"]["x"], 1),
            round(bounds["radius"]["y"], 1),
        )
        if key == self._last_viewport_request:
            return
        self._last_viewport_request = key
        try:
            sender(bounds["center"]["x"], bounds["center"]["y"],
                   bounds["radius"]["x"], bounds["radius"]["y"])
        except Exception:
            # A failed request must not break the map; the observer keeps
            # serving the chunks it already has.
            self._last_viewport_request = None

    def pan_start(self, e):
        self.drag = (e.x, e.y, dict(self.offset))

    def pan_move(self, e):
        if self.drag is None:
            return
        x, y, old = self.drag
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale = map_scale(width, height, viewport_radius(self.zoom.get(), width, height))
        # No arbitrary 128-tile clamp: the viewport can follow any observed surface.
        self.offset = {
            k: old[k] - delta / scale
            for k, delta in [("x", e.x - x), ("y", e.y - y)]
        }
        self.request_viewport()
        self.draw()

    def change_zoom(self, factor):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        radius = viewport_radius(self.zoom.get(), width, height)
        self.zoom.set(str(max(8, min(200, round(radius * factor, 1)))))
        self.request_viewport()
        self.draw()

    def wheel(self, e):
        self.change_zoom(0.8 if e.delta > 0 else 1.25)

    def map_pointer(self, e):
        if self.last is None:
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width <= 0 or height <= 0:
            return
        player = self.last["position"]
        center = {k: player[k] + self.offset[k] for k in ("x", "y")}
        p = unproject(e.x, e.y, center, width, height, viewport_radius(self.zoom.get(), width, height))
        self.pointer.set(
            f"Tile {math.floor(p['x'])}, {math.floor(p['y'])} "
            f"· position {p['x']:.2f}, {p['y']:.2f} · Drag to pan"
        )

    def reset(self):
        self.last = None
        self.received = None
        self.available = False
        self.offset = {"x": 0, "y": 0}
        self.status.set("Waiting for live data")
        self.inventory_status.set("Player main inventory: waiting")
        self.items.delete("all")
        self.slot_hits = {}
        self.slot_nodes = {}
        self._inventory_layout = None
        self._inventory_fingerprint = None
        self._inventory_status_base = ""
        self.draw()

    def icon(self, name) -> tk.PhotoImage | None:
        if name in self.icons:
            return self.icons[name]
        result: tk.PhotoImage | None = None
        # Prototype names are labels, never arbitrary paths from telemetry.
        for path in all_icon_candidates(self.icon_root, self.mods_root, name):
                if path.is_file():
                    try:
                        source = tk.PhotoImage(file=str(path))
                        # Factorio PNGs are a horizontal mipmap strip; crop the 1x frame.
                        edge = min(source.width(), source.height())
                        square = tk.PhotoImage(width=edge, height=edge)
                        square.tk.call(str(square), "copy", str(source), "-from", 0, 0, edge, edge)
                        result = square.subsample(max(1, math.ceil(edge / SLOT_ICON)))
                    except tk.TclError:
                        pass
                    break
        self.icons[name] = result
        return result

    def draw_slot_frame(self, slot):
        """Draw the Factorio-style recessed frame of one slot."""
        x, y = slot.x, slot.y
        edge = SLOT_SIZE - 4
        filled = not slot.empty
        nodes = [
            self.items.create_rectangle(
                x, y, x + edge, y + edge,
                fill=SLOT_FILLED_FILL if filled else SLOT_EMPTY_FILL,
                outline=SLOT_EMPTY_EDGE, width=2,
            )
        ]
        # Dark top and left edges, light bottom and right edges: a recessed well.
        nodes.append(self.items.create_line(x + 2, y + 2, x + edge - 2, y + 2,
                                           fill="#252b20", width=2))
        nodes.append(self.items.create_line(x + 2, y + 2, x + 2, y + edge - 2,
                                           fill="#252b20", width=2))
        nodes.append(self.items.create_line(x + 2, y + edge - 1, x + edge - 1, y + edge - 1,
                                           fill=SLOT_HIGHLIGHT))
        nodes.append(self.items.create_line(x + edge - 1, y + 2, x + edge - 1, y + edge - 1,
                                           fill=SLOT_HIGHLIGHT))
        return nodes

    def quality_badge(self, quality) -> tk.PhotoImage | None:
        """Load the game's own quality badge icon, cached per tier."""
        if quality in self.quality_icons:
            return self.quality_icons[quality]
        image: tk.PhotoImage | None = None
        for path in quality_icon_candidates(self.icon_root, quality):
            if path.is_file():
                try:
                    source = tk.PhotoImage(file=str(path))
                    edge = min(source.width(), source.height())
                    square = tk.PhotoImage(width=edge, height=edge)
                    square.tk.call(str(square), "copy", str(source), "-from", 0, 0, edge, edge)
                    image = square.subsample(
                        max(1, math.ceil(edge / QUALITY_BADGE_SIZE))
                    )
                except tk.TclError:
                    image = None
                break
        self.quality_icons[quality] = image
        return image

    def draw_slot_quality(self, slot):
        """Draw the quality indicator: a coloured border around the slot."""
        quality = slot.quality or "normal"
        if quality == "normal":
            return []
        color = quality_color(quality)
        x, y = slot.x, slot.y
        edge = SLOT_SIZE - 4
        nodes = [
            self.items.create_rectangle(
                x + 1, y + 1, x + edge - 1, y + edge - 1,
                outline=color, width=2,
            )
        ]
        badge = self.quality_badge(quality)
        if badge is not None:
            nodes.append(self.items.create_image(
                x + 3, y + 3, image=badge, anchor="nw"
            ))
        else:
            nodes.append(self.items.create_rectangle(
                x + 3, y + 3, x + 12, y + 12, fill=color, outline=""
            ))
            nodes.append(self.items.create_text(
                x + 7.5, y + 7.5, text=quality[0].upper(),
                fill="#11140d", font=("Segoe UI", 6, "bold"),
            ))
        return nodes

    def draw_slot_contents(self, slot):
        """Draw the icon and the item count of one slot."""
        if slot.empty or slot.name is None:
            return []
        nodes = []
        image = self.icon(slot.name)
        if image:
            nodes.append(self.items.create_image(
                slot.x + SLOT_SIZE / 2 - 2, slot.y + SLOT_SIZE / 2 - 2,
                image=image, anchor="center",
            ))
        else:
            # Missing icon: show the prototype name so the slot is still legible.
            nodes.append(self.items.create_text(
                slot.x + SLOT_SIZE / 2 - 2, slot.y + SLOT_SIZE / 2 - 3,
                text="\n".join(slot.name.split("-")[:2]),
                fill="#e0dfd3", font=("Segoe UI", 7), width=SLOT_SIZE - 8,
            ))
        count = str(slot.count if slot.count is not None else 0)
        # Dark shadow first, bright text on top: the count stays readable.
        nodes.append(self.items.create_text(
            slot.x + SLOT_SIZE - 7, slot.y + SLOT_SIZE - 6,
            anchor="se", text=count, fill=COUNT_SHADOW,
            font=("Segoe UI", 9, "bold"),
        ))
        nodes.append(self.items.create_text(
            slot.x + SLOT_SIZE - 8, slot.y + SLOT_SIZE - 7,
            anchor="se", text=count, fill=COUNT_TEXT,
            font=("Segoe UI", 9, "bold"),
        ))
        return nodes

    def redraw_slot(self, slot):
        """Replace the canvas items of one slot with a fresh rendering."""
        for item in self.slot_nodes.pop(slot.index, ()):
            self.items.delete(item)
        nodes = self.draw_slot_frame(slot)
        nodes += self.draw_slot_contents(slot)
        nodes += self.draw_slot_quality(slot)
        self.slot_nodes[slot.index] = nodes
        self.slot_hits[slot.index] = (slot.x, slot.y, tooltip_text(slot))

    def clear_slot(self, index):
        """Remove one slot from the canvas."""
        for item in self.slot_nodes.pop(index, ()):
            self.items.delete(item)
        self.slot_hits.pop(index, None)

    def inventory(self):
        """Render the inventory, updating only the slots that changed."""
        width = self.items.winfo_width()
        layout = build_layout(self.last, width)
        current = layout_fingerprint(layout)
        if current == self._inventory_fingerprint:
            return
        previous = self._inventory_layout
        self._inventory_fingerprint = current
        self._inventory_layout = layout

        if self.last is None or not self.last.get("inventory_available"):
            for index in list(self.slot_nodes):
                self.clear_slot(index)
            self.items.configure(scrollregion=(0, 0, 0, 0))
            self.inventory_status.set("Main inventory unavailable")
            return

        status = f"Player main inventory - {layout.capacity} slots"
        if layout.partial:
            status += " - partial"
        if not layout.actual:
            status += " - aggregate fallback (not real slot positions)"
        self._inventory_status_base = status
        self.inventory_status.set(status + self._stale_suffix())

        changed, removed = changed_slots(
            previous.slots if previous is not None else (), layout.slots
        )
        by_index = {slot.index: slot for slot in layout.slots}

        # A resize or a change of provenance moves every slot: redraw it all.
        geometry_changed = previous is None or (
            previous.columns != layout.columns
            or previous.actual != layout.actual
        )
        if geometry_changed:
            for index in list(self.slot_nodes):
                self.clear_slot(index)
            changed = {slot.index for slot in layout.slots}
        for index in removed:
            self.clear_slot(index)
        for index in changed:
            slot = by_index.get(index)
            if slot is not None:
                self.redraw_slot(slot)

        # Empty slots stay visible as recessed wells so the grid keeps its shape.
        for index in range(1, layout.capacity + 1):
            if index not in by_index and index not in self.slot_nodes:
                column = (index - 1) % layout.columns
                row = (index - 1) // layout.columns
                self.redraw_slot(Slot(
                    index=index,
                    x=column * SLOT_SIZE + SLOT_PADDING,
                    y=row * SLOT_SIZE + SLOT_PADDING,
                ))

        self.items.configure(
            scrollregion=(0, 0, layout.width, layout.height)
        )

    def hover(self, e):
        y = self.items.canvasy(e.y)
        for x0, y0, hint in self.slot_hits.values():
            if x0 <= e.x < x0 + SLOT_SIZE - 4 and y0 <= y < y0 + SLOT_SIZE - 4:
                self.item_hint.set(hint)
                return

    def update_frame(self, data):
        if data["status"] != "ok":
            # The observer dropped out: keep the last known contents but mark
            # the inventory panel as no longer a live reading.
            self.available = False
            base = getattr(self, "_inventory_status_base", "")
            if base and getattr(self, "inventory_status", None) is not None:
                self.inventory_status.set(
                    base + " - STALE (observer disconnected)"
                )
            return
        if self.last is not None and self.last["surface"] != data["surface"]:
            for key in ("visited", "failed", "resources"):
                data[key] = []
            data["objective"] = data["proposal"] = None
            self.offset = {"x": 0, "y": 0}
        overlays = data.get("terrain", {}).get("overlays", {})
        for key, (index, label) in self.overlay_entries.items():
            available = overlays.get("available", {}).get(key, False)
            partial = overlays.get("partial", {}).get(key, False)
            self.overlay_menu.entryconfigure(
                index,
                state="normal" if available else "disabled",
                label=label
                + (" · partial" if partial else "")
                + ("" if available else " — unavailable"),
            )
        self.last = data
        self.received = time.monotonic()
        self.available = True
        self.inventory()
        self.draw()

    def _stale_suffix(self):
        """Suffix that marks the inventory as no longer a live reading."""
        if self.last is None:
            return ""
        if not self.available:
            return " - STALE (observer disconnected)"
        if self.received is None:
            return " - STALE (no reading yet)"
        age = time.monotonic() - self.received
        if age > 3:
            return f" - STALE ({age:.0f}s old)"
        return ""

    def freshness(self, running):
        if self.last is None or self.received is None:
            return
        age = time.monotonic() - self.received
        state = (
            "Live"
            if running and self.available and age <= 3
            else "Stale"
            if running
            else "Session ended; last snapshot"
        )
        partial = " · partial entities" if self.last.get("terrain", {}).get("partial") else ""
        self.status.set(
            f"{state} | {self.last['surface']} | tick {self.last['tick']} | {age:.1f}s old | charted terrain, live visible entities{partial}"
        )
        # The inventory panel carries its own freshness marker.
        base = getattr(self, "_inventory_status_base", "")
        label = getattr(self, "inventory_status", None)
        if base and label is not None:
            label.set(base + self._stale_suffix())

    def draw_raster(self, terrain, center, width, height, radius):
        key = (
            tuple((r["origin"]["x"], r["origin"]["y"], tuple(r["rows"]), tuple(r["palette"])) for r in terrain.get("rasters", [])),
            tuple(terrain.get("rows", [])),
            tuple(terrain.get("palette", [])),
            tuple(terrain["origin"].values()),
            center["x"],
            center["y"],
            width,
            height,
            radius,
        )
        if getattr(self, "raster_key", None) != key:
            pixels = raster_pixels(terrain, center, width, height, radius)
            self.map_image = tk.PhotoImage(
                data=f"P6 {width} {height} 255\n".encode() + pixels, format="PPM"
            )
            self.raster_key = key
        self.canvas.create_image(0, 0, anchor="nw", image=self.map_image)

    def draw_resource_patches(self, terrain, center, width, height, radius):
        """Paint observed resource deposits as continuous filled patches.

        Only deposits the observer actually reported are drawn. Each patch
        is a filled rectangle with no per-deposit border, so an ore field
        reads as a continuous coloured area like the in-game map.
        """
        entities = terrain.get("entities", [])
        if not entities:
            return
        origin = terrain.get("origin")
        window = None
        if origin:
            window = dict(
                x=origin["x"],
                y=origin["y"],
                width=terrain.get("width", 256),
                height=terrain.get("height", 256),
            )
        for name, rectangles in resource_patch_rectangles(entities, window).items():
            color = resource_patch_color(name)
            for x0, y0, x1, y1 in rectangles:
                left, top = project(
                    {"x": x0, "y": y0}, center, width, height, radius
                )
                right, bottom = project(
                    {"x": x1 + 1, "y": y1 + 1}, center, width, height, radius
                )
                self.canvas.create_rectangle(
                    left,
                    top,
                    right,
                    bottom,
                    fill=color,
                    outline="",
                    tags="resource-patch",
                )

    def draw_nature(self, terrain, center, width, height, radius):
        """Draw observed natural objects the way the in-game map draws them.

        Each natural object uses the prototype map colour the observer
        reported, or a verified Factorio 2.1.23 prototype colour. Trees, rocks
        and cliffs get their own map geometry, and no object gets a black
        selection-box outline: the in-game map has no such border.

        Only observed entities are drawn. Nothing is inferred from a name and
        no colour is invented: an object with no authoritative colour is drawn
        as a small outline-only marker so its position stays truthful.

        The classified shapes are cached per observation so that panning and
        zooming do not re-classify a large forest on every frame. The cache
        is keyed on the observed entity list itself, so a new observation
        invalidates it automatically.
        """
        entities = terrain.get("entities", [])
        if not entities:
            return
        origin = terrain.get("origin")
        window = None
        if origin:
            window = dict(
                x=origin["x"],
                y=origin["y"],
                width=terrain.get("width", 256),
                height=terrain.get("height", 256),
            )
        shapes = self._nature_shape_cache(entities, window)
        scale = map_scale(width, height, radius)
        for shape in shapes:
            x, y = project({"x": shape.x, "y": shape.y}, center, width, height, radius)
            if shape.kind == "tree":
                # A map canopy glyph is wider than a trunk collision box.
                # This adjusts the display glyph only, not observed positions
                # or inferred gameplay footprint, so neighboring crowns blend
                # into the wooded pattern seen on the game's chart.
                #
                # The glyph keeps a minimum pixel size so that a densely
                # wooded region still reads as forest cover at a wide map
                # zoom, where one tile is only a few pixels across. The
                # minimum never adds a tree: only the observed tree at its
                # observed position is drawn, and the glyph is the same dark
                # map green the game uses for a charted tree.
                radius_px = max(
                    TREE_MIN_MARKER_PIXELS,
                    tree_shape(shape) * scale * 0.85,
                )
                # Vanilla chart trees are dark-green marks, not their bright
                # sprite-tint palette. Use the color measured from the live
                # Factorio minimap; retain prototype colors for modded trees.
                chart_color = "#31401b" if shape.name.startswith("tree-") else shape.color
                self._draw_tree(x, y, radius_px, chart_color)
            elif shape.kind == "rock":
                radius_px = rock_shape(shape) * scale / 2
                self._draw_rock(x, y, radius_px, shape.color)
            else:
                radius_px = cliff_shape(shape) * scale / 2
                self._draw_cliff(x, y, radius_px, shape.color)

    def _nature_shape_cache(self, entities, window):
        """Return the classified natural shapes, reusing the last result.

        The cache key is a fingerprint of the observed entity list plus the
        observed window, so it is invalidated automatically when the observer
        reports a new frame and reused while the user only pans or zooms. The
        fingerprint is cheap: it only inspects the nature entities.
        """
        key = (nature_fingerprint(entities), window)
        cached = getattr(self, "_nature_cache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        shapes = nature_shapes(entities, window)
        self._nature_cache = (key, shapes)
        return shapes

    def _draw_tree(self, x, y, radius_px, color):
        """Draw a map tree: a small round canopy, like the in-game map."""
        radius_px = max(1.0, radius_px)
        if color is None:
            # The game's chart does not show selection rings for unknown
            # vegetation. Don't misrepresent missing chart color as a ring.
            return
        self.canvas.create_oval(
            x - radius_px,
            y - radius_px,
            x + radius_px,
            y + radius_px,
            fill=color,
            outline="",
            tags="nature-tree",
        )

    def _draw_rock(self, x, y, radius_px, color):
        """Draw a map rock: a rounded square, like the in-game map."""
        radius_px = max(1.0, radius_px)
        if color is None:
            # No verified chart color: leave this object unpainted rather
            # than inventing an outline absent from the real map.
            return
        self.canvas.create_rectangle(
            x - radius_px,
            y - radius_px,
            x + radius_px,
            y + radius_px,
            fill=color,
            outline="",
            tags="nature-rock",
        )

    def _draw_cliff(self, x, y, radius_px, color):
        """Draw a cliff: a wide bar across its observed footprint."""
        radius_px = max(1.0, radius_px)
        if color is None:
            # Unknown chart colors do not become fabricated selection boxes.
            return
        self.canvas.create_rectangle(
            x - radius_px,
            y - radius_px / 3,
            x + radius_px,
            y + radius_px / 3,
            fill=color,
            outline="",
            tags="nature-cliff",
        )

    def draw(self):
        self.canvas.delete("all")
        if self.last is None:
            self.canvas.create_text(
                15, 15, anchor="nw", fill="white", text="Waiting for observed map data"
            )
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        player = self.last["position"]
        center = {k: player[k] + self.offset[k] for k in ("x", "y")}
        radius = viewport_radius(self.zoom.get(), width, height)

        def loc(p):
            return project(p, center, width, height, radius)

        scale = min(width, height) / (2 * radius)
        terrain = merged_terrain(self.last)
        if terrain.get("rasters") or "rows" in terrain:
            self.draw_raster(terrain, center, width, height, radius)
        for t in terrain.get("tiles", []):
            x, y = loc(t)
            color = t.get("color", terrain_color(t["name"]))
            if t.get("visible") is False:
                # A charted-but-not-visible tile is drawn with the same map
                # shading factor the backend uses for the terrain palette, so
                # both paths agree on how Factorio darkens fogged terrain.
                # An unusable colour is left alone rather than guessed.
                color = shade_fog_color(color) or color
            step = terrain.get("step", 2)
            self.canvas.create_rectangle(
                x, y, x + step * scale + 1, y + step * scale + 1, fill=color, outline=""
            )
        # Layer 2: resource patches. Observed deposits are rasterized into
        # continuous filled tiles, so an ore field reads as one patch like
        # the in-game map instead of outlined individual shapes.
        if self.layers["resource"].get():
            self.draw_resource_patches(terrain, center, width, height, radius)
        # Layer 3: natural objects. Trees, rocks and cliffs are drawn with the
        # prototype map colour the observer reported, using the natural map
        # geometry and without the black selection-box outline.
        if self.layers["nature"].get():
            self.draw_nature(terrain, center, width, height, radius)
        overlays = terrain.get("overlays", {})
        self.canvas.create_rectangle(0, 0, width, height, outline="", tags="overlay-boundary")
        for key in self.overlay_entries:
            if not self.layers[key].get() or not overlays.get("available", {}).get(key):
                continue
            for e in overlays[key]:
                x, y = loc(e)
                if key == "pollution":
                    if e["value"] <= 0:
                        continue
                    red = min(220, 80 + int(25 * math.log1p(e["value"])))
                    self.canvas.create_rectangle(
                        x,
                        y,
                        x + e["width"] * scale,
                        y + e["height"] * scale,
                        fill=f"#{red:02x}3020",
                        outline="",
                        stipple="gray50",
                    )
                elif key == "electric":
                    r = e["radius"] * scale
                    self.canvas.create_rectangle(
                        x - r,
                        y - r,
                        x + r,
                        y + r,
                        outline="#78b8ed",
                        stipple="gray25",
                        fill="#447799",
                    )
                    for q in e["connections"]:
                        tx, ty = loc(q)
                        self.canvas.create_line(x, y, tx, ty, fill="#e0ca5b")
                elif key == "logistics":
                    for field, color in [("construction", "#68b568"), ("logistic", "#db9b42")]:
                        r = e[field] * scale
                        self.canvas.create_rectangle(
                            x - r,
                            y - r,
                            x + r,
                            y + r,
                            outline=color,
                            dash=() if e["active"] else (3, 3),
                        )
                elif key == "turrets":
                    r = e["radius"] * scale
                    self.canvas.create_oval(
                        x - r, y - r, x + r, y + r, outline="#df6672", dash=(3, 3)
                    )
                else:
                    text = e["text"] or e.get("icon") or "(unnamed)"
                    self.canvas.create_rectangle(
                        x - 3, y - 3, x + 3, y + 3, fill="#e8b45b", outline="#1a1b17"
                    )
                    self.canvas.create_text(
                        x + 7,
                        y,
                        anchor="w",
                        text=text,
                        fill="#f4e4b0",
                        font=("Segoe UI", 9, "bold"),
                    )
        for e in terrain.get("entities", []):
            if not self.layers[e["kind"]].get():
                continue
            # Resource deposits are drawn by the resource-patch layer above
            # as continuous filled patches, not as individual outlined
            # shapes. Drawing them here as well would put a dark border
            # around every deposit and make an ore field look like a black
            # checkerboard at normal map zoom.
            if e["kind"] == "resource":
                continue
            x, y = loc(e)
            if not 0 <= x <= width or not 0 <= y <= height:
                continue
            kind = e["kind"]
            size = max(1, scale * 0.7)
            color = {"enemy": "#ed4e42", "building": "#67acc2", "nature": "#34462a"}[kind]
            if kind == "nature":
                # Natural objects are drawn by the nature layer above, with
                # the prototype map colour and the natural map geometry.
                continue
            if kind == "enemy":
                # The observer reports only entities that are currently
                # visible, so an enemy here is a confirmed threat. Factorio
                # charts an enemy with the prototype's own enemy colour, so
                # that colour is used when the observer reported one; the
                # fallback is the dashboard's fixed threat red.
                color = enemy_marker_color(e)
                r = max(5.0, min(11.0, scale * 1.6))
                self.canvas.create_oval(x-r, y-r, x+r, y+r,
                                        fill=color, outline="#ffd9d0",
                                        width=2, tags="enemy-marker")
                # A dark halo keeps the marker readable over a bright ore
                # patch or a pale terrain tile.
                self.canvas.create_oval(x-r-2, y-r-2, x+r+2, y+r+2,
                                        outline="#1a0d0d", width=1,
                                        tags="enemy-marker")
                continue
            bounds = entity_screen_bounds(e, x, y, scale)
            if bounds is not None:
                self.canvas.create_rectangle(
                    *bounds, fill=color, outline="#111416", width=1
                )
            else:
                # A symbol, not an asserted entity footprint, when dimensions
                # are absent from the verified observer frame.
                self.canvas.create_oval(
                    x - size, y - size, x + size, y + size, fill=color, outline=""
                )
        if self.layers["grid"].get():
            for axis in ("x", "y"):
                extent = (width if axis == "x" else height) / (2 * scale)
                start = math.floor((center[axis] - extent) / 32) * 32
                end = math.ceil((center[axis] + extent) / 32) * 32
                for value in range(start, end + 1, 32):
                    p = dict(center)
                    p[axis] = value
                    x, y = loc(p)
                    self.canvas.create_line(
                        x, 0, x, height, fill="#706f54", dash=(2, 4)
                    ) if axis == "x" else self.canvas.create_line(
                        0, y, width, y, fill="#706f54", dash=(2, 4)
                    )
        for key, color in [("visited", "#a9aaa0"), ("failed", "#ff6861")]:
            if not self.layers["history"].get():
                continue
            for p in self.last[key]:
                x, y = loc(p)
                self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, outline=color)
        px, py = loc(player)
        for key, color in [("objective", "#ffda65"), ("proposal", "#ff9c5c")]:
            p = self.last[key]
            if p and self.layers["goals"].get():
                x, y = loc(p)
                self.canvas.create_line(px, py, x, y, fill=color, dash=(4, 4))
                self.canvas.create_rectangle(x - 5, y - 5, x + 5, y + 5, outline=color, width=2)
        self.canvas.create_polygon(
            px, py - 8, px + 6, py + 6, px - 6, py + 6, fill="#5ed7f5", outline="#101d20"
        )
        if self.layers["player_name"].get():
            self.canvas.create_text(
                px + 10,
                py - 10,
                anchor="w",
                text=overlays.get("player_name", "Player"),
                fill="#5ed7f5",
            )
        self.canvas.create_text(
            8,
            height - 8,
            anchor="sw",
            fill="white",
            text=(
                f"Player {player['x']:.2f}, {player['y']:.2f} | N up | "
                "Black: unexplored | Dimmed: charted, not visible | "
                "Full colour + markers: currently visible | Read-only"
            ),
        )
        if not terrain:
            self.canvas.create_text(
                8,
                8,
                anchor="nw",
                fill="#ffda65",
                text="Terrain unavailable: rebuild display backend",
            )
