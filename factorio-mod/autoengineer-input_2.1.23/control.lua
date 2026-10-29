-- Event handlers for human takeover
local function takeover(event)
    local index = event.player_index
    if not index then return end
    storage.human_epochs = storage.human_epochs or {}
    storage.human_epochs[index] = (storage.human_epochs[index] or 0) + 1
    if remote.interfaces.autoengineer_control and remote.interfaces.autoengineer_control.takeover then
        -- This interface name is negotiated dynamically with the companion mod.
        -- LuaLS cannot infer a static keyof type for runtime registered methods.
        local invoke_remote = remote.call
        ---@cast invoke_remote fun(interface_name:string, method:string, player_index:number)
        invoke_remote("autoengineer_control", "takeover", index)
    end
end

-- Use registered mod commands, not /c. The game's first-Lua-command warning
-- must remain intact for arbitrary scripting and achievement-affecting actions.
commands.add_command("autoengineer-status",
    "Show your AutoEngineer input guard generation without changing the game.",
    function(command)
        if not command.player_index then return end
        local player = game.get_player(command.player_index)
        if not player then return end
        local values = storage.human_epochs or {}
        player.print("AutoEngineer input guard active; takeover generation: " ..
            tostring(values[command.player_index] or 0) ..
            ". See the dashboard for AI connection/status.")
    end)

commands.add_command("autoengineer-takeover",
    "Revoke the AutoEngineer control lease for your own character.",
    function(command)
        if not command.player_index then return end
        local player = game.get_player(command.player_index)
        if not player then return end
        takeover{player_index = command.player_index}
        player.print("AutoEngineer human takeover requested.")
    end)

-- Read-only observation command used by the AutoEngineer backend.
--
-- The backend reaches the game through this registered mod command rather
-- than through a raw Lua console command. A registered command is not
-- arbitrary scripting, so an observation never triggers the Factorio
-- achievement-disabling confirmation.
--
-- The parameter is a fixed operation selector plus strictly numeric
-- arguments. No client-supplied Lua is accepted and no gameplay action is
-- possible through this command.
local observation = require("observation")
-- The telemetry module registers the telemetry operation.
require("observation_telemetry")
-- The map module registers the map operation.
require("observation_map")
-- The terrain module registers the terrain raster operation.
require("observation_terrain")
-- The overlay module registers the map overlay operation.
require("observation_overlay")
-- The entity layer module adds the electric, logistics, turret and station
-- layers to the overlay observation.
require("observation_overlay_entities")
-- The inventory module registers the inventory operation.
require("observation_inventory")
-- The logistics module registers the machine, logistics, robot and
-- transport observations.
require("observation_logistics")
-- The catalog module registers the recipe, research and machine operations.
require("observation_catalog")
require("observation_singleplayer_export")

commands.add_command("autoengineer-observe",
    "Read-only AutoEngineer observation (status, telemetry, map, recipes, research, machines).",
    function(command)
        local document = observation.run(command.parameter)
        local text = helpers.table_to_json(document)
        if command.player_index then
            -- A player typed the command: show it to that player only.
            local player = game.get_player(command.player_index)
            if player then player.print(text) end
        else
            -- Issued over RCON: the response body carries the document.
            rcon.print(text)
        end
    end)

-- Register event listeners using script.on_event (2.0+)
script.on_event("autoengineer-human-move-up", takeover)
script.on_event("autoengineer-human-move-down", takeover)
script.on_event("autoengineer-human-move-left", takeover)
script.on_event("autoengineer-human-move-right", takeover)
script.on_event("autoengineer-human-mine", takeover)
script.on_event("autoengineer-human-build", takeover)
script.on_event("autoengineer-human-build-ghost", takeover)
script.on_event("autoengineer-human-super-forced-build", takeover)
script.on_event("autoengineer-human-toggle-driving", takeover)
script.on_event("autoengineer-human-shoot-enemy", takeover)
script.on_event("autoengineer-human-shoot-selected", takeover)
script.on_event("autoengineer-human-open-character-gui", takeover)
script.on_event("autoengineer-human-open-gui", takeover)
script.on_event("autoengineer-human-controller-gui-crafting-tab", takeover)
script.on_event("autoengineer-human-use-item", takeover)
script.on_event("autoengineer-human-alternative-use-item", takeover)
script.on_event("autoengineer-human-pick-items", takeover)
script.on_event("autoengineer-human-drop-cursor", takeover)
script.on_event("autoengineer-human-copy-entity-settings", takeover)
script.on_event("autoengineer-human-paste-entity-settings", takeover)
script.on_event("autoengineer-human-select-for-blueprint", takeover)
script.on_event("autoengineer-human-select-for-cancel-deconstruct", takeover)

-- Built-in event listeners
script.on_event(defines.events.on_player_controller_changed, takeover)
script.on_event(defines.events.on_player_driving_changed_state, takeover)
script.on_event(defines.events.on_player_changed_surface, takeover)
script.on_event(defines.events.on_pre_player_died, takeover)
-- Respawn invalidates any previous lease; use player_index only (2.1.23 API).
script.on_event(defines.events.on_player_respawned, takeover)
script.on_event(defines.events.on_player_left_game, takeover)

-- Remote interface
remote.add_interface("autoengineer_input", {
    state = function(index)
        local values = storage.human_epochs or {}
        return { version = 1, generation = values[index] or 0 }
    end,
    version = function() return 1 end,
    request_takeover = function(index)
        if type(index) ~= 'number' or not game.get_player(index) then
            error('valid player required')
        end
        takeover{player_index = index}
        local values = storage.human_epochs or {}; return {version = 1, generation = values[index] or 0}
    end
})
