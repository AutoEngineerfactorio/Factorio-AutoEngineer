from autoengineer_config import get_settings, mcp_parameters

import asyncio
import json
import math
import urllib.request
import time
import signal
import sys

from session_safety import ConsoleControl, SafetySession, StopRequested, daemon_call

from movement_proposals import movement_choices, proposal_messages, resolve_choice

from movement_watchdog import monitored_walk
from agent_events import emit
from dispatch_boundary import DispatchBoundary

from mcp import ClientSession
from mcp.client.stdio import stdio_client

API = get_settings()["llm_api_url"]
MAX_ACTIONS = 3
MAX_WALK = 5.0

READ_TOOLS = {
    "get_player_position",
    "get_nearby_entities",
    "scan_resources",
}

WRITE_TOOLS = {"walk_to_position"}


def decode(result):
    if result.is_error:
        raise RuntimeError("MCP returned an error")
    for part in result.content:
        if part.type == "text":
            return json.loads(part.text)
    raise RuntimeError("Missing JSON result")


async def read_tool(session, name, args=None):
    if name not in READ_TOOLS:
        raise PermissionError("Read tool forbidden")
    result = await asyncio.wait_for(
        session.call_tool(name, arguments=args or {}),
        timeout=30
    )
    value = decode(result)
    if not isinstance(value, dict):
        raise ValueError("Invalid observation")
    if name == "get_player_position" and any(type(value.get(k)) not in (float, int) or not math.isfinite(value[k]) for k in ("x", "y")):
        raise ValueError("Invalid player position")
    return value


def ask_ai(observation, history):
    choices = movement_choices(observation, history)
    if not choices:
        return {"action": "stop", "x": None, "y": None, "reason": "No untried short waypoints remain"}
    payload = {
        "model": get_settings()["llm_model"],
        "temperature": 0.2,
        "max_tokens": 120,
        "messages": proposal_messages(observation, history, choices),
    }

    req = urllib.request.Request(
        API + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=120) as res:
        content = json.load(res)["choices"][0]["message"]["content"]

    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    return resolve_choice(json.loads(content), choices)


def validate(decision, position):
    if not isinstance(decision, dict):
        raise ValueError("Invalid AI response")

    action = decision.get("action")

    if action == "stop":
        return None

    if action != "walk":
        raise PermissionError("Only walking is enabled")

    x = decision.get("x")
    y = decision.get("y")

    if any(
        type(v) not in (float, int) or not math.isfinite(v)
        for v in (x, y)
    ):
        raise ValueError("Invalid coordinates")

    distance = math.dist(
        (position["x"], position["y"]), (x, y)
    )

    if not 0.5 <= distance <= MAX_WALK:
        raise PermissionError(
            f"Walking distance rejected: {distance:.2f}"
        )

    return {
        "targetX": x,
        "targetY": y,
        "tolerance": 0.75,
        "timeoutSeconds": 20
    }


