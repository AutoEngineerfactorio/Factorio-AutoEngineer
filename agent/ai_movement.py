from autoengineer_config import get_settings, mcp_parameters

import argparse
import asyncio
import json
import math
import urllib.request

from mcp import ClientSession
from mcp.client.stdio import stdio_client


API = get_settings()["llm_api_url"]
MAX_DISTANCE = 5.0


async def call_read_tool(session, name, args=None):
    allowed = {
        "get_player_position",
        "get_nearby_entities",
    }

    if name not in allowed:
        raise PermissionError("Read tool not allowed")

    result = await asyncio.wait_for(
        session.call_tool(name, arguments=args or {}),
        timeout=30,
    )

    if result.is_error:
        raise RuntimeError(f"{name} returned an error")

    for item in result.content:
        if item.type == "text":
            return json.loads(item.text)

    raise RuntimeError("No JSON response")


def ask_qwen(state):
    request = urllib.request.Request(
        API + "/chat/completions",
        data=json.dumps({
            "model": get_settings()["llm_model"],
            "temperature": 0.1,
            "max_tokens": 250,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You control a Factorio character. "
                        "Choose one nearby walking destination "
                        "within 5 tiles of the current position. "
                        "Return ONLY JSON with keys "
                        "action, x, y, reason. "
                        "action must equal walk. "
                        "Never invent resources or claim "
                        "that a destination is safe."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(state),
                },
            ],
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        content = json.load(response)["choices"][0]["message"]["content"]

    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    return json.loads(content)


def validate(decision, position):
    if not isinstance(decision, dict):
        raise ValueError("Invalid decision object")

    if decision.get("action") != "walk":
        raise PermissionError("Only walking is permitted")

    x, y = decision.get("x"), decision.get("y")

    if any(
        type(value) not in (int, float) or not math.isfinite(value)
        for value in (x, y)
    ):
        raise ValueError("Invalid coordinates")

    distance = math.dist(
        (position["x"], position["y"]),
        (x, y),
    )

    if distance > MAX_DISTANCE or distance < 0.5:
        raise PermissionError(
            f"Movement distance rejected: {distance:.2f}"
        )

    return {
        "targetX": x,
        "targetY": y,
        "tolerance": 0.75,
        "timeoutSeconds": 20,
    }


async def main(execute=False):
    params = mcp_parameters()

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            position = await call_read_tool(
                session, "get_player_position"
            )

            nearby = await call_read_tool(
                session,
                "get_nearby_entities",
                {"radius": 8},
            )

            state = {
                "position": position,
                "nearby_entities": nearby,
            }

            print("\n=== LIVE STATE ===")
            print(json.dumps(state, indent=2)[:5000])

            decision = await asyncio.to_thread(ask_qwen, state)

            print("\n=== QWEN PROPOSAL ===")
            print(json.dumps(decision, indent=2))

            arguments = validate(decision, position)

            print("\n=== VALIDATED MOVEMENT ===")
            print(json.dumps(arguments, indent=2))
            if not execute:
                print("\nDRY RUN: No movement executed.")
                return

            current = await call_read_tool(
                session, "get_player_position"
            )

            drift = math.dist(
                (position["x"], position["y"]),
                (current["x"], current["y"])
            )

            if drift > 0.5:
                raise RuntimeError(
                    "Player moved since observation. Aborting."
                )

            # Validate against the latest position.
            arguments = validate(decision, current)

            print("\nExecuting AI-selected movement...")

            result = await asyncio.wait_for(
                session.call_tool(
                    "walk_to_position",
                    arguments=arguments
                ),
                timeout=30
            )

            if result.is_error:
                raise RuntimeError("Movement tool failed")

            for item in result.content:
                if item.type == "text":
                    print("Movement result:", item.text)

            final = await call_read_tool(
                session, "get_player_position"
            )

            distance = math.dist(
                (position["x"], position["y"]),
                (final["x"], final["y"])
            )

            remaining = math.dist(
                (arguments["targetX"], arguments["targetY"]),
                (final["x"], final["y"])
            )

            print("\n=== MOVEMENT VERIFICATION ===")
            print("Final position:", final)
            print("Distance moved:", round(distance, 2))
            print("Distance from target:", round(remaining, 2))
            print(
                "Target reached:",
                remaining <= arguments["tolerance"]
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    asyncio.run(main(args.execute))
