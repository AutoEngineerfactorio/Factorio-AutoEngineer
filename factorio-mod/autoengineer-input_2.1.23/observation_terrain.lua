-- AutoEngineer read-only observation API - terrain raster.
--
-- The terrain observation reads the charted tiles of exactly one aligned
-- 64x64 chunk and returns them as a palette-indexed raster. It never
-- charts, never requests chunk generation and never changes the world.
--
-- The raster shape matches what the dashboard has always consumed: one
-- two-hex-digit palette index per tile, a palette of at most 256 colours
-- and the chunk metadata that ties the raster to an aligned window.
--
-- Factorio 2.1.23 API only.

local observation = require("observation")

-- The observed window is exactly one aligned 64x64 chunk.
local MAP_CHUNK_TILES = 64

-- Factorio 2.1.23 shades a charted-but-not-currently-visible map tile by
-- this factor. The renderer must not apply it a second time.
local FOG_SHADE = 0.6667

-- The palette bound. A raster may not carry more colours than this.
local MAX_PALETTE = 256

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

--- Format one palette colour as the two hex digits the raster uses.
local function palette_index(palette, colors, hex)
    local index = colors[hex]
    if not index then
        if #palette < MAX_PALETTE then
            index = #palette
            palette[#palette + 1] = hex
            colors[hex] = index
        else
            -- The palette is full: the tile keeps the background colour
            -- rather than silently recolouring another tile.
            index = 0
        end
    end
    return index
end

local function observe_terrain(arguments)
    local player, character = observation.observed_player()
    if not player or not character then
        return observation.unavailable("no_connected_player_with_character")
    end
    local surface = character.surface

    local chunk_x, chunk_y, chunk_error = chunk_index(arguments, character)
    if chunk_error then return observation.error_status(chunk_error) end

    local origin_x = chunk_x * MAP_CHUNK_TILES
    local origin_y = chunk_y * MAP_CHUNK_TILES

    -- The charted state is asked once per 32x32 chunk, not once per tile.
    local charted = {}
    local function is_charted(x, y)
        local key = math.floor(x / 32) .. ":" .. math.floor(y / 32)
        local state = charted[key]
        if state == nil then
            local ok_call, value = pcall(function()
                return player.force.is_chunk_charted(surface, { math.floor(x / 32), math.floor(y / 32) })
            end)
            state = ok_call and value or false
            charted[key] = state
        end
        return state
    end

    local visible = {}
    local function is_visible(x, y)
        local key = math.floor(x / 32) .. ":" .. math.floor(y / 32)
        local state = visible[key]
        if state == nil then
            local ok_call, value = pcall(function()
                return player.force.is_chunk_visible(surface, { math.floor(x / 32), math.floor(y / 32) })
            end)
            state = ok_call and value or false
            visible[key] = state
        end
        return state
    end

    -- Palette-indexed tile rows preserve one-tile detail without huge
    -- JSON cell objects.
    local rows = {}
    local palette = { "#000000" }
    local colors = { ["#000000"] = 0 }
    for y = origin_y, origin_y + MAP_CHUNK_TILES - 1 do
        local row = {}
        for x = origin_x, origin_x + MAP_CHUNK_TILES - 1 do
            local index = 0
            if is_charted(x, y) then
                local tile_ok, tile = pcall(function() return surface.get_tile(x, y) end)
                local color_ok, color = false, nil
                if tile_ok and tile then
                    color_ok, color = pcall(function() return tile.prototype.map_color end)
                end
                if color_ok and color and type(color) == "table" then
                    local shade = is_visible(x, y) and 1 or FOG_SHADE
                    local hex = string.format("#%02x%02x%02x",
                        math.floor((color.r or 0) * shade + 0.5),
                        math.floor((color.g or 0) * shade + 0.5),
                        math.floor((color.b or 0) * shade + 0.5))
                    index = palette_index(palette, colors, hex)
                end
            end
            row[#row + 1] = string.format("%02x", index)
        end
        rows[#rows + 1] = table.concat(row)
    end

    return observation.ok({
        tick = game.tick,
        terrain = {
            origin = { x = origin_x, y = origin_y },
            step = 1,
            rows = rows,
            palette = palette,
            map_chunk = { x = chunk_x, y = chunk_y, size = MAP_CHUNK_TILES },
            -- The raster itself is complete: every tile of the chunk was
            -- read. Entity completeness is reported by the map observation.
            chunk_complete = true,
            partial = false,
        },
    })
end

observation.HANDLERS.terrain = observe_terrain
