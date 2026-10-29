-- AutoEngineer read-only observation API - map overlay helpers.
--
-- The overlay observation reads the optional display layers of exactly one
-- aligned 64x64 chunk. This module holds the shared window helpers and the
-- chart-based layers; the entity-based layers live in
-- ``observation_overlay_entities``.
--
-- Each layer is read independently and reports whether it was available and
-- whether it was truncated, so a layer that could not be read is never
-- presented as an empty layer.
--
-- Factorio 2.1.23 API only.

local observation = require("observation")

local MAP_CHUNK_TILES = 64

-- The per-layer bounds the dashboard has always accepted.
local MAX_POLLUTION = 81
local MAX_TAGS = 128

--- Resolve the observed chunk index from the request.
function observation.chunk_index(arguments, character)
    local chunk_x = math.floor(character.position.x / MAP_CHUNK_TILES)
    local chunk_y = math.floor(character.position.y / MAP_CHUNK_TILES)
    if arguments.chunk_x and arguments.chunk_y then
        chunk_x = observation.integer_argument(arguments.chunk_x, -100000, 100000)
        chunk_y = observation.integer_argument(arguments.chunk_y, -100000, 100000)
        if chunk_x == nil or chunk_y == nil then
            return nil, nil, "invalid_chunk_coordinates"
        end
    end
    return chunk_x, chunk_y, nil
end

--- Build the window helpers the overlay layers share.
function observation.overlay_window(player, character, chunk_x, chunk_y)
    local surface = character.surface
    local origin_x = chunk_x * MAP_CHUNK_TILES
    local origin_y = chunk_y * MAP_CHUNK_TILES
    local area = {
        { origin_x, origin_y },
        { origin_x + MAP_CHUNK_TILES, origin_y + MAP_CHUNK_TILES },
    }

    local function inside(x, y)
        return x >= origin_x and x < origin_x + MAP_CHUNK_TILES
            and y >= origin_y and y < origin_y + MAP_CHUNK_TILES
    end

    local function is_visible(x, y)
        local ok_call, value = pcall(function()
            return player.force.is_chunk_visible(surface, { math.floor(x / 32), math.floor(y / 32) })
        end)
        return ok_call and value or false
    end

    local function is_charted(x, y)
        local ok_call, value = pcall(function()
            return player.force.is_chunk_charted(surface, { math.floor(x / 32), math.floor(y / 32) })
        end)
        return ok_call and value or false
    end

    return {
        surface = surface,
        force_name = player.force.name,
        origin_x = origin_x,
        origin_y = origin_y,
        area = area,
        inside = inside,
        is_visible = is_visible,
        is_charted = is_charted,
    }
end

--- Read the pollution layer of the window.
function observation.pollution_layer(window)
    local result = {}
    for cy = math.floor(window.origin_y / 32),
        math.floor((window.origin_y + MAP_CHUNK_TILES - 1) / 32) do
        for cx = math.floor(window.origin_x / 32),
            math.floor((window.origin_x + MAP_CHUNK_TILES - 1) / 32) do
            local x = math.max(window.origin_x, cx * 32)
            local y = math.max(window.origin_y, cy * 32)
            if window.is_charted(x, y) then
                local ok_call, value = pcall(function()
                    return window.surface.get_pollution({ x, y })
                end)
                if ok_call and type(value) == "number" then
                    result[#result + 1] = {
                        x = x,
                        y = y,
                        value = value,
                        width = math.min(window.origin_x + MAP_CHUNK_TILES, (cx + 1) * 32) - x,
                        height = math.min(window.origin_y + MAP_CHUNK_TILES, (cy + 1) * 32) - y,
                    }
                end
            end
        end
    end
    return result, #result >= MAX_POLLUTION
end

--- Remove control characters and bound the length of a label.
function observation.clean_label(text)
    return string.sub(string.gsub(text or "", "%c", " "), 1, 128)
end

--- Read the chart tag layer of the window.
function observation.tag_layer(window)
    local ok_call, found = pcall(function()
        return game.forces[window.force_name].find_chart_tags(window.surface, window.area)
    end)
    if not ok_call or not found then return nil, false end
    local result = {}
    for index = 1, math.min(#found, MAX_TAGS) do
        local tag = found[index]
        if tag.valid and window.inside(tag.position.x, tag.position.y)
            and window.is_charted(tag.position.x, tag.position.y) then
            local icon = ""
            if tag.icon and tag.icon.name then
                icon = observation.clean_label(tag.icon.name)
            end
            result[#result + 1] = {
                x = tag.position.x,
                y = tag.position.y,
                text = observation.clean_label(tag.text),
                icon = icon,
            }
        end
    end
    return result, #found > MAX_TAGS
end

--- Read the overlay layers of the requested chunk.
local function observe_overlay(arguments)
    local player, character = observation.observed_player()
    if not player or not character then
        return observation.unavailable("no_connected_player_with_character")
    end

    local chunk_x, chunk_y, chunk_error = observation.chunk_index(arguments, character)
    if chunk_error then return observation.error_status(chunk_error) end

    local window = observation.overlay_window(player, character, chunk_x, chunk_y)
    local overlays = {
        schema = 1,
        available = {},
        partial = {},
        player_name = string.sub(player.name or "", 1, 128),
    }

    -- Read one layer defensively. A failure marks the layer unavailable
    -- instead of failing the whole observation.
    local function layer(name, read)
        local ok_call, result, is_partial = pcall(read)
        overlays.available[name] = ok_call
        overlays[name] = ok_call and result or {}
        overlays.partial[name] = ok_call and is_partial == true or false
    end

    layer("pollution", function() return observation.pollution_layer(window) end)
    layer("electric", function() return observation.electric_layer(window) end)
    layer("logistics", function() return observation.logistics_layer(window) end)
    layer("turrets", function() return observation.turret_layer(window) end)
    layer("stations", function() return observation.station_layer(window) end)
    layer("tags", function() return observation.tag_layer(window) end)

    return observation.ok({
        tick = game.tick,
        map_chunk = { x = chunk_x, y = chunk_y, size = MAP_CHUNK_TILES },
        origin = { x = window.origin_x, y = window.origin_y },
        overlays = overlays,
    })
end

observation.HANDLERS.overlay = observe_overlay
