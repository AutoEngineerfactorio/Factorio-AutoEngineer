"""Bounded local display frames; isolated from gameplay approval and dispatch."""

import asyncio
import json
import math
import re
import time

PREFIX = "@AUTOENGINEER_VIEW "


def point(value):
    if not isinstance(value, dict) or any(
        type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) or abs(value[k]) > 1e7
        for k in ("x", "y")
    ):
        raise ValueError("Invalid display position")
    return {k: value[k] for k in ("x", "y")}


def snapshot(raw):
    if not isinstance(raw, dict) or raw.get("status") != "ok":
        raise ValueError("Display unavailable")
    data = {"position": point(raw)}
    if type(raw.get("tick")) is not int or raw["tick"] < 0:
        raise ValueError("Invalid display tick")
    if not isinstance(raw.get("surface"), str) or len(raw["surface"]) > 128:
        raise ValueError("Invalid display surface")
    data.update(tick=raw["tick"], surface=raw["surface"])
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

    def cell(v):
        p = point(v)
        if not all(
            origin[k] <= p[k] < origin[k] + (256 if t["step"] in (1, 4) else 64) for k in ("x", "y")
        ):
            raise ValueError("Map data outside observed window")
        return dict(p, name=label(v.get("name")))

    raster = {}
    if t["step"] == 1:
        rows = bounded_list(t.get("rows"), 256)
        palette = bounded_list(t.get("palette"), 256)
        if (
            len(rows) != 256
            or not palette
            or any(
                not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in palette
            )
        ):
            raise ValueError("Invalid map raster")
        for row in rows:
            if (
                not isinstance(row, str)
                or len(row) != 512
                or not re.fullmatch("[0-9a-fA-F]{512}", row)
                or any(i >= len(palette) for i in bytes.fromhex(row))
            ):
                raise ValueError("Invalid map row")
        raster = dict(rows=rows, palette=palette)
    tiles = []
    for v in bounded_list(t.get("tiles", []), 4096 if t["step"] == 4 else 1024):
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
        entities.append(dict(e, kind=v["kind"]))
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
            **raster,
            **overlay_details(
                dict(raw, overlays=t["overlays"]) if "overlays" in t else raw, origin
            ),
        ),
        slots=slots,
        capacity=capacity,
        slots_truncated=raw["slots_truncated"],
    )


def overlay_details(raw, origin):
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
    out = dict(schema=1, available={}, partial={}, player_name=label(value.get("player_name")))

    def pos(v):
        p = point(v)
        if not all(origin[k] <= p[k] < origin[k] + 256 for k in ("x", "y")):
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
                    p[k] + p[size] > origin[k] + 256
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
    def __init__(self):
        self.features = {
            "visited": [],
            "failed": [],
            "resources": [],
            "objective": None,
            "proposal": None,
        }
        self.resource_recorded = None

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
        print(
            PREFIX
            + json.dumps(
                {"schema": 1, "status": "ok", **data}, separators=(",", ":"), allow_nan=False
            ),
            flush=True,
        )

    async def poll(self, session, control, interval=1):
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


def parse_frame(line):
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
    clean = snapshot(dict(data, **position))
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
    return clean
