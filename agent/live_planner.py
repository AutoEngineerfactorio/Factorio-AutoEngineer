import asyncio
import json
import urllib.request

from autoengineer_config import get_settings, mcp_parameters
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from runtime_settings import model_endpoint, model_name, request_timeout
from ups_inference import guarded_urlopen


def api_base():
    """Return the model endpoint at the moment of the call.

    The endpoint used to be a module-level constant, which froze it when
    the module was first imported: a Settings change could never reach
    it. It is a function now, so the next request uses the configured
    endpoint.
    """
    return model_endpoint()

READ_TOOLS = (
    "get_player_position",
    "get_inventory",
    "scan_resources",
    "get_available_recipes",
)


async def observe(session, schemas):
    observation = {}

    for name in READ_TOOLS:
        tool = schemas.get(name)

        if tool is None:
            observation[name] = {"error": "Tool unavailable"}
            continue

        # Only call tools that take no required arguments.
        schema = tool.input_schema or {}
        if schema.get("required"):
            observation[name] = {
                "error": "Requires arguments",
                "required": schema["required"],
            }
            continue

        try:
            result = await asyncio.wait_for(
                session.call_tool(name, arguments={}),
                timeout=30,
            )
            observation[name] = {
                "error": bool(result.is_error),
                "content": [item.text for item in result.content if item.type == "text"],
            }
        except Exception as exc:
            observation[name] = {"error": str(exc)}

    return observation


def compact_observation(observation):
    compact = {}

    for name, result in observation.items():
        if result.get("error"):
            compact[name] = result
            continue

        try:
            value = json.loads(result["content"][0])
        except (KeyError, IndexError, ValueError, TypeError):
            compact[name] = {"error": "Could not parse observation"}
            continue

        if name == "get_available_recipes":
            recipes = value.get("recipes", [])
            compact[name] = {
                "total_recipes": len(recipes),
                "early_game_examples": [
                    recipe
                    for recipe in recipes
                    if recipe.get("name")
                    in {
                        "burner-mining-drill",
                        "stone-furnace",
                        "iron-plate",
                        "copper-plate",
                        "iron-gear-wheel",
                        "transport-belt",
                        "burner-inserter",
                    }
                ],
            }
        else:
            compact[name] = value

    return compact


def ask_qwen(observation):
    request = urllib.request.Request(
        api_base() + "/chat/completions",
        data=json.dumps(
            {
                "model": model_name() or get_settings()["llm_model"],
                "temperature": 0.1,
                "max_tokens": 350,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are Factorio AutoEngineer. "
                            "Plan using ONLY observed game data. "
                            "Choose one next action: observe, walk, "
                            "mine, or craft. "
                            "If information is missing, choose observe. "
                            "Do not invent items, recipes, positions, "
                            "or resources. "
                            "Return only valid JSON containing "
                            "action, target, and reason. "
                            "You cannot execute actions."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(compact_observation(observation)),
                    },
                ],
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with guarded_urlopen(request, timeout=request_timeout()) as response:
        return json.load(response)["choices"][0]["message"]["content"]


async def main():
    params = mcp_parameters()

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            schemas = {tool.name: tool for tool in tools.tools}

            observation = await observe(session, schemas)

            print("\n=== LIVE FACTORIO OBSERVATION ===")
            print(json.dumps(observation, indent=2)[:12000])

    print("\n=== QWEN DECISION ===")
    decision = await asyncio.to_thread(ask_qwen, observation)
    print(decision)

    print("\nDRY RUN ONLY: No gameplay actions executed.")


if __name__ == "__main__":
    asyncio.run(main())
