import json
import re
import urllib.request

from autoengineer_config import get_settings

API = get_settings()["llm_api_url"]
ALLOWED = {"walk", "mine", "craft", "observe", "wait"}
FORBIDDEN = {"execute_lua", "teleport", "spawn_item", "create_entity"}

# Simulated observation; real MCP observations come later.
state = {
    "player_position": {"x": 0, "y": 0},
    "inventory": {},
    "nearby_resources": [
        {"name": "iron-ore", "x": 5, "y": 2},
        {"name": "stone", "x": 8, "y": 3},
        {"name": "coal", "x": -4, "y": 3},
    ],
    "goal": "Gather materials for early-game production",
}


def api(endpoint, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        API + endpoint,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def parse_json(content):
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content.strip())
    return json.loads(cleaned)


def validate(action):
    if not isinstance(action, dict):
        return False, "Action must be an object"

    name = action.get("action")
    if name not in ALLOWED or name in FORBIDDEN:
        return False, "Action not permitted"

    if name == "walk":
        if not all(
            isinstance(action.get(k), (int, float)) and not isinstance(action.get(k), bool)
            for k in ("x", "y")
        ):
            return False, "Walk requires numeric x and y"

    if name in ("mine", "craft"):
        if not isinstance(action.get("item"), str):
            return False, "Missing item name"
        count = action.get("count")
        if type(count) is not int or not 1 <= count <= 100:
            return False, "Invalid count"

    if name in ("observe", "wait"):
        if name == "wait":
            return False, "Wait is not enabled in this prototype"

    return True, "Allowed for dry run"


def main():
    model_id = get_settings()["llm_model"]
    print("Connected model:", model_id)

    response = api(
        "/chat/completions",
        {
            "model": model_id,
            "temperature": 0.1,
            "max_tokens": 250,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Factorio game-playing agent. "
                        "Use only the provided observation. "
                        "Choose exactly one next action. "
                        "Return only JSON with action, "
                        "optional x, y, item, count, and reason. "
                        "Available actions: walk, mine, craft, observe. "
                        "Never cheat or invent resources."
                    ),
                },
                {"role": "user", "content": json.dumps(state)},
            ],
        },
    )

    content = response["choices"][0]["message"]["content"]
    print("LLM response:", content)

    try:
        action = parse_json(content)
        valid, reason = validate(action)
        print("Validation:", reason)
        print("DRY RUN ONLY - no game commands executed")
    except (ValueError, TypeError) as error:
        print("Invalid model response:", error)


if __name__ == "__main__":
    main()
