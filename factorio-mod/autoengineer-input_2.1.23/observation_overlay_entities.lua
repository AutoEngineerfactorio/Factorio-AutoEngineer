-- AutoEngineer read-only observation API - entity-based map overlays.
--
-- The electric, logistics, turret and train stop layers of the map
-- overlay observation. The shared window helpers live in
-- ``observation_overlay``.
--
-- Nothing here charts, selects or changes anything; the module only reads.
--
-- Factorio 2.1.23 API only.

local observation = require("observation")

-- The per-layer bounds the dashboard has always accepted.
local MAX_ELECTRIC = 128
local MAX_LOGISTICS = 64
local MAX_TURRETS = 128
local MAX_STATIONS = 128
local MAX_CONNECTIONS = 16

--- Read the entities of one type inside the window.
local function own(window, types, limit, read)
    local ok_call, found = pcall(function()
        return window.surface.find_entities_filtered({
            area = window.area,
            force = window.force_name,
            type = types,
            limit = limit + 1,
        })
    end)
    if not ok_call or not found then return nil, false end
    local result = {}
    for index = 1, math.min(#found, limit) do
        local entity = found[index]
        if entity.valid and window.inside(entity.position.x, entity.position.y)
            and window.is_visible(entity.position.x, entity.position.y) then
            read(entity, result)
        end
    end
    return result, #found > limit
end

--- Read the electric pole layer.
function observation.electric_layer(window)
    return own(window, { "electric-pole" }, MAX_ELECTRIC, function(entity, result)
        local lines = {}
        local ok_call, connector = pcall(function()
            return entity.get_wire_connector(defines.wire_connector_id.pole_copper, false)
        end)
        if ok_call and connector then
            for _, wire in pairs(connector.connections) do
                local target = wire.target.owner
                if #lines < MAX_CONNECTIONS and target.valid
                    and window.inside(target.position.x, target.position.y)
                    and window.is_visible(target.position.x, target.position.y) then
                    lines[#lines + 1] = { x = target.position.x, y = target.position.y }
                end
            end
        end
        local radius = 0
        local radius_ok, value = pcall(function()
            return entity.prototype.get_supply_area_distance(entity.quality)
        end)
        if radius_ok and type(value) == "number" then radius = value end
        result[#result + 1] = {
            x = entity.position.x, y = entity.position.y,
            radius = radius, connections = lines,
        }
    end)
end

--- Read the roboport logistic layer.
function observation.logistics_layer(window)
    return own(window, { "roboport" }, MAX_LOGISTICS, function(entity, result)
        local cell = entity.logistic_cell
        if cell and cell.valid then
            result[#result + 1] = {
                x = entity.position.x,
                y = entity.position.y,
                logistic = cell.logistic_radius,
                construction = cell.construction_radius,
                active = cell.transmitting,
            }
        end
    end)
end

--- Read the turret layer.
function observation.turret_layer(window)
    return own(window,
        { "ammo-turret", "electric-turret", "fluid-turret", "artillery-turret" },
        MAX_TURRETS, function(entity, result)
            local range = 0
            local range_ok, value = pcall(function() return entity.prototype.turret_range end)
            if range_ok and type(value) == "number" then range = value end
            result[#result + 1] = {
                x = entity.position.x, y = entity.position.y, radius = range,
            }
        end)
end

--- Read the train stop layer.
function observation.station_layer(window)
    return own(window, { "train-stop" }, MAX_STATIONS, function(entity, result)
        result[#result + 1] = {
            x = entity.position.x,
            y = entity.position.y,
            text = observation.clean_label(entity.backer_name),
        }
    end)
end
