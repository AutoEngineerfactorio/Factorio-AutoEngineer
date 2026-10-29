-- AutoEngineer read-only observation API - request parsing.
--
-- The parser is the security boundary of the observation API. It accepts a
-- fixed operation selector plus a small set of strictly named arguments and
-- refuses everything else, so no client-supplied text can ever reach the
-- game as Lua or as a command separator.
--
-- Factorio 2.1.23 API only.

local parse = {}

-- Operations the backend may request. An unknown selector is refused.
parse.OPERATIONS = {
    status = true,
    telemetry = true,
    map = true,
    terrain = true,
    overlay = true,
    inventory = true,
    recipes = true,
    research = true,
    machines = true,
    capabilities = true,
    machine_inventories = true,
    logistics = true,
    robots = true,
    transport = true,
}

-- The arguments each operation understands. Any other name is refused so a
-- typo can never silently widen the read.
local PAGED = { page = true, page_size = true }
local CHUNKED = { chunk_x = true, chunk_y = true }
-- The inventory and logistics observations may be narrowed by surface and
-- by entity type. Both are optional and both are bounded by the handler.
local FILTERED = { page = true, page_size = true, surface = true,
                   entity_type = true }
parse.ALLOWED_ARGUMENTS = {
    status = {},
    telemetry = {},
    map = CHUNKED,
    terrain = CHUNKED,
    overlay = CHUNKED,
    inventory = {},
    recipes = PAGED,
    research = PAGED,
    capabilities = PAGED,
    -- The machine, logistics and transport observations may be narrowed by
    -- surface and by entity type.
    machine_inventories = FILTERED,
    logistics = FILTERED,
    robots = {},
    transport = FILTERED,
}

--- Split the command parameter into an operation and validated arguments.
--- Returns nil plus a reason when anything is not understood.
function parse.parameter(parameter)
    if type(parameter) ~= "string" or parameter == "" then
        return nil, "missing_operation"
    end
    local parts = {}
    for word in parameter:gmatch("%S+") do
        parts[#parts + 1] = word
    end
    if #parts == 0 then return nil, "missing_operation" end

    local operation = parts[1]
    if not parse.OPERATIONS[operation] then
        return nil, "unknown_operation"
    end

    local arguments = {}
    for index = 2, #parts do
        local word = parts[index]
        local key, value = word:match("^([%a_]+)=(.+)$")
        if not key or not value then
            return nil, "malformed_argument"
        end
        if arguments[key] ~= nil then
            return nil, "duplicate_argument"
        end
        arguments[key] = value
    end
    for key in pairs(arguments) do
        if not parse.ALLOWED_ARGUMENTS[operation][key] then
            return nil, "unknown_argument"
        end
    end

    return { operation = operation, arguments = arguments }
end

return parse
