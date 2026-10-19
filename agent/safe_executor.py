import argparse
import asyncio
import json
import math

from autoengineer_config import mcp_parameters
from mcp import ClientSession
from mcp.client.stdio import stdio_client

# This first executor allows only these MCP calls.
ALLOWED_TOOLS = {
    "get_player_position",
    "walk_to_position",
}

MAX_STEP = 5.0


def parse_result(result):
    if result.is_error:
        raise RuntimeError("MCP tool returned an error")

    for item in result.content:
        if item.type == "text":
            try:
                return json.loads(item.text)
            except json.JSONDecodeError:
                return {"message": item.text}

    raise RuntimeError("No usable MCP response")


async def safe_call(session, name, arguments):
    if name not in ALLOWED_TOOLS:
        raise PermissionError(f"Tool forbidden: {name}")

    result = await asyncio.wait_for(
        session.call_tool(name, arguments=arguments),
        timeout=45,
    )
    return parse_result(result)


async def main(execute):
    # Legacy proof-of-concept has no owner-scoped approval or lease path.
    # Fail before even opening MCP; approved movement belongs to supervised_agent.
    if execute:
        raise PermissionError(
            "Legacy --execute disabled: use supervised_agent under the restricted "
            "Semi-Autonomous approval/lease policy"
        )
    params = mcp_parameters()

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            position = await safe_call(session, "get_player_position", {})

            x = float(position["x"])
            y = float(position["y"])

            if not all(map(math.isfinite, (x, y))):
                raise ValueError("Invalid player position")

            # Initial controlled experiment:
            # move three tiles east from the current position.
            target_x = x + 3.0
            target_y = y

            distance = math.dist((x, y), (target_x, target_y))

            if distance > MAX_STEP:
                raise PermissionError("Move exceeds safety limit")

            arguments = {
                "targetX": target_x,
                "targetY": target_y,
                "tolerance": 0.75,
                "timeoutSeconds": 20,
            }

            print("\n=== AUTOENGINEER ACTION ===")
            print("Current position:", position)
            print("Proposed action: walk_to_position")
            print("Validated arguments:")
            print(json.dumps(arguments, indent=2))
            print("Distance:", round(distance, 2), "tiles")

            if not execute:
                print("\nDRY RUN: No movement executed.")
                return

            print("\nExecuting approved movement...")

            result = await safe_call(session, "walk_to_position", arguments)

            print("MCP movement result:")
            print(json.dumps(result, indent=2))

            new_position = await safe_call(session, "get_player_position", {})

            moved = math.dist(
                (x, y),
                (
                    float(new_position["x"]),
                    float(new_position["y"]),
                ),
            )

            print("\n=== VERIFICATION ===")
            print("New position:", new_position)
            print("Distance moved:", round(moved, 2), "tiles")
            print(
                "Physical movement detected:"
                if moved > 0.25
                else "No significant movement detected",
                moved > 0.25,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the validated movement",
    )
    args = parser.parse_args()
    asyncio.run(main(args.execute))
