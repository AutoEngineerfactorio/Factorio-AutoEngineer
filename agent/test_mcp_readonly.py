import asyncio

from autoengineer_config import mcp_parameters
from mcp import ClientSession
from mcp.client.stdio import stdio_client


async def main():
    params = mcp_parameters()

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()

            print("MCP connected.")
            print("Available tool count:", len(tools.tools))

            names = [tool.name for tool in tools.tools]

            if "get_player_position" not in names:
                print("GetPlayerPosition not found.")
                print("Available names:", names)
                return

            result = await session.call_tool("get_player_position", arguments={})

            print("Player position result:")

            for item in result.content:
                if item.type == "text":
                    print(item.text)

            if result.is_error:
                print("MCP returned an error.")

            print("READ-ONLY TEST COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
