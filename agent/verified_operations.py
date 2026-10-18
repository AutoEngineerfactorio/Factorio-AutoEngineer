"""User-selected starter batches; fresh approval and independent inventory checks."""

import asyncio
import json
import math
import os

from agent_events import emit
from dashboard_feed import snapshot
from session_safety import StopRequested

SUPPORTED = {
    "mine": {"iron-ore", "copper-ore", "coal", "stone"},
    "craft": {"iron-gear-wheel", "copper-cable"},
}


def validate_operation(value):
    if not isinstance(value, dict) or set(value) != {"kind", "name", "count"}:
        raise ValueError("Select kind, name and count for one starter batch")
    if (
        value["kind"] not in SUPPORTED
        or value["name"] not in SUPPORTED[value["kind"]]
        or type(value["count"]) is not int
        or not 1 <= value["count"] <= 3
    ):
        raise ValueError(
            "Supported: mine iron-ore/copper-ore/coal/stone; craft iron-gear-wheel/copper-cable; count 1..3"
        )
    return dict(value)


def load_operation():
    text = os.environ.get("AUTOENGINEER_OPERATION")
    return validate_operation(json.loads(text)) if text is not None else None


def decode(response):
    if response.is_error:
        raise RuntimeError("Operation tool failed")
    data = next(json.loads(part.text) for part in response.content if part.type == "text")
    if not isinstance(data, dict):
        raise ValueError("Invalid operation result")
    return data


def inventory(data, name):
    data = snapshot(data)
    if not data.get("inventory_available") or data.get("truncated"):
        raise ValueError("Full main inventory observation required")
    entries = data.get("inventory")
    if entries == {}:
        entries = []
    if not isinstance(entries, list):
        raise ValueError("Invalid inventory observation")
    return sum(
        i["count"] for i in entries if i.get("name") == name and i.get("quality") == "normal"
    )


async def run_operation(session, control, owner, operation, feed=None):
    operation = validate_operation(operation)

    async def read(name, arguments=None):
        return decode(await asyncio.wait_for(session.call_tool(name, arguments=arguments or {}), 3))

    preview = await read("autoengineer_operation_preview", operation)
    print("Operation preflight:", preview.get("status"), flush=True)
    if preview.get("status") != "ready":
        return
    if feed is not None:
        from exploration_memory import load_memory

        resources = (
            [
                {
                    "name": operation["name"],
                    "center_x": preview["targetX"],
                    "center_y": preview["targetY"],
                }
            ]
            if operation["kind"] == "mine"
            else []
        )
        feed.update({"resources": resources}, load_memory())
    print("Action proposed:", flush=True)
    print(
        json.dumps(
            dict(
                action=operation["kind"],
                name=operation["name"],
                count=operation["count"],
                reason="User-selected bounded batch",
            ),
            indent=2,
        ),
        flush=True,
    )
    if operation["kind"] == "mine":
        print("Mining target:", preview.get("targetX"), preview.get("targetY"), flush=True)
    emit("operation_proposal", count=operation["count"])
    if hasattr(session, "propose"):
        session.propose("autoengineer_operation", operation, {"preview": preview})
    answer = await control.approve()
    emit("approval", approved=answer == "y")
    if control.stop.is_set():
        raise StopRequested()
    if answer != "y":
        if hasattr(session, "cancel_proposal"):
            session.cancel_proposal()
        print("Operation rejected; no action executed.", flush=True)
        return
    fresh = await read("autoengineer_operation_preview", operation)
    if fresh.get("status") != "ready":
        print("Operation conditions changed; cancelled.", flush=True)
        return
    if math.dist((fresh["x"], fresh["y"]), (preview["x"], preview["y"])) > 0.5 or any(
        fresh.get(k) != preview.get(k)
        for k in ("targetX", "targetY", "product_before", "input_before")
    ):
        print("Operation observations changed; fresh approval required.", flush=True)
        return
    before = await read("autoengineer_view")
    product_before = inventory(before, operation["name"])
    ingredient = "iron-plate" if operation["name"] == "iron-gear-wheel" else "copper-plate"
    input_before = inventory(before, ingredient) if operation["kind"] == "craft" else None
    args = dict(
        operation,
        safetyOwner=owner,
        targetX=fresh.get("targetX", 0),
        targetY=fresh.get("targetY", 0),
    )
    if control.stop.is_set():
        raise StopRequested()
    session.approve(args, answer, tool="autoengineer_operation")
    emit("dispatch", count=operation["count"])
    result = decode(
        await asyncio.wait_for(session.call_tool("autoengineer_operation", arguments=args), 12)
    )
    after = await read("autoengineer_view")
    expected = operation["count"] * (2 if operation["name"] == "copper-cable" else 1)
    gained = inventory(after, operation["name"]) - product_before
    verified = result.get("status") == "verified" and gained == expected
    verified = (
        verified
        and after["surface"] == before["surface"]
        and math.dist((after["x"], after["y"]), (before["x"], before["y"])) <= 0.5
    )
    if operation["kind"] == "craft":
        used = input_before - inventory(after, ingredient)
        verified = verified and used == operation["count"] * (
            2 if ingredient == "iron-plate" else 1
        )
    else:
        used = result.get("resource_before", 0) - result.get("resource_after", 0)
        verified = verified and used == operation["count"]
    if hasattr(session, "checkpoint"):
        session.checkpoint(
            verified,
            {
                "position": {"x": after["x"], "y": after["y"]},
                "inventory_gained": gained,
                "used": used,
            },
        )
    emit("operation_verified" if verified else "operation_failed", count=gained)
    if feed is not None and after["surface"] == before["surface"]:
        feed.publish(after)
    print("Operation status:", result.get("status"), flush=True)
    print("Inventory gained:", gained, "input/resource used:", used, flush=True)
    print("Verified operation:", verified, flush=True)
    if not verified:
        raise RuntimeError("Operation verification failed; session stopped")
