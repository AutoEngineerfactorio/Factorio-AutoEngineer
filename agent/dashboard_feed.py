"""Bounded local display frames; isolated from gameplay approval and dispatch."""

import asyncio
import json
import math
import re
import time
from typing import Any

from dashboard_chunk_cache import ChunkCache
from dashboard_chunk_map import merge_chunks

PREFIX = "@AUTOENGINEER_VIEW "

VIEWPORT_PREFIX = "@AUTOENGINEER_VIEWPORT "

COMMAND_HELP = (
    "In-game commands: /autoengineer-status (input guard only; not backend "
    "connection proof); /autoengineer-takeover (explicit human takeover only). "
    "AI Helper mode, backend connection, takeover request, and telemetry "
    "availability are reported separately by the dashboard."
)

MAX_VIEWPORT_CHUNKS = 64
"""Upper bound on the chunks one viewport request may ask for."""


def command_help() -> str:
    """Return stable user help without claiming backend connectivity."""
    return COMMAND_HELP


def encode_viewport_request(center_x, center_y, radius_x, radius_y) -> str:
    """Encode a viewport request for the observer process.

    The view sends the world rectangle it currently shows. The observer turns
    that into a bounded list of chunk indices on the aligned 64-tile grid and
    observes only those chunks.

    The request is advisory: it asks for a read-only observation of an area
    and never asks the game to change anything.
    """
    for value in (center_x, center_y, radius_x, radius_y):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Invalid viewport bounds")
        if abs(value) > 1e7:
            raise ValueError("Viewport bounds out of range")
    if radius_x < 0 or radius_y < 0:
        raise ValueError("Viewport radius must not be negative")
    return VIEWPORT_PREFIX + json.dumps(
        {
            "schema": 1,
            "center": {"x": center_x, "y": center_y},
            "radius": {"x": radius_x, "y": radius_y},
            "limit": MAX_VIEWPORT_CHUNKS,
        },
        separators=(",", ":"),
        allow_nan=False,
    )


def decode_viewport_request(line: str) -> dict[str, Any] | None:
    """Decode a viewport request, or return None when the line is not one.

    A malformed request is rejected rather than partially applied, so the
    observer keeps using its previous viewport instead of guessing.
    """
    if not isinstance(line, str) or not line.startswith(VIEWPORT_PREFIX):
        return None
    payload = line[len(VIEWPORT_PREFIX) :].strip()
    if not payload or len(payload) > 4096:
        raise ValueError("Invalid viewport request")
    data = json.loads(payload)
    if not isinstance(data, dict) or set(data) != {"schema", "center", "radius", "limit"}:
        raise ValueError("Invalid viewport request")
    if type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("Unsupported viewport request schema")
    limit = data["limit"]
    if type(limit) is not int or not 1 <= limit <= MAX_VIEWPORT_CHUNKS:
        raise ValueError("Invalid viewport chunk limit")
    for name in ("center", "radius"):
        part = data[name]
        if not isinstance(part, dict) or set(part) != {"x", "y"}:
            raise ValueError("Invalid viewport bounds")
        for key in ("x", "y"):
            value = part[key]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Invalid viewport bounds")
            if abs(value) > 1e7:
                raise ValueError("Viewport bounds out of range")
    if data["radius"]["x"] < 0 or data["radius"]["y"] < 0:
        raise ValueError("Viewport radius must not be negative")
    return data


def point(value):
    if not isinstance(value, dict) or any(
        type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) or abs(value[k]) > 1e7
        for k in ("x", "y")
    ):
        raise ValueError("Invalid display position")
    return {k: value[k] for k in ("x", "y")}


