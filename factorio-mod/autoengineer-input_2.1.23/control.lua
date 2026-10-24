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
