-- AutoEngineer read-only observation API - telemetry.
--
-- The telemetry observation is map-free and recipe-free: it reads the
-- production statistics of the player's surface and the electrical flow of
-- the networks near the player. Nothing here charts, generates, selects or
-- mutates anything.
--
-- Every collection is bounded and the coverage is reported explicitly, so a
-- sampled answer is never presented as a complete force-wide rate.
--
-- Factorio 2.1.23 API only.

local observation = require("observation")

-- Hard bounds. These cap the work and the response size of one observation.
local MAX_TELEMETRY_ITEMS = 24
local MAX_TELEMETRY_FLUIDS = 12
local MAX_ELECTRIC_NETWORKS = 4
local MAX_ELECTRIC_POLES = 16

-- The production windows the answer reports. ``one_minute`` is the rate
-- window Factorio keeps for the last minute and ``five_seconds`` the short
-- window; the per-second rate is derived from the short window.
local WINDOWS = { "one_minute", "five_seconds" }

--- Read one production statistic flow count defensively.
local function flow_count(statistics, name, category, precision)
    if not statistics then return nil end
    local ok_call, value = pcall(function()
        return statistics.get_flow_count({
            name = name,
            category = category,
            precision_index = precision,
        })
    end)
    if not ok_call or type(value) ~= "number" then return nil end
    if value ~= value or value == math.huge or value == -math.huge then return nil end
    return value
end

--- Read the production windows for one statistics object.
local function production_windows(statistics, name)
    local row = {}
    for _, window in ipairs(WINDOWS) do
        local precision = defines.flow_precision_index[window]
        local produced = flow_count(statistics, name, "output", precision)
        local consumed = flow_count(statistics, name, "input", precision)
        if produced ~= nil or consumed ~= nil then
            row[window] = {
                produced = produced or 0,
                consumed = consumed or 0,
                -- The short window is five seconds long, so the per-second
                -- rate is that count divided by five.
                per_second_produced = produced and produced / 5 or nil,
                per_second_consumed = consumed and consumed / 5 or nil,
            }
        end
    end
    return row
end