def snapshot(raw) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("status") != "ok":
        raise ValueError("Display unavailable")
    data: dict[str, Any] = {"position": point(raw)}
    if type(raw.get("tick")) is not int or raw["tick"] < 0:
        raise ValueError("Invalid display tick")
    if not isinstance(raw.get("surface"), str) or len(raw["surface"]) > 128:
        raise ValueError("Invalid display surface")
    data.update(tick=raw["tick"], surface=raw["surface"])
    from production_telemetry import validate_telemetry

    data["telemetry"] = validate_telemetry(raw.get("telemetry"), raw["tick"])
    items = raw.get("inventory")
    if items == {}:
        items = []  # Factorio encodes an empty Lua table as {}.
    if not isinstance(items, list) or len(items) > 64:
        raise ValueError("Invalid inventory display")
    data["inventory"] = []
    for item in items:
        if (
            not isinstance(item, dict)
            or any(
                not isinstance(item.get(k), str) or not 1 <= len(item[k]) <= 128
                for k in ("name", "quality")
            )
            or type(item.get("count")) is not int
            or not 0 <= item["count"] <= 10**12
        ):
            raise ValueError("Invalid inventory item")
        data["inventory"].append({k: item[k] for k in ("name", "quality", "count")})
    for key in ("inventory_available", "truncated"):
        if type(raw.get(key)) is not bool:
            raise ValueError("Invalid inventory state")
        data[key] = raw[key]
    if "control" in raw:
        c = raw["control"]
        if (
            not isinstance(c, dict)
            or any(
                type(c.get(k)) is not bool
                for k in ("input_adapter", "character_control", "lease_active", "walking")
            )
            or type(c.get("generation")) is not int
            or not 0 <= c["generation"] <= 2**53
        ):
            raise ValueError("Invalid human control state")
        data["control"] = {
            k: c[k]
            for k in ("input_adapter", "character_control", "lease_active", "walking", "generation")
        }
    # Older policy-8 backends omit this same-tick metadata and remain observation-only.
    capabilities = None
    if "capabilities" in raw:
        from read_only_planning import validate_capabilities

        capabilities = validate_capabilities(
            raw["capabilities"], data["surface"], data["tick"]
        )
        data["capabilities"] = capabilities
    if "catalog_status" in raw:
        status = raw["catalog_status"]
        if (not isinstance(status, dict)
                or set(status) not in (
                    {"page", "page_size", "status"},
                    {"page", "page_size", "status", "total_count", "total_pages"},
                    {"page", "page_size", "status", "total_count", "total_pages", "pages_collected"},
                )
                or type(status.get("page")) is not int or not 1 <= status["page"] <= 10000
                or type(status.get("page_size")) is not int or not 1 <= status["page_size"] <= 32
                or status.get("status") not in (
                    "ok", "assembled", "assembly_failed", "page_out_of_range",
                    "catalog_limit", "unavailable",
                )):
            raise ValueError("Invalid recipe catalog page status")
        normalized = {key: status[key] for key in ("page", "page_size", "status")}
        if "total_count" in status:
            if (type(status["total_count"]) is not int or not 0 <= status["total_count"] <= 10000
                    or type(status["total_pages"]) is not int or not 0 <= status["total_pages"] <= 10000):
                raise ValueError("Invalid recipe catalog counts")
            expected_pages = math.ceil(status["total_count"] / status["page_size"])
            if status["total_pages"] != expected_pages:
                raise ValueError("Inconsistent recipe catalog page count")
            normalized.update(total_count=status["total_count"], total_pages=status["total_pages"])
        if "pages_collected" in status:
            if type(status["pages_collected"]) is not int or not 1 <= status["pages_collected"] <= 10000:
                raise ValueError("Invalid assembled recipe page count")
            normalized["pages_collected"] = status["pages_collected"]
        if status["status"] == "ok" and "total_count" not in normalized:
            raise ValueError("Missing recipe catalog counts")
        if status["status"] == "ok":
            if ((status["total_pages"] == 0 and status["page"] != 1)
                    or (status["total_pages"] > 0 and status["page"] > status["total_pages"])):
                raise ValueError("Successful recipe page is out of range")
            if capabilities is None or len(capabilities["recipes"]) > status["page_size"]:
                raise ValueError("Recipe page missing or exceeds declared size")
            if (not capabilities["truncated"]
                    and status["total_pages"] <= 1
                    and status["total_count"] != len(capabilities["recipes"])):
                raise ValueError("Incomplete recipe page cannot certify completeness")
        elif status["status"] == "assembled":
            expected_pages = max(1, status.get("total_pages", -1))
            if ("total_count" not in normalized or "pages_collected" not in normalized
                    or status["page"] != 1 or status["pages_collected"] != expected_pages
                    or capabilities is None
                    or len(capabilities["recipes"]) > status["total_count"]
                    or (not capabilities["truncated"]
                        and len(capabilities["recipes"]) != status["total_count"])
                    or not capabilities.get("source_fingerprint")):
                raise ValueError("Invalid assembled recipe catalog")
        elif status["status"] == "assembly_failed":
            if capabilities is not None:
                raise ValueError("Failed recipe assembly must not expose catalog data")
        elif status["status"] == "page_out_of_range":
            if ("total_pages" not in normalized
                    or status["page"] <= status["total_pages"]
                    or capabilities is not None):
                raise ValueError("Invalid out-of-range recipe page")
        elif capabilities is not None:
            raise ValueError("Recipe data present without a successful page")
        data["catalog_status"] = normalized
    data.update(display_details(raw))
    return data


