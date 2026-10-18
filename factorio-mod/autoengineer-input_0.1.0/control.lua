-- One bounded epoch per player; no key history or typed text is recorded.
local function state(index)
    local values=storage.human_epochs or {}
    return {version=1,generation=values[index] or 0}
end
local function takeover(event)
    local index=event.player_index
    if not index then return end
    storage.human_epochs=storage.human_epochs or {}
    storage.human_epochs[index]=(storage.human_epochs[index] or 0)+1
    if remote.interfaces.autoengineer_control and remote.interfaces.autoengineer_control.takeover then
        remote.call("autoengineer_control","takeover",index)
    end
end
for _,control in ipairs(require("inputs")) do
    script.on_event("autoengineer-human-"..control,takeover)
end
script.on_event(defines.events.on_player_controller_changed,takeover)
script.on_event(defines.events.on_player_driving_changed_state,takeover)
script.on_event(defines.events.on_player_changed_surface,takeover)
script.on_event(defines.events.on_pre_player_died,takeover)
script.on_event(defines.events.on_player_left_game,takeover)
remote.add_interface("autoengineer_input",{state=state,version=function() return 1 end,
    request_takeover=function(index)
        if type(index)~='number' or not game.get_player(index) then error('valid player required') end
        takeover{player_index=index}
        return state(index)
    end})