--- Collect the distinct prototype names present in the character inventory.
local function inventory_prototype_names(character, limit)
    local names, seen = {}, {}
    local inventory = character.get_inventory(defines.inventory.character_main)
    if not inventory then return names, false end
    for index = 1, math.min(#inventory, 200) do
        local stack = inventory[index]
        if stack.valid_for_read and not seen[stack.name] then
            seen[stack.name] = true
            names[#names + 1] = stack.name
            if #names >= limit then return names, true end
        end
    end
    return names, false
end

--- Read one electric network's last-tick flow.
local function electric_row(network, tick, subnetwork_id)
    local flow = network.flow_last_tick
    if not flow then return nil end
    local row = { network_id = subnetwork_id, tick = tick }
    for _, field in ipairs({
        "maximum_production",
        "maximum_consumption",
        "consumption_satisfaction",
        "production_satisfaction",
        "accumulator_energy",
        "accumulator_capacity",
    }) do
        local value = flow[field]
        if type(value) ~= "number" or value ~= value or value < 0 or value == math.huge then
            return nil
        end
        row[field] = value
    end
    return row
end

--- Read the item production and consumption of the player's surface.
local function observe_items(player, character, surface)
    local names, truncated = inventory_prototype_names(character, MAX_TELEMETRY_ITEMS)
    local ok_call, statistics = pcall(function()
        return player.force.get_item_production_statistics(surface)
    end)
    if not ok_call or not statistics then
        return {
            status = "unavailable",
            reason = "production statistics are unavailable for this surface",
            items = {},
            item_names_sampled = #names,
            item_names_truncated = truncated,
            partial = true,
        }
    end
    local items = {}
    for _, name in ipairs(names) do
        local windows = production_windows(statistics, name)
        if windows.one_minute or windows.five_seconds then
            items[#items + 1] = {
                name = name,
                one_minute = windows.one_minute,
                five_seconds = windows.five_seconds,
            }
        end
    end
    return {
        status = "ok",
        items = items,
        item_names_sampled = #names,
        item_names_truncated = truncated,
        partial = truncated,
    }
end

--- Read the fluid production and consumption of the player's surface.
local function observe_fluids(player, surface)
    local ok_call, statistics = pcall(function()
        return player.force.get_fluid_production_statistics(surface)
    end)
    if not ok_call or not statistics then
        return {
            status = "unavailable",
            reason = "fluid production statistics are unavailable for this surface",
            fluids = {},
            partial = true,
        }
    end
    local names = {}
    for name in pairs(prototypes.fluid) do
        if type(name) == "string" then names[#names + 1] = name end
    end
    table.sort(names)
    local fluids = {}
    for index = 1, math.min(#names, MAX_TELEMETRY_FLUIDS) do
        local windows = production_windows(statistics, names[index])
        if windows.one_minute or windows.five_seconds then
            fluids[#fluids + 1] = {
                name = names[index],
                one_minute = windows.one_minute,
                five_seconds = windows.five_seconds,
            }
        end
    end
    return { status = "ok", fluids = fluids, partial = #names > MAX_TELEMETRY_FLUIDS }
end

--- Read the electrical flow of the networks near the player.
local function observe_power(player, surface, force)
    local poles_ok, poles = pcall(function()
        return surface.find_entities_filtered({
            position = player.position,
            radius = 48,
            force = force,
            type = "electric-pole",
            limit = MAX_ELECTRIC_POLES,
        })
    end)
    if not poles_ok or not poles then
        return {
            status = "unavailable",
            reason = "the electric network survey failed",
            unit = "joules_per_tick",
            networks = {},
            partial = true,
        }
    end
    local networks = {}
    local seen_networks = {}
    for _, pole in ipairs(poles) do
        local network = pole.electric_network
        if network then
            local parent = network.parent_network or network
            -- LuaElectricSubNetwork.id is the 2.1.23 identity; the parent
            -- LuaElectricNetwork has flow_last_tick but no network_id.
            local id = network.id
            if id and not seen_networks[id] and #networks < MAX_ELECTRIC_NETWORKS then
                seen_networks[id] = true
                local row = electric_row(parent, game.tick, id)
                if row then networks[#networks + 1] = row end
            end
        end
    end
    if #networks == 0 then
        return {
            status = "unavailable",
            reason = "no nearby readable electric network",
            unit = "joules_per_tick",
            networks = {},
            partial = false,
        }
    end
    table.sort(networks, function(a, b) return a.network_id < b.network_id end)
    return {
        status = "ok",
        unit = "joules_per_tick",
        tick = game.tick,
        networks = networks,
        partial = #poles >= MAX_ELECTRIC_POLES,
    }
end

-- Constant-cost context: current force research and the character's own chunk.
local function dashboard_context(force, surface, position)
    local research = {status="unavailable"}
    local research_ok, current = pcall(function() return force.current_research end)
    if research_ok then
        if current == nil then research = {status="ok",active=false}
        else
            local ok_values, name, progress = pcall(function()
                return current.name, force.research_progress
            end)
            if ok_values and type(name) == "string" and #name <= 128
                and type(progress) == "number" and progress >= 0 and progress <= 1 then
                research = {status="ok",active=true,name=name,progress=progress}
            end
        end
    end
    local pollution = {status="unavailable",coverage="character_chunk"}
    local ok_pollution, amount = pcall(function() return surface.get_pollution(position) end)
    if ok_pollution and type(amount) == "number" and amount == amount
        and amount >= 0 and amount < math.huge then
        pollution = {status="ok",coverage="character_chunk",amount=amount}
    end
    return research, pollution
end

local function observe_telemetry()
    local player, character = observation.observed_player()
    if not player or not character then
        return observation.unavailable("no_connected_player_with_character")
    end
    local surface = character.surface
    local force = player.force

    local items = observe_items(player, character, surface)
    local fluids = observe_fluids(player, surface)
    local power = observe_power(player, surface, force)
    local research, pollution = dashboard_context(force, surface, character.position)

    return observation.ok({
        tick = game.tick,
        x = character.position.x,
        y = character.position.y,
        surface = surface.name,
        production = {
            status = items.status,
            reason = items.reason,
            items = items.items,
            item_names_sampled = items.item_names_sampled,
            item_names_truncated = items.item_names_truncated,
            fluids = fluids.fluids,
            fluid_status = fluids.status,
            fluid_reason = fluids.reason,
            partial = items.partial or fluids.partial,
            coverage = "sampled prototypes only; not a complete force-wide rate",
        },
        power = power,
        research = research,
        pollution = pollution,
    })
end

observation.HANDLERS.telemetry = observe_telemetry
