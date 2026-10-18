import asyncio
import json

from autoengineer_config import mcp_parameters
from mcp import ClientSession
from mcp.client.stdio import stdio_client

NAMES = [
    "get_player_position",
    "get_inventory",
    "scan_resources",
    "find_nearest",
    "walk_to_position",
    "mine_resource",
    "craft",
    "check_craft_feasibility",
    "get_recipe_details",
    "get_nearby_entities",
]


async def main():
    params = mcp_parameters()

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

            tools = {tool.name: tool for tool in result.tools}

            for name in NAMES:
                print(f"\n=== {name} ===")

                tool = tools.get(name)
                if not tool:
                    print("NOT FOUND")
                    continue

                print("Description:", tool.description)
                print("Input schema:")
                print(json.dumps(tool.input_schema, indent=2))

    print("\nINSPECTION COMPLETE: No gameplay actions executed.")


if __name__ == "__main__":
    asyncio.run(main())
