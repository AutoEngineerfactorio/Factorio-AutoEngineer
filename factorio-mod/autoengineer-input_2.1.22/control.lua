-- Event handlers for human takeover
local function takeover(event)
    local index = event.player_index
    if not index then return end
    storage.human_epochs = storage.human_epochs or {}
    storage.human_epochs[index] = (storage.human_epochs[index] or 0) + 1
    if remote.interfaces.autoengineer_control and remote.interfaces.autoengineer_control.takeover then
        remote.call("autoengineer_control", "takeover", index)
    end
end

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

