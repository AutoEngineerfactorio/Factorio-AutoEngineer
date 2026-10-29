-- AutoEngineer read-only observation API - map entities.
--
-- The map observation reads the entities of exactly one aligned 64x64 chunk.
-- It never charts, never requests chunk generation, never selects an entity
-- and never changes the world.
--
-- The entity shape matches what the dashboard has always consumed: the
-- prototype identity, the game's own chart colour, the observed direction
-- and the explicit bounding rectangle.
--
-- Factorio 2.1.23 API only.

local observation = require("observation")

-- The observed window is exactly one aligned 64x64 chunk.
local MAP_CHUNK_TILES = 64

-- The chunk is observed as four 32x32 sub-windows. The per-call limit
-- protects one find_entities_filtered query; the chunk budget bounds the
-- merged total. A chunk that reaches the budget is reported as partial.
local MAP_CHUNK_WINDOW_TILES = 32
local MAP_CHUNK_ENTITY_LIMIT = 512
local MAP_CHUNK_ENTITY_BUDGET = 2048
local MAX_BOUNDS_EXTENT = 128

--- The entity kinds the map observation reports.
local GROUPS = {
    { kind = "resource", types = { "resource" } },
    { kind = "nature", types = { "tree", "simple-entity", "cliff" } },
    { kind = "building", types = { "resource" }, force = "player" },
    { kind = "enemy", types = { "resource" }, force = "enemy" },
}

--- Read the chart colour of one prototype.
---
--- Factorio 2.1.23 charts an entity with friendly_map_color or
--- enemy_map_color when they are defined and falls back to map_color.
local function chart_color(prototype, keys)
    if not prototype then return nil end
    for _, key in ipairs(keys) do
        local ok_call, value = pcall(function() return prototype[key] end)
        if ok_call and type(value) == "table" and value.r and value.g and value.b then
            return {
                r = math.floor(math.min(1, math.max(0, tonumber(value.r) or 0)) * 255 + 0.5),
                g = math.floor(math.min(1, math.max(0, tonumber(value.g) or 0)) * 255 + 0.5),
                b = math.floor(math.min(1, math.max(0, tonumber(value.b) or 0)) * 255 + 0.5),
            }
        end
    end
    return nil
end

--- Resolve the observed chunk index from the request.
local function chunk_index(arguments, character)
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

local function observe_map(arguments)
    local player, character = observation.observed_player()
    if not player or not character then
        return observation.unavailable("no_connected_player_with_character")
    end
    local surface = character.surface

    local chunk_x, chunk_y, chunk_error = chunk_index(arguments, character)
    if chunk_error then return observation.error_status(chunk_error) end

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

    local entities = {}
    local partial = false
    local chunk_complete = true

    for _, group in ipairs(GROUPS) do
        local force = group.force
        if force == "player" then force = player.force.name end
        local found = {}
        -- The chunk is observed as four 32x32 sub-windows so one dense
        -- sub-window cannot starve the others.
        for wy = origin_y, origin_y + MAP_CHUNK_TILES - MAP_CHUNK_WINDOW_TILES, MAP_CHUNK_WINDOW_TILES do
            for wx = origin_x, origin_x + MAP_CHUNK_TILES - MAP_CHUNK_WINDOW_TILES, MAP_CHUNK_WINDOW_TILES do
                if #found >= MAP_CHUNK_ENTITY_BUDGET then
                    partial = true
                    chunk_complete = false
                    break
                end
                local ok_call, part = pcall(function()
                    return surface.find_entities_filtered({
                        area = { { wx, wy }, { wx + MAP_CHUNK_WINDOW_TILES, wy + MAP_CHUNK_WINDOW_TILES } },
                        type = group.types,
                        force = force,
                        limit = MAP_CHUNK_ENTITY_LIMIT + 1,
                    })
                end)
                if not ok_call or not part then
                    partial = true
                    chunk_complete = false
                else
                    if #part > MAP_CHUNK_ENTITY_LIMIT then
                        partial = true
                        chunk_complete = false
                    end
                    for index = 1, math.min(#part, MAP_CHUNK_ENTITY_LIMIT) do
                        if #found >= MAP_CHUNK_ENTITY_BUDGET then
                            partial = true
                            chunk_complete = false
                            break
                        end
                        found[#found + 1] = part[index]
                    end
                end
            end
        end

        for _, entity in ipairs(found) do
            if entity.valid and entity.type ~= "character"
                and inside(entity.position.x, entity.position.y)
                and is_visible(entity.position.x, entity.position.y) then
                local record = {
                    x = entity.position.x,
                    y = entity.position.y,
                    name = entity.name,
                    kind = group.kind,
                }
                if group.kind == "nature" or group.kind == "resource" then
                    -- Natural objects and resources need their own chart
                    -- colour and prototype identity so the map can draw a
                    -- tree, a rock, a cliff and an ore deposit differently.
                    record.entity_type = entity.type
                    local type_ok, prototype_type = pcall(function() return entity.prototype.type end)
                    if type_ok and type(prototype_type) == "string" then
                        record.prototype_type = prototype_type
                    end
                    local color = chart_color(entity.prototype, { "friendly_map_color", "map_color" })
                    if color then record.map_color = color end
                    local direction_ok, direction = pcall(function() return entity.direction end)
                    if direction_ok and type(direction) == "number" then
                        record.direction = direction
                    end
                    -- The graphics variation selects the tree's sprite
                    -- tint against the terrain underneath.
                    local variation_ok, variation = pcall(function() return entity.graphics_variation end)
                    if variation_ok and type(variation) == "number"
                        and variation >= 0 and variation < 256 then
                        record.graphics_variation = variation
                    end
                elseif group.kind == "enemy" then
                    -- A currently visible enemy needs its own chart colour,
                    -- the way the game charts it.
                    record.entity_type = entity.type
                    local type_ok, prototype_type = pcall(function() return entity.prototype.type end)
                    if type_ok and type(prototype_type) == "string" then
                        record.prototype_type = prototype_type
                    end
                    local color = chart_color(entity.prototype, { "enemy_map_color", "map_color" })
                    if color then record.map_color = color end
                end
                -- The 2.1.23 bounding_box is already in world coordinates and
                -- reflects orientation and offset.
                local box_ok, box = pcall(function() return entity.bounding_box end)
                if box_ok and box and box.left_top and box.right_bottom then
                    local a, b = box.left_top, box.right_bottom
                    if b.x > a.x and b.y > a.y
                        and b.x - a.x <= MAX_BOUNDS_EXTENT
                        and b.y - a.y <= MAX_BOUNDS_EXTENT then
                        record.bounds = {
                            left_top = { x = a.x, y = a.y },
                            right_bottom = { x = b.x, y = b.y },
                        }
                    end
                end
                entities[#entities + 1] = record
            end
        end
    end

    return observation.ok({
        tick = game.tick,
        map_chunk = { x = chunk_x, y = chunk_y, size = MAP_CHUNK_TILES },
        origin = { x = origin_x, y = origin_y },
        entities = entities,
        partial = partial,
        chunk_complete = chunk_complete,
        entity_limit = MAP_CHUNK_ENTITY_BUDGET,
    })
end

observation.HANDLERS.map = observe_map