async def run_cycles(session, control, owner):
    if not isinstance(session, DispatchBoundary):
        session = DispatchBoundary(session, control)
    history = []
    attempted = []
    for step in range(1, MAX_ACTIONS + 1):
        emit("proposal", cycle=step)
        print(f"\n=== AI CYCLE {step}/{MAX_ACTIONS} ===")

        position = await read_tool(
            session, "get_player_position"
        )
        resources = await read_tool(
            session, "scan_resources",
            {"radius": 50}
        )
        nearby = await read_tool(
            session, "get_nearby_entities",
            {"radius": 8}
        )

        state = {
            "position": position,
            "resources": resources,
            "nearby": nearby
        }

        decision = await daemon_call(
            ask_ai, state, history
        )

        print("\nQwen proposes:")
        print(json.dumps(decision, indent=2))

        try:
            arguments = validate(decision, position)
        except (ValueError, PermissionError) as exc:
            print("\n=== PROPOSAL REJECTED ===")
            print("Reason:", str(exc))
            print("No gameplay action executed.")
            history.append({
                "decision": decision,
                "result": "validation_rejected",
                "reason": str(exc)
            })
            continue

        if arguments is None:
            print("AI chose to stop.")
            break

        print("\nValidated action:")
        print(json.dumps(arguments, indent=2))

        approval = await control.approve()
        emit("approval", cycle=step, approved=approval == "y")

        if approval == "q":
            print("Stopped by user.")
            break

        if approval != "y":
            history.append({
                "decision": decision,
                "result": "rejected_by_user"
            })
            continue

        latest = await read_tool(
            session, "get_player_position"
        )

        drift = math.dist(
            (position["x"], position["y"]),
            (latest["x"], latest["y"])
        )

        if drift > 0.5:
            print("Player position changed. Action cancelled.")
            break

        arguments = validate(decision, latest)

        name = "walk_to_position"
        if name not in WRITE_TOOLS:
            raise PermissionError("Write tool forbidden")

        if control.stop.is_set():
            raise StopRequested()
        if any(math.dist((latest["x"], latest["y"]), origin) <= 0.75 and
               math.dist((arguments["targetX"], arguments["targetY"]), target) <= 1.0
               for origin, target in attempted):
            emit("movement_repeated", cycle=step)
            print("Repeated movement from the same location rejected.")
            continue
        attempted.append(((latest["x"], latest["y"]), (arguments["targetX"], arguments["targetY"])))
        arguments["safetyOwner"] = owner
        session.approve(arguments, approval)
        emit("dispatch", cycle=step)
        began = time.monotonic()
        result = await asyncio.wait_for(
            monitored_walk(session, arguments),
            timeout=30
        )

        outcome = decode(result)

        final = await read_tool(
            session, "get_player_position"
        )

        remaining = math.dist(
            (arguments["targetX"], arguments["targetY"]),
            (final["x"], final["y"])
        )

        moved = math.dist(
            (latest["x"], latest["y"]),
            (final["x"], final["y"])
        )

        initial_remaining = math.dist(
            (latest["x"], latest["y"]),
            (
                arguments["targetX"],
                arguments["targetY"]
            )
        )

        progress = initial_remaining - remaining

        success = (
            outcome.get("status") == "arrived"
            and remaining <= arguments["tolerance"]
            and moved >= 0.25
            and progress >= 0.15
        )

        print("\n=== ACTION RESULT ===")
        print("MCP status:", outcome.get("status"))
        print("Final position:", final)
        print("Distance to target:", round(remaining, 2))
        print("Distance moved:", round(moved, 2))
        print("Progress toward target:", round(progress, 2))
        print("Verified success:", success)

        stalled = outcome.get("status") == "stuck" or (not success and moved < 0.25 and outcome.get("status") != "no_path")
        emit("movement_arrived" if success else "movement_stalled" if stalled else "movement_failed",
             cycle=step, moved=moved, remaining=remaining, progress=progress, elapsed=time.monotonic()-began,
             status=outcome.get("status") if outcome.get("status") in {"arrived", "no_path", "stuck", "timeout"} else "other")
        history.append({
            "decision": decision,
            "outcome": outcome.get("status"),
            "verified": success
        })

        if not success:
            if outcome.get("status") in {"no_path", "stuck", "timeout"}:
                # Completed backend route calls clear walking before returning.
                # Confirm a stationary position before any fresh proposal; a
                # failed observation, transport error or cancellation ends safely.
                await asyncio.sleep(0.1)
                stationary = await read_tool(session, "get_player_position")
                if math.dist((final["x"], final["y"]),
                             (stationary["x"], stationary["y"])) <= 0.01:
                    if control.stop.is_set():
                        raise StopRequested()
                    emit("route_recovery", cycle=step)
                    print("Route blocked; excluding this destination. A new movement requires fresh approval.")
                    continue
                print("Player still moving after route failure; stopping loop.")
            else:
                print("Verification failed; stopping loop.")
            break



async def main():
    params = mcp_parameters()
    emit("session_start")
    control = ConsoleControl()
    control.start_reader(sys.stdin)
    loop = asyncio.get_running_loop()
    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.getsignal(sig)
        signal.signal(sig, lambda *_: loop.call_soon_threadsafe(control.stop.set))
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=10)
                session = DispatchBoundary(session, control)
                await session.verify()
                emit("policy_verified")
                try:
                    safety = SafetySession(session, control)
                    await safety.run(
                        lambda: run_cycles(session, control, safety.owner)
                    )
                except StopRequested:
                    print("Stopped by user or closed input.", flush=True)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        emit("session_end")
    print("\nSupervised session finished.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
