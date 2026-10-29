-- AutoEngineer read-only observation API - core.
--
-- The AutoEngineer backend reaches the game through this registered mod
-- command instead of through raw Lua console commands. A command registered
-- with commands.add_command() is not arbitrary scripting, so Factorio does
-- not treat an observation as achievement-affecting and never asks the
-- operator to confirm that achievements may be disabled.
--
-- Security rules this module enforces:
--   * the client never supplies Lua; only a fixed operation selector and
--     strictly numeric arguments are accepted;
--   * every parameter is validated and an unknown operation is refused;
--   * every collection is bounded and the truncation is reported;
--   * no gameplay action is possible through this API - it only reads;
--   * the answer is a single versioned JSON document.
--
-- Factorio 2.1.23 API only. The signatures used here were verified against
-- the 2.1.23 offline archive (memory/_r09_api_facts.json).

local PROTOCOL_VERSION = 1

-- The module table returned to control.lua.
local observation = {}

-- The request parser is the security boundary of the observation API.
local parse = require("observation_parse")

--- Build a successful, versioned answer document.
function observation.ok(payload)
    payload.protocol = PROTOCOL_VERSION
    payload.status = payload.status or "ok"
    return payload
end

--- Build an error answer document.
function observation.error_status(reason)
    return observation.ok({ status = "error", reason = reason })
end

--- Build an "unavailable" answer document.
function observation.unavailable(reason)
    return observation.ok({ status = "unavailable", reason = reason })
end

--- Parse a strictly numeric integer argument.
function observation.integer_argument(value, minimum, maximum)
    if type(value) ~= "string" then return nil end
    if not value:match("^%-?%d+$") then return nil end
    local number = tonumber(value)
    if number == nil then return nil end
    if number < minimum or number > maximum then return nil end
    return number
end

--- Return the single connected player with a character, or nil.
---
--- The character is returned as well so a caller never has to re-narrow a
--- nullable ``player.character``.
function observation.observed_player()
    if #game.connected_players ~= 1 then return nil end
    local player = game.connected_players[1]
    if not player then return nil end
    local character = player.character
    if not character then return nil end
    return player, character
end

-- ---------------------------------------------------------------------------
-- status
-- ---------------------------------------------------------------------------

local function observe_status()
    local player, character = observation.observed_player()
    if not player or not character then
        return observation.unavailable("no_connected_player_with_character")
    end
    local lease = storage.autoengineer_safety
    local control = {
        lease_active = lease ~= nil and not lease.stopped and game.tick < lease.deadline,
        walking = character.walking_state.walking,
        character_control = player.controller_type == defines.controllers.character and not player.driving,
        generation = 0,
        input_adapter = false,
    }
    if remote.interfaces.autoengineer_input then
        local ok_call, value = pcall(remote.call, "autoengineer_input", "state", player.index)
        if ok_call and type(value) == "table" and value.version == 1 then
            control.input_adapter = true
            control.generation = value.generation
        end
    end
    return observation.ok({
        tick = game.tick,
        x = character.position.x,
        y = character.position.y,
        surface = character.surface.name,
        force = player.force.name,
        control = control,
        connected_players = #game.connected_players,
        game_version = script.active_mods and script.active_mods.base,
        player_name = player.name,
    })
end

-- ---------------------------------------------------------------------------
-- dispatch
-- ---------------------------------------------------------------------------

-- The handler table is public so the telemetry, map and catalog modules can
-- register their own operations without this file needing to know them.
observation.HANDLERS = {
    status = observe_status,
}

--- Run one observation and return its JSON document.
function observation.run(parameter)
    local request, reason = parse.parameter(parameter)
    if not request then
        return observation.error_status(reason)
    end
    local handler = observation.HANDLERS[request.operation]
    if not handler then
        return observation.error_status("unknown_operation")
    end
    local success, result = pcall(handler, request.arguments)
    if not success then
        -- A failure inside an observation is reported as an error state. The
        -- internal message never leaves the mod.
        return observation.error_status("observation_failed")
    end
    return result
end

return observation