def bounded_list(value, maximum):
    if value == {}:
        value = []
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("Display collection exceeds bound")
    return value


def label(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid display name")
    return value


def observed_chart_color(value):
    """Accept only an explicit, bounded observed chart colour.

    The observer reports the colour the game itself charts the entity with,
    as three bytes. Nothing is inferred from the entity name and an absent
    colour stays absent: the map layer then reports "no authoritative colour"
    instead of inventing one.
    """
    if "map_color" not in value:
        return {}
    color = value["map_color"]
    if not isinstance(color, dict) or set(color) != {"r", "g", "b"}:
        raise ValueError("Invalid observed chart color")
    result = {}
    for key in ("r", "g", "b"):
        channel = color[key]
        if type(channel) is not int or not 0 <= channel <= 255:
            raise ValueError("Invalid observed chart color channel")
        result[key] = channel
    return {"map_color": result}


def observed_prototype_identity(value):
    """Accept only the observed entity type, prototype type and variation.

    The graphics variation selects a tree's sprite tint from its prototype's
    own colour palette, so it is part of the observed identity of a natural
    object and is bounded to the 0..255 range Factorio uses.
    """
    result = {}
    for key in ("entity_type", "prototype_type"):
        if key in value:
            name = value[key]
            if not isinstance(name, str) or not 1 <= len(name) <= 64:
                raise ValueError("Invalid observed prototype identity")
            result[key] = name
    if "graphics_variation" in value:
        variation = value["graphics_variation"]
        if type(variation) is not int or not 0 <= variation <= 255:
            raise ValueError("Invalid observed graphics variation")
        result["graphics_variation"] = variation
    return result


def observed_entity_footprint(value):
    """Accept only explicit, bounded geometry; never infer shape from entity name."""
    fields = ("width", "height", "direction", "bounds")
    present = [key for key in fields if key in value]
    result: dict = {}
    result.update(observed_chart_color(value))
    result.update(observed_prototype_identity(value))
    if not present:
        return result
    if ("width" in value) != ("height" in value):
        raise ValueError("Incomplete observed entity footprint")
    for key in ("width", "height"):
        if key in value:
            number = value[key]
            if type(number) not in (int, float) or not math.isfinite(number) or not 0 < number <= 128:
                raise ValueError("Invalid observed entity dimension")
            result[key] = number
    if "bounds" in value:
        bounds = value["bounds"]
        if not isinstance(bounds, dict) or set(bounds) != {"left_top", "right_bottom"}:
            raise ValueError("Invalid observed entity bounds")
        a, b = point(bounds["left_top"]), point(bounds["right_bottom"])
        if any(b[k] <= a[k] or b[k] - a[k] > 128 for k in ("x", "y")):
            raise ValueError("Invalid observed entity bounding rectangle")
        result["bounds"] = {"left_top": a, "right_bottom": b}
    if "direction" in value:
        direction = value["direction"]
        if type(direction) is not int or not 0 <= direction <= 15:
            raise ValueError("Invalid observed entity direction")
        result["direction"] = direction
    return result


def display_details(raw):
    # Old backends remain usable, with an explicit unavailable terrain/slot layer.
    if "terrain" not in raw:
        return {}
    t = raw["terrain"]
    if (
        not isinstance(t, dict)
        or t.get("step") not in (1, 2, 4)
        or type(t.get("step")) is not int
        or type(t.get("partial")) is not bool
    ):
        raise ValueError("Invalid terrain frame")
    origin = point(t.get("origin"))
    map_chunk = None
    chunk_complete = None
    if "map_chunk" in t:
        chunk = t["map_chunk"]
        if (
            not isinstance(chunk, dict)
            or set(chunk) != {"x", "y", "size"}
            or type(chunk.get("x")) is not int
            or type(chunk.get("y")) is not int
            or type(chunk.get("size")) is not int
            or chunk["size"] != 64
            or not -100000 <= chunk["x"] <= 100000
            or not -100000 <= chunk["y"] <= 100000
        ):
            raise ValueError("Invalid map chunk metadata")
        map_chunk = dict(chunk)
        # The chunk origin must be the aligned origin of the named chunk.
        # A mismatch would silently misplace terrain and entities.
        if origin["x"] != chunk["x"] * 64 or origin["y"] != chunk["y"] * 64:
            raise ValueError("Map chunk origin is not aligned to its chunk")
    if "chunk_complete" in t:
        if type(t["chunk_complete"]) is not bool:
            raise ValueError("Invalid map chunk completeness flag")
        chunk_complete = t["chunk_complete"]
    # The observed window is the chunk size for chunked frames. Older backends
    # carried no chunk metadata; their window depends on the raster step, so
    # they keep the legacy window and an old backend stays readable.
    window = 64 if map_chunk is not None else (256 if t["step"] in (1, 4) else 64)

    def cell(v):
        p = point(v)
        if not all(
            origin[k] <= p[k] < origin[k] + window for k in ("x", "y")
        ):
            raise ValueError("Map data outside observed window")
        return dict(p, name=label(v.get("name")))

    raster = {}
    if t["step"] == 1:
        rows = bounded_list(t.get("rows"), window)
        palette = bounded_list(t.get("palette"), 256)
        if (
            len(rows) != window
            or not palette
            or any(
                not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in palette
            )
        ):
            raise ValueError("Invalid map raster")
        for row in rows:
            if (
                not isinstance(row, str)
                or len(row) != window * 2
                or not re.fullmatch(f"[0-9a-fA-F]{{{window * 2}}}", row)
                or any(i >= len(palette) for i in bytes.fromhex(row))
            ):
                raise ValueError("Invalid map row")
        raster = dict(rows=rows, palette=palette)
    tiles = []
    for v in bounded_list(t.get("tiles", []), window * window if t["step"] == 4 else 1024):
        tile = cell(v)
        if "color" in v:
            if (
                not isinstance(v["color"], str)
                or not re.fullmatch(r"#[0-9a-fA-F]{6}", v["color"])
                or type(v.get("visible")) is not bool
            ):
                raise ValueError("Invalid terrain color or visibility")
            tile.update(color=v["color"], visible=v["visible"])
        tiles.append(tile)
    entities = []
    for v in bounded_list(t.get("entities"), 2944):
        e = cell(v)
        if v.get("kind") not in ("resource", "nature", "building", "enemy"):
            raise ValueError("Invalid entity layer")
        entities.append(dict(e, kind=v["kind"], **observed_entity_footprint(v)))
    capacity = raw.get("capacity")
    if (
        type(capacity) is not int
        or not 0 <= capacity <= 2000
        or type(raw.get("slots_truncated")) is not bool
    ):
        raise ValueError("Invalid inventory capacity")
    slots = []
    seen = set()
    for v in bounded_list(raw.get("slots"), 200):
        i = v.get("slot")
        if type(i) is not int or not 1 <= i <= min(capacity, 200) or i in seen:
            raise ValueError("Invalid inventory slot")
        seen.add(i)
        if type(v.get("count")) is not int or not 1 <= v["count"] <= 10**12:
            raise ValueError("Invalid stack count")
        slots.append(
            dict(
                slot=i, name=label(v.get("name")), quality=label(v.get("quality")), count=v["count"]
            )
        )
    return dict(
        terrain=dict(
            origin=origin,
            step=t["step"],
            tiles=tiles,
            entities=entities,
            partial=t["partial"],
            **({"map_chunk": map_chunk} if map_chunk is not None else {}),
            **({"chunk_complete": chunk_complete} if chunk_complete is not None else {}),
            **raster,
            **overlay_details(
                dict(raw, overlays=t["overlays"]) if "overlays" in t else raw, origin, window
            ),
        ),
        slots=slots,
        capacity=capacity,
        slots_truncated=raw["slots_truncated"],
    )


def overlay_details(raw, origin, window=256):
    """Validate optional overlays on both sides of the display process boundary."""
    if "overlays" not in raw:
        return {}
    value = raw["overlays"]
    names = {
        "pollution": 81,
        "electric": 128,
        "logistics": 64,
        "turrets": 128,
        "stations": 128,
        "tags": 128,
    }
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise ValueError("Invalid overlay schema")
    out: dict[str, Any] = dict(schema=1, available={}, partial={}, player_name=label(value.get("player_name")))

    def pos(v):
        p = point(v)
        if not all(origin[k] <= p[k] < origin[k] + window for k in ("x", "y")):
            raise ValueError("Overlay outside chart window")
        return p

    def number(v, key, maximum):
        n = v.get(key)
        if type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= maximum:
            raise ValueError("Invalid overlay value")
        return n

    def text(v):
        if v == "":
            return ""
        return label(v)

    for name, limit in names.items():
        for flag in ("available", "partial"):
            flags = value.get(flag)
            if not isinstance(flags, dict) or type(flags.get(name)) is not bool:
                raise ValueError("Invalid overlay availability")
            out[flag][name] = flags[name]
        entries = bounded_list(value.get(name), limit)
        if not out["available"][name] and entries:
            raise ValueError("Unavailable overlay has data")
        out[name] = []
        for v in entries:
            p = pos(v)
            if name == "pollution":
                p.update(
                    value=number(v, "value", 1e15),
                    width=number(v, "width", 32),
                    height=number(v, "height", 32),
                )
                if any(
                    p[k] + p[size] > origin[k] + window
                    for k, size in [("x", "width"), ("y", "height")]
                ):
                    raise ValueError("Pollution cell outside window")
            elif name in ("electric", "turrets"):
                p["radius"] = number(v, "radius", 2048)
                if name == "electric":
                    p["connections"] = [pos(q) for q in bounded_list(v.get("connections"), 16)]
            elif name == "logistics":
                p.update(
                    logistic=number(v, "logistic", 2048),
                    construction=number(v, "construction", 2048),
                )
                if type(v.get("active")) is not bool:
                    raise ValueError("Invalid logistics state")
                p["active"] = v["active"]
            else:
                p["text"] = text(v.get("text"))
                if name == "tags":
                    p["icon"] = text(v.get("icon"))
            out[name].append(p)
    return {"overlays": out}


class DashboardFeed:
    def __init__(self, cache=None):
        self.features: dict[str, Any] = {
            "visited": [],
            "failed": [],
            "resources": [],
            "objective": None,
            "proposal": None,
        }
        self.resource_recorded = None
        # The cache owns every observed chunk. The live frame keeps the
        # inventory, telemetry and control state; the map comes from the
        # cache so a panned or zoomed viewport can show chunks that were
        # observed earlier.
        self.cache = cache if cache is not None else ChunkCache()
        self.surface = None

    def update(self, resources, memory=None, objective=None, proposal=None):
        self.resource_recorded = time.monotonic() - resources.get("age_seconds", 0)
        self.features["resources"] = [
            {"name": r["name"][:128], "x": r["center_x"], "y": r["center_y"]}
            for r in resources.get("resources", [])[:16]
        ]
        if memory is not None:
            self.features["visited"] = [point(p) for p in memory.data["visited"][-64:]]
            self.features["failed"] = [point(p) for p in memory.data["failed"][-64:]]
        self.features["objective"] = point(objective) if objective is not None else None
        self.features["proposal"] = (
            point(proposal)
            if isinstance(proposal, dict) and proposal.get("action") == "walk"
            else None
        )

    def publish(self, raw):
        data = snapshot(raw)
        data.update(self.features)
        data["resource_age_seconds"] = (
            max(0, time.monotonic() - self.resource_recorded)
            if self.resource_recorded is not None
            else None
        )
        data["map"] = self.remember(raw, data)
        print(
            PREFIX
            + json.dumps(
                {"schema": 1, "status": "ok", **data}, separators=(",", ":"), allow_nan=False
            ),
            flush=True,
        )

    def remember(self, raw, data=None) -> dict[str, Any]:
        """Store the observed chunk and return the merged map description.

        A frame that carries no chunk metadata comes from an older backend and
        is returned unchanged so the dashboard keeps working, but it is never
        merged into the chunk cache.
        """
        surface = (data or raw).get("surface")
        if isinstance(surface, str) and surface != self.surface:
            # A different surface isolates the cache completely.
            self.surface = surface
            self.cache.set_surface(surface)
        terrain = raw.get("terrain") if isinstance(raw, dict) else None
        if isinstance(terrain, dict) and isinstance(terrain.get("map_chunk"), dict):
            tick = raw.get("tick")
            if type(tick) is int:
                try:
                    self.cache.store(terrain, tick=tick)
                except ValueError:
                    # A malformed chunk frame must not take the whole frame
                    # down; the map keeps the chunks that were stored before.
                    pass
        return self.merged_map()

    def merged_map(self) -> dict[str, Any]:
        """Return the merged map for every cached chunk."""
        records = self.cache.records()
        merged = merge_chunks(self.cache, records)
        merged["stats"] = self.cache.stats()
        return merged

    async def poll(self, session, control, interval: float = 1):
        surface = None
        while not control.stop.is_set():
            try:
                response = await asyncio.wait_for(
                    session.call_tool("autoengineer_view"), timeout=1.5
                )
                if response.is_error:
                    raise ValueError("Display read failed")
                raw = next(json.loads(p.text) for p in response.content if p.type == "text")
                data = snapshot(raw)
                if surface is not None and surface != data["surface"]:
                    control.stop.set()
                    raise ValueError("Surface changed during session")
                surface = data["surface"]
                self.publish(raw)
            except Exception:
                print(PREFIX + '{"schema":1,"status":"unavailable"}', flush=True)
            await asyncio.sleep(interval)

    async def run(self, session, control, work):
        task = asyncio.create_task(self.poll(session, control))
        try:
            return await work()
        finally:
            task.cancel()
            # Display cleanup cannot delay the surrounding game-side stop.
            task.add_done_callback(lambda t: None if t.cancelled() else t.exception())


def parse_frame(line: str) -> dict[str, Any] | None:
    if not line.startswith(PREFIX):
        return None
    if len(line) > 1048576:
        raise ValueError("Display frame too large")
    data = json.loads(line[len(PREFIX) :])
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Invalid display frame")
    if data.get("status") == "unavailable":
        return {"status": "unavailable"}
    # Validate backend fields again across the child-process boundary.
    position = point(data.get("position"))
    clean: dict[str, Any] = snapshot(dict(data, **position))
    for name, limit in [("visited", 64), ("failed", 64), ("resources", 16)]:
        values = data.get(name)
        if not isinstance(values, list) or len(values) > limit:
            raise ValueError("Invalid map markers")
        clean[name] = []
        for value in values:
            marker = point(value)
            if name == "resources":
                if not isinstance(value.get("name"), str) or len(value["name"]) > 128:
                    raise ValueError("Invalid marker label")
                marker["name"] = value["name"]
            clean[name].append(marker)
    for key in ("objective", "proposal"):
        clean[key] = point(data[key]) if data.get(key) is not None else None
    clean["status"] = "ok"
    age = data.get("resource_age_seconds")
    if age is not None and (type(age) not in (int, float) or not math.isfinite(age) or age < 0):
        raise ValueError("Invalid resource age")
    clean["resource_age_seconds"] = age
    clean["map"] = map_details(data.get("map"))
    return clean


def map_details(value):
    """Validate the merged map that the observer publishes.

    The map carries only what was observed. An absent map is an older
    observer and stays absent rather than being faked.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Invalid map payload")
    entities = []
    for entity in bounded_list(value.get("entities", []), 20000):
        if not isinstance(entity, dict) or entity.get("kind") not in (
            "resource", "nature", "building", "enemy",
        ):
            raise ValueError("Invalid map entity")
        entities.append(dict(entity))
    origins = []
    for origin in bounded_list(value.get("origins", []), 256):
        if (
            not isinstance(origin, (list, tuple))
            or len(origin) != 2
            or any(type(value) is not int for value in origin)
        ):
            raise ValueError("Invalid map chunk origin")
        origins.append((origin[0], origin[1]))
    tiles = []
    for tile in bounded_list(value.get("tiles", []), 20000):
        if not isinstance(tile, dict):
            raise ValueError("Invalid map tile")
        tiles.append(dict(tile))
    rasters = []
    for raster in bounded_list(value.get("rasters", []), 64):
        if not isinstance(raster, dict):
            raise ValueError("Invalid merged raster")
        origin = point(raster.get("origin"))
        if origin["x"] % 64 or origin["y"] % 64:
            raise ValueError("Unaligned merged raster")
        rows = bounded_list(raster.get("rows"), 64)
        palette = bounded_list(raster.get("palette"), 256)
        if len(rows) != 64 or not palette or any(
            not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c)
            for c in palette
        ):
            raise ValueError("Invalid merged raster palette")
        for row in rows:
            if not isinstance(row, str) or len(row) != 128 or not re.fullmatch(r"[0-9a-fA-F]{128}", row):
                raise ValueError("Invalid merged raster row")
            if any(index >= len(palette) for index in bytes.fromhex(row)):
                raise ValueError("Merged raster index out of range")
        rasters.append({"origin": origin, "rows": rows, "palette": palette})
    partial = value.get("partial")
    if type(partial) is not bool:
        raise ValueError("Invalid map partial flag")
    return {
        "surface": value.get("surface"),
        "origins": origins,
        "entities": entities,
        "tiles": tiles,
        "rasters": rasters,
        "partial": partial,
        "statuses": bounded_list(value.get("statuses", []), 256),
    }
