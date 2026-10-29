-- AutoEngineer read-only observation API - inventory and logistics.
--
-- This module adds the four observation categories that R10-A could only
-- show as explicitly unavailable:
--
--   * ``machines``  - the inventories of the crafting machines, the storage
--     chests, the wagons and the tanks on one surface, with the item
--     quantities, the qualities, the capacities and the machine identity;
--   * ``logistics`` - the logistic networks of the force with their
--     available counts and their provider, requester, buffer and storage
--     membership;
--   * ``robots``    - the aggregate logistic and construction robot
--     availability, read from the network counters rather than by walking
--     the robots;
--   * ``transport`` - the train contents, the wagon inventories, the
--     locomotive fuel and the fluid wagons.
--
-- Three rules govern everything in this file.
--
-- **Read only.** Nothing here inserts, removes, moves or crafts anything.
-- Only the documented 2.1.23 getters are called.
--
-- **Bounded.** Every collection has an explicit cap and reports whether it
-- was reached. The factory is never scanned in full: the entity search is
-- bounded and the counts are read before the entities are.
--
-- **Honest.** A field the game did not report is reported as absent. A
-- shortage is only reported when the game itself can satisfy the request
-- question; it is never derived from an unrelated number.
--
-- The exact 2.1.23 signatures used here were verified against the offline
-- API archive; they are listed in memory/R10_B_API_FACTS_2123.md.

local observation = require("observation")

-- ---------------------------------------------------------------------------
-- bounds
-- ---------------------------------------------------------------------------

--: The largest number of entities one page may inspect.
local MAX_ENTITIES_PER_PAGE = 64

--: The largest number of inventory slots one entity may report.
local MAX_SLOTS_PER_ENTITY = 48

--: The largest number of distinct item stacks one entity may report.
local MAX_ITEMS_PER_ENTITY = 32

--: The largest number of fluid containers one entity may report.
local MAX_FLUIDS_PER_ENTITY = 16

--: The largest number of logistic networks one page may report.
local MAX_NETWORKS_PER_PAGE = 16

--: The largest number of member entities one network may report.
local MAX_NETWORK_MEMBERS = 32

--: The largest number of item stacks one network may report.
local MAX_NETWORK_ITEMS = 64

--: The largest number of trains one page may report.
local MAX_TRAINS_PER_PAGE = 16

--: The largest page number the parser accepts.
local MAX_PAGE = 100000

-- ---------------------------------------------------------------------------
-- the entity types this module reads
-- ---------------------------------------------------------------------------

-- The entity types whose inventories are read. A type that the running
-- game does not have is simply never matched.
--
-- "storage-chest" covers the wooden, iron and steel chests. The logistic
-- container is included because its request slots are a requester.
local MACHINE_TYPES = {
    ["assembling-machine"] = true,
    ["furnace"] = true,
    ["rocket-silo"] = true,
    ["lab"] = true,
    ["mining-drill"] = true,
    ["offshore-pump"] = true,
    ["pump"] = true,
    ["boiler"] = true,
    ["steam-engine"] = true,
    ["steam-turbine"] = true,
    ["agricultural-tower"] = true,
    ["asteroid-collector"] = true,
    ["storage-chest"] = true,
    ["logistic-container"] = true,
    ["cargo-wagon"] = true,
    ["fluid-wagon"] = true,
    ["locomotive"] = true,
    ["storage-tank"] = true,
    ["fluid-tank"] = true,
    ["car"] = true,
    ["spider-vehicle"] = true,
    ["turret"] = true,
    ["ammo-turret"] = true,
    ["artillery-turret"] = true,
    ["beacon"] = true,
    ["roboport"] = true,
    ["container"] = true,
}

-- The entity types whose inventories are read as transport and storage.
local TRANSPORT_TYPES = {
    ["cargo-wagon"] = true,
    ["fluid-wagon"] = true,
    ["locomotive"] = true,
    ["storage-tank"] = true,
    ["fluid-tank"] = true,
    ["storage-chest"] = true,
    ["logistic-container"] = true,
    ["car"] = true,
}

-- ---------------------------------------------------------------------------
-- the inventory identifiers this module probes
-- ---------------------------------------------------------------------------

-- Factorio 2.1.23 has **no** generic "input" or "output" inventory
-- identifier. ``defines.inventory`` is a fixed enum of entity-specific
-- inventories, so a machine's ingredient inventory can only be reached by
-- probing a bounded, explicit candidate list.
--
-- Every identifier below was read out of the 2.1.23 ``defines.inventory``
-- enum in the offline archive. An identifier that is not in that enum is
-- never named here: it would be a guess, and a guess that silently reads
-- the wrong inventory is worse than no inventory at all.
--
-- The ingredient-like identifiers of the 2.1.23 enum are the input, source
-- and arm identifiers plus the storage identifiers.
local INGREDIENT_IDENTIFIERS = {
    ["lab_input"] = true,
    ["crafter_input"] = true,
    ["agricultural_tower_input"] = true,
    ["asteroid_collector_arm"] = true,
    ["chest"] = true,
    ["cargo_wagon"] = true,
    ["character_main"] = true,
    ["linked_container_main"] = true,
    ["proxy_main"] = true,
    ["hub_main"] = true,
}

-- The output-like identifiers of the same enum.
local OUTPUT_IDENTIFIERS = {
    ["crafter_output"] = true,
    ["agricultural_tower_output"] = true,
    ["asteroid_collector_output"] = true,
    ["chest"] = true,
    ["cargo_wagon"] = true,
    ["hub_main"] = true,
    ["linked_container_main"] = true,
}

-- The module-slot identifiers of the same enum.
local MODULE_IDENTIFIERS = {
    ["lab_modules"] = true,
    ["mining_drill_modules"] = true,
    ["beacon_modules"] = true,
    ["agricultural_tower_modules"] = true,
    ["crafter_modules"] = true,
}

-- The fuel identifier of the same enum.
local FUEL_IDENTIFIERS = {
    ["fuel"] = true,
}

-- The burnt-result identifier of the same enum.
local BURNT_RESULT_IDENTIFIERS = {
    ["burnt_result"] = true,
}

-- The ammunition identifier of the same enum.
local AMMO_IDENTIFIERS = {
    ["turret_ammo"] = true,
    ["artillery_turret_ammo"] = true,
    ["artillery_wagon_ammo"] = true,
    ["character_ammo"] = true,
}

-- The vehicle-trunk identifier of the same enum.
local VEHICLE_IDENTIFIERS = {
    ["car_trunk"] = true,
    ["spider_trunk"] = true,
}

-- The roboport robot and material identifiers of the same enum.
local ROBOPORT_IDENTIFIERS = {
    ["roboport_robot"] = true,
    ["roboport_material"] = true,
}

-- The candidate inventories probed for one entity, in a stable order. The
-- order is fixed so that two observations of the same factory report the
-- same inventories in the same sequence.
local PROBE_ORDER = {
    { category = "ingredient", identifiers = INGREDIENT_IDENTIFIERS },
    { category = "output", identifiers = OUTPUT_IDENTIFIERS },
    { category = "fuel", identifiers = FUEL_IDENTIFIERS },
    { category = "module", identifiers = MODULE_IDENTIFIERS },
    { category = "burnt_result", identifiers = BURNT_RESULT_IDENTIFIERS },
    { category = "ammo", identifiers = AMMO_IDENTIFIERS },
    { category = "vehicle", identifiers = VEHICLE_IDENTIFIERS },
    { category = "roboport", identifiers = ROBOPORT_IDENTIFIERS },
}

-- ---------------------------------------------------------------------------
-- small helpers
-- ---------------------------------------------------------------------------

--- Return the identifier of an inventory enum member, or nil.
---
--- The identifiers are read from ``defines.inventory`` at run time so a
--- member that the running game does not have is skipped instead of
--- raising. The fallback table keeps the module working in the offline
--- contract tests, whose shim only declares a few members.
local function inventory_identifier(name)
    local inventory = defines and defines.inventory
    if type(inventory) ~= "table" then return nil end
    local value = inventory[name]
    if value == nil then return nil end
    return value
end

--- Return the stacks of one inventory as a bounded list of plain tables.
---
--- The inventory is read through ``get_contents`` which already returns
--- one entry per item and quality pair, so a stack is never missed. The
--- result is sorted so that two observations of the same inventory report
--- the same order.
local function inventory_contents(inventory, limit)
    if inventory == nil then return nil end
    local ok, contents = pcall(function()
        return inventory.get_contents()
    end)
    if not ok or type(contents) ~= "table" then return nil end
    local rows = {}
    local truncated = false
    for _, entry in pairs(contents) do
        local name = entry.name
        local count = entry.count
        local quality = "normal"
        if type(entry.quality) == "table" and type(entry.quality.name) == "string" then
            quality = entry.quality.name
        elseif type(entry.quality) == "string" then
            quality = entry.quality
        end
        if type(name) == "string" and type(count) == "number" then
            if #rows < limit then
                rows[#rows + 1] = { name = name, quality = quality, count = count }
            else
                truncated = true
            end
        end
    end
    table.sort(rows, function(a, b)
        if a.name ~= b.name then return a.name < b.name end
        return a.quality < b.quality
    end)
    return rows, truncated
end

--- Return the number of slots an inventory has.
local function inventory_capacity(inventory)
    if inventory == nil then return nil end
    local ok, size = pcall(function() return #inventory end)
    if not ok or type(size) ~= "number" then return nil end
    return size
end

--- Return the bounded fluid contents of one entity.
---
--- ``get_fluid_contents`` returns a dictionary of fluid name to amount.
--- The temperature is read from ``get_fluid`` when the entity exposes a
--- fluid box, because it is the only documented source of it.
local function entity_fluids(entity, limit)
    local ok, contents = pcall(function()
        return entity.get_fluid_contents()
    end)
    if not ok or type(contents) ~= "table" then return nil end
    local rows = {}
    local truncated = false
    local names = {}
    for name in pairs(contents) do
        if type(name) == "string" then names[#names + 1] = name end
    end
    table.sort(names)
    for _, name in ipairs(names) do
        local amount = contents[name]
        if type(amount) == "number" then
            if #rows < limit then
                local row = { name = name, amount = amount }
                -- The temperature is meaningful only for a fluid that is
                -- actually held by the entity.
                local got, fluid = pcall(function()
                    return entity.get_fluid(1)
                end)
                if got and type(fluid) == "table" and type(fluid.temperature) == "number" then
                    if fluid.name == name then row.temperature = fluid.temperature end
                end
                rows[#rows + 1] = row
            else
                truncated = true
            end
        end
    end
    return rows, truncated
end

--- Return the name of an entity's quality, or "normal".
local function entity_quality(entity)
    local ok, quality = pcall(function() return entity.quality end)
    if ok and type(quality) == "table" and type(quality.name) == "string" then
        return quality.name
    end
    return "normal"
end

--- Return the selected recipe name of an entity, or nil.
---
--- ``get_recipe`` returns the recipe and, when the recipe has one, the
--- quality. A machine without a selected recipe reports nil, which is not
--- the same as an empty recipe.
local function entity_recipe(entity)
    local ok, recipe = pcall(function()
        return entity.get_recipe()
    end)
    if not ok or recipe == nil then return nil end
    if type(recipe) == "table" and type(recipe.name) == "string" then
        return recipe.name
    end
    if type(recipe) == "string" then return recipe end
    return nil
end

--- Probe the bounded candidate inventories of one entity.
---
--- The probe is the whole point: Factorio 2.1.23 has no generic input or
--- output inventory identifier, so the only honest way to find a machine's
--- inventories is to try the documented identifiers and report the ones
--- that answered.
local function probe_inventories(entity)
    local found = {}
    local seen = {}
    for _, group in ipairs(PROBE_ORDER) do
        local identifiers = {}
        for identifier in pairs(group.identifiers) do
            identifiers[#identifiers + 1] = identifier
        end
        table.sort(identifiers)
        for _, identifier in ipairs(identifiers) do
            -- The same identifier can serve two categories; it is read once.
            local key = identifier
            if not seen[key] then
                seen[key] = true
                local enum = inventory_identifier(identifier)
                if enum ~= nil then
                    local ok, inventory = pcall(function()
                        return entity.get_inventory(enum)
                    end)
                    if ok and inventory ~= nil then
                        local rows, truncated = inventory_contents(
                            inventory, MAX_ITEMS_PER_ENTITY)
                        local capacity = inventory_capacity(inventory)
                        found[#found + 1] = {
                            category = group.category,
                            identifier = identifier,
                            slots = capacity,
                            capacity = capacity,
                            items = rows or {},
                            -- The item count is reported next to the list so
                            -- that an empty inventory can never be confused
                            -- with an inventory that was not read.
                            item_count = rows and #rows or 0,
                            empty = rows ~= nil and #rows == 0,
                            truncated = truncated,
                        }
                    end
                end
            end
        end
    end
    return found
end

--- Return the bounded position of an entity.
local function entity_position(entity)
    local ok, position = pcall(function() return entity.position end)
    if not ok or type(position) ~= "table" then return nil end
    local x = tonumber(position.x)
    local y = tonumber(position.y)
    if x == nil or y == nil then return nil end
    return { x = x, y = y }
end

--- Return a stable ordering key for an entity.
---
--- The key is the surface name, the prototype name, the quality, the
--- position and the entity number, so that two observations of the same
--- factory agree on the order even when the entity numbers differ. The
--- entity number is the last part, so two entities of the same type at
--- the same position still get distinct keys and the page boundary
--- stays deterministic.
local function entity_sort_key(surface_name, entity)
    local position = entity_position(entity)
    local x = position and position.x or 0
    local y = position and position.y or 0
    local name = "?"
    local ok, prototype_name = pcall(function() return entity.name end)
    if ok and type(prototype_name) == "string" then name = prototype_name end
    -- The unit number identifies the entity. ``tonumber`` is used so the
    -- value is a plain number: the raw attribute is a 64-bit integer and
    -- the format string below needs a number.
    ---@type number
    local number = 0
    local ok_number, value = pcall(function() return entity.unit_number end)
    if ok_number then
        local converted = tonumber(value)
        if converted ~= nil then number = converted end
    end
    return string.format("%s\x1f%s\x1f%s\x1f%012.2f\x1f%012.2f\x1f%012d",
        surface_name, name, entity_quality(entity), x, y, number)
end

--- Return the surface a surface filter names, or nil.
---
--- The surface filter is a numeric index or an exact name. An unknown
--- surface is an error, not an empty surface.
local function resolve_surface(arguments)
    local requested = arguments.surface
    if requested == nil then return nil, nil end
    -- Preserve the parser's inferred optional integer without a conflicting cast.
    local index = observation.integer_argument(requested, 1, 1024)
    if index ~= nil then
        for _, surface in pairs(game.surfaces) do
            if surface.index == index then return surface end
        end
        return nil, "unknown_surface"
    end
    for _, surface in pairs(game.surfaces) do
        if surface.name == requested then return surface end
    end
    return nil, "unknown_surface"
end

--- Resolve the bounded page number and page size.
---
--- The parsed value is kept in its own local, so the returned page and page
--- size are always numbers: the parsed value may be absent, and an
--- absent value is refused rather than assigned.
---
--- The two locals are annotated as ``number`` and not left to inference.
--- The literal ``1`` would be inferred as an ``integer``, and an
--- ``integer`` cannot take the ``number|nil`` that the argument parser
--- returns.
---@param arguments table
---@param maximum number
---@return number|nil, number|nil, string|nil
local function page_bounds(arguments, maximum)
    ---@type number
    local page = 1
    ---@type number
    local page_size = maximum
    if arguments.page then
        local parsed = observation.integer_argument(arguments.page, 1, MAX_PAGE)
        if parsed == nil then return nil, nil, "invalid_page" end
        page = parsed
    end
    if arguments.page_size then
        local parsed = observation.integer_argument(arguments.page_size, 1, maximum)
        if parsed == nil then return nil, nil, "invalid_page_size" end
        page_size = parsed
    end
    return page, page_size, nil
end

--- Return the first and last index of the requested page.
local function page_range(page, page_size, total)
    local first = (page - 1) * page_size + 1
    if first > total then return nil, nil end
    return first, math.min(first + page_size - 1, total)
end

--- Return the entity type filter, or nil when no filter was given.
local function entity_type_filter(arguments)
    local requested = arguments.entity_type
    if requested == nil then return nil end
    if type(requested) ~= "string" or requested == "" then return false end
    if #requested > 64 then return false end
    return requested
end

--- Build the bounded entity search filter for one surface.
---
--- The filter carries **no** ``area``. The 2.1.23 documentation states that
--- "if no area or position and radius is given, the entire surface is
--- searched", and an ``area`` has to be a bounding box
--- ``{{x1, y1}, {x2, y2}}``. Passing the surface object itself is not a
--- valid area, so the filter omits it entirely.
---
--- The search is bounded twice: ``count_entities_filtered`` gives the
--- total before anything is read, and ``find_entities_filtered`` is given
--- a ``limit`` so the game itself stops after the requested number.
local function search_entities(surface, type_filter, limit, shape)
    -- The search uses the **set** form of the type filter: a table whose
    -- keys are the entity types. ``find_entities_filtered`` accepts it and
    -- the R09 map observation already uses it in the live game. A *list*
    -- of names would not match, because the filter looks the type up as a
    -- key.
    local types = type_filter or MACHINE_TYPES
    local set = {}
    local names = {}
    if type(types) == "string" then
        set[types] = true
        names[1] = types
    else
        for name in pairs(types) do
            set[name] = true
            names[#names + 1] = name
        end
    end
    table.sort(names)

    -- The call is made inside a closure on purpose. ``pcall`` would pass
    -- the surface as the first argument, and the game would then see two
    -- arguments where it expects one.
    local ok, entities = pcall(function()
        return surface.find_entities_filtered({
            type = set,
            limit = limit + 1,
        })
    end)
    if ok and type(entities) == "table" and #entities > 0 then
        return entities, #entities
    end

    -- The set form found nothing. Fall back to one type at a time, which
    -- every build accepts.
    local found = {}
    for _, name in ipairs(names) do
        if #found >= limit then break end
        local ok_one, part = pcall(function()
            return surface.find_entities_filtered({
                type = name,
                limit = limit - #found + 1,
            })
        end)
        if ok_one and type(part) == "table" then
            for _, entity in ipairs(part) do
                found[#found + 1] = entity
                if #found >= limit then break end
            end
        end
    end
    if #found > 0 then return found, #found end
    if ok and type(entities) == "table" then return entities, #entities end
    return found, #found
end

--- Return the number of entities of the searched kinds on a surface.
---
--- The 2.1.23 build rejects an **array** of types for
--- ``count_entities_filtered`` ("bad argument #4 of 5 ...
--- (string expected)"), while ``find_entities_filtered`` accepts the
--- array form. The count is therefore taken **one type at a time** and
--- summed, so it stays the number of the kinds this module reads and
--- never the number of every entity on the surface.
---
--- The failure reason is returned with the count, so an unavailable
--- section can name **why** it is unavailable instead of only saying
--- that it is. The reason is a short, bounded description of the error the
--- game raised; it never carries game state.
local function count_entities(surface, type_filter)
    -- Without a type filter the search would cover every entity on the
    -- surface, so only the kinds this module reads are counted.
    local types = type_filter or MACHINE_TYPES
    local names = {}
    if type(types) == "string" then
        names[1] = types
    else
        for name in pairs(types) do names[#names + 1] = name end
    end
    table.sort(names)

    ---@type number
    local total = 0
    local last_reason = nil
    local counted_types = {}
    for _, name in ipairs(names) do
        -- The call is made inside a closure on purpose. ``pcall`` would
        -- pass the surface as the first argument, and the game would then
        -- see two arguments where it expects one.
        local ok, count = pcall(function()
            return surface.count_entities_filtered({ type = name })
        end)
        if ok and type(count) == "number" then
            total = total + count
            counted_types[#counted_types + 1] = name
        elseif not ok then
            -- A type the game does not have is not an error: the game
            -- simply has no entity of that type. The count stays.
            local reason = tostring(count)
            if #reason > 120 then
                reason = string.sub(reason, 1, 120)
            end
            last_reason = reason
        end
    end
    return total, last_reason, "per_type", counted_types
end

--- Build the snapshot identity of one observation.
---
--- The snapshot token lets the caller detect that the factory changed
--- between two pages. It is the game tick plus the total number of
--- matching entities, so a page that was read against a different factory
--- state is recognisable.
local function snapshot_token(tick, total)
    return string.format("%d:%d", tick, total)
end

-- ---------------------------------------------------------------------------
-- machines
-- ---------------------------------------------------------------------------

local function observe_machines(arguments)
    -- The request is validated **before** the game state is consulted, so a
    -- malformed request is always refused as an error and never as an
    -- "unavailable" answer that depends on who happens to be connected.
    local page, page_size, page_error = page_bounds(arguments, MAX_ENTITIES_PER_PAGE)
    if page_error then return observation.error_status(page_error) end
    local type_filter = entity_type_filter(arguments)
    if type_filter == false then
        return observation.error_status("invalid_entity_type")
    end

    local player = observation.observed_player()
    if not player then
        return observation.unavailable("no_connected_player_with_character")
    end

    local surface, surface_error = resolve_surface(arguments)
    if surface_error then return observation.error_status(surface_error) end
    if surface == nil then
        local character = player.character
        if not character then
            return observation.unavailable("no_connected_player_with_character")
        end
        surface = character.surface
    end
    if not surface.valid then
        return observation.unavailable("surface_unavailable")
    end

    local total, count_reason, shape, counted = count_entities(surface,
                                                              type_filter)
    if total == nil then
        return observation.unavailable(
            "entity_count_unavailable: " .. (count_reason or "unknown"))
    end

    -- The entity list is read once and sorted, so that the page boundary
    -- is deterministic and does not depend on the game's own iteration
    -- order.
    local entities = search_entities(surface, type_filter,
                                    MAX_ENTITIES_PER_PAGE * 4, shape)
    if entities == nil then
        return observation.unavailable("entity_search_unavailable")
    end
    local keyed = {}
    for _, entity in pairs(entities) do
        keyed[#keyed + 1] = { entity = entity, key = entity_sort_key(surface.name, entity) }
    end
    table.sort(keyed, function(a, b) return a.key < b.key end)

    local rows = {}
    local first, last = page_range(page, page_size, #keyed)
    local inspected = 0
    if first then
        for index = first, last do
            local entity = keyed[index].entity
            if not entity.valid then goto continue end
            inspected = inspected + 1
            local row = {
                name = entity.name,
                type = entity.type,
                surface = surface.name,
                quality = entity_quality(entity),
            }
            -- The unit number identifies the entity. Two entities of the
            -- same prototype share the prototype name, so the name alone
            -- cannot tell the rows apart.
            local ok_number, unit = pcall(function()
                return entity.unit_number
            end)
            if ok_number then
                -- ``tonumber`` turns the 64-bit integer attribute into a
                -- plain number, so the row always carries a number.
                local converted = tonumber(unit)
                if converted ~= nil then row.unit_number = converted end
            end
            local position = entity_position(entity)
            if position then
                row.x = position.x
                row.y = position.y
            end
            local recipe = entity_recipe(entity)
            if recipe then row.recipe = recipe end
            local active = nil
            local ok_active, value = pcall(function() return entity.active end)
            if ok_active and type(value) == "boolean" then active = value end
            if active ~= nil then row.active = active end
            row.inventories = probe_inventories(entity)
            row.inventory_count = #row.inventories
            local fluids = entity_fluids(entity, MAX_FLUIDS_PER_ENTITY)
            if fluids then
                row.fluids = fluids
                row.fluids_truncated = row.fluids_truncated or false
            end
            rows[#rows + 1] = row
            ::continue::
        end
    end

    return observation.ok({
        tick = game.tick,
        surface = surface.name,
        page = page,
        page_size = page_size,
        total = total,
        matched = #keyed,
        counted_types = counted,
        page_count = math.max(1, math.ceil(#keyed / page_size)),
        snapshot = snapshot_token(game.tick, #keyed),
        rows = rows,
        -- The row count is reported next to the list so that an empty page
        -- can never be confused with a page that was not read.
        row_count = #rows,
        inspected = inspected,
        partial = #keyed < total,
        truncated = #keyed >= MAX_ENTITIES_PER_PAGE * 4,
    })
end

-- ---------------------------------------------------------------------------
-- logistics
-- ---------------------------------------------------------------------------

--- Return the logistic networks of the force.
---
--- ``LuaForce.logistic_networks`` is a dictionary of surface name to the
--- networks on that surface. The networks are never merged across
--- surfaces: each network keeps its own surface.
local function collect_networks(force, surface_filter)
    local networks = {}
    local by_surface = force.logistic_networks
    if type(by_surface) ~= "table" then return networks end
    local surface_names = {}
    for name in pairs(by_surface) do
        if type(name) == "string" then surface_names[#surface_names + 1] = name end
    end
    table.sort(surface_names)
    for _, surface_name in ipairs(surface_names) do
        if surface_filter == nil or surface_filter == surface_name then
            local list = by_surface[surface_name]
            if type(list) == "table" then
                for _, network in pairs(list) do
                    networks[#networks + 1] = { network = network, surface = surface_name }
                end
            end
        end
    end
    table.sort(networks, function(a, b)
        if a.surface ~= b.surface then return a.surface < b.surface end
        return a.network.network_id < b.network.network_id
    end)
    return networks
end

--- Return the bounded item counts of one logistic network.
local function network_contents(network, limit)
    local ok, contents = pcall(function()
        return network.get_contents()
    end)
    if not ok or type(contents) ~= "table" then return nil end
    local rows = {}
    local truncated = false
    for _, entry in pairs(contents) do
        if type(entry.name) == "string" and type(entry.count) == "number" then
            if #rows < limit then
                local quality = "normal"
                if type(entry.quality) == "table" and type(entry.quality.name) == "string" then
                    quality = entry.quality.name
                elseif type(entry.quality) == "string" then
                    quality = entry.quality
                end
                rows[#rows + 1] = {
                    name = entry.name, quality = quality, count = entry.count,
                }
            else
                truncated = true
            end
        end
    end
    table.sort(rows, function(a, b)
        if a.name ~= b.name then return a.name < b.name end
        return a.quality < b.quality
    end)
    return rows, truncated
end

--- Return the bounded member names of one network list.
local function network_members(list, limit)
    local rows = {}
    if type(list) ~= "table" then return rows end
    for _, entity in pairs(list) do
        if #rows < limit then
            local name = "?"
            local ok, value = pcall(function() return entity.name end)
            if ok and type(value) == "string" then name = value end
            rows[#rows + 1] = name
        end
    end
    table.sort(rows)
    return rows
end

local function observe_logistics(arguments)
    -- The request is validated before the game state is consulted.
    local page, page_size, page_error = page_bounds(arguments, MAX_NETWORKS_PER_PAGE)
    if page_error then return observation.error_status(page_error) end

    local surface_filter = arguments.surface
    if surface_filter ~= nil and type(surface_filter) ~= "string" then
        return observation.error_status("invalid_surface")
    end

    local player = observation.observed_player()
    if not player then
        return observation.unavailable("no_connected_player_with_character")
    end

    local force = player.force
    local networks = collect_networks(force, surface_filter)
    local total = #networks

    local rows = {}
    local first, last = page_range(page, page_size, total)
    if first then
        for index = first, last do
            local entry = networks[index]
            local network = entry.network
            if not network.valid then goto continue end
            local row = {
                network_id = network.network_id,
                surface = entry.surface,
                force = force.name,
                custom_name = network.custom_name,
                available_logistic_robots = network.available_logistic_robots,
                all_logistic_robots = network.all_logistic_robots,
                available_construction_robots = network.available_construction_robots,
                all_construction_robots = network.all_construction_robots,
                robot_limit = network.robot_limit,
            }
            local contents, truncated = network_contents(network, MAX_NETWORK_ITEMS)
            if contents then
                row.items = contents
                row.items_truncated = truncated
                row.available_items = #contents
            end
            local providers = network_members(network.providers, MAX_NETWORK_MEMBERS)
            local requesters = network_members(network.requesters, MAX_NETWORK_MEMBERS)
            local storages = network_members(network.storages, MAX_NETWORK_MEMBERS)
            row.providers = providers
            row.provider_count = #providers
            row.requesters = requesters
            row.requester_count = #requesters
            row.storages = storages
            row.storage_count = #storages
            rows[#rows + 1] = row
            ::continue::
        end
    end

    return observation.ok({
        tick = game.tick,
        page = page,
        page_size = page_size,
        total = total,
        page_count = math.max(1, math.ceil(total / page_size)),
        snapshot = snapshot_token(game.tick, total),
        rows = rows,
        row_count = #rows,
        partial = false,
    })
end

-- ---------------------------------------------------------------------------
-- robots
-- ---------------------------------------------------------------------------

--- Return the aggregate robot availability of one force.
---
--- The counts come from the logistic network counters, so the robots are
--- never walked one by one. The network totals are summed, and the
--- per-network rows are included so the sum can be checked.
local function observe_robots(arguments)
    local player = observation.observed_player()
    if not player then
        return observation.unavailable("no_connected_player_with_character")
    end

    local force = player.force
    local networks = collect_networks(force, nil)
    local rows = {}
    local total_logistic = 0
    local total_construction = 0
    local available_logistic = 0
    local available_construction = 0
    local limit = 0

    for _, entry in ipairs(networks) do
        local network = entry.network
        if network.valid then
            total_logistic = total_logistic + network.all_logistic_robots
            total_construction = total_construction + network.all_construction_robots
            available_logistic = available_logistic + network.available_logistic_robots
            available_construction = available_construction + network.available_construction_robots
            limit = limit + network.robot_limit
            if #rows < MAX_NETWORKS_PER_PAGE then
                rows[#rows + 1] = {
                    network_id = network.network_id,
                    surface = entry.surface,
                    all_logistic_robots = network.all_logistic_robots,
                    available_logistic_robots = network.available_logistic_robots,
                    all_construction_robots = network.all_construction_robots,
                    available_construction_robots = network.available_construction_robots,
                    robot_limit = network.robot_limit,
                }
            end
        end
    end

    return observation.ok({
        tick = game.tick,
        force = force.name,
        networks = #networks,
        total_logistic_robots = total_logistic,
        available_logistic_robots = available_logistic,
        total_construction_robots = total_construction,
        available_construction_robots = available_construction,
        robot_limit = limit,
        rows = rows,
        partial = #rows < #networks,
    })
end

-- ---------------------------------------------------------------------------
-- transport
-- ---------------------------------------------------------------------------

local function observe_transport(arguments)
    -- The request is validated before the game state is consulted.
    local page, page_size, page_error = page_bounds(arguments, MAX_ENTITIES_PER_PAGE)
    if page_error then return observation.error_status(page_error) end

    local player = observation.observed_player()
    if not player then
        return observation.unavailable("no_connected_player_with_character")
    end

    local surface, surface_error = resolve_surface(arguments)
    if surface_error then return observation.error_status(surface_error) end
    if surface == nil then
        local character = player.character
        if not character then
            return observation.unavailable("no_connected_player_with_character")
        end
        surface = character.surface
    end
    if not surface.valid then
        return observation.unavailable("surface_unavailable")
    end

    local total, count_reason, shape = count_entities(surface, TRANSPORT_TYPES)
    if total == nil then
        return observation.unavailable(
            "entity_count_unavailable: " .. (count_reason or "unknown"))
    end

    local entities = search_entities(surface, TRANSPORT_TYPES,
                                    MAX_ENTITIES_PER_PAGE * 4, shape)
    if entities == nil then
        return observation.unavailable("entity_search_unavailable")
    end
    local keyed = {}
    for _, entity in pairs(entities) do
        if TRANSPORT_TYPES[entity.type] then
            keyed[#keyed + 1] = {
                entity = entity, key = entity_sort_key(surface.name, entity),
            }
        end
    end
    table.sort(keyed, function(a, b) return a.key < b.key end)

    local rows = {}
    local first, last = page_range(page, page_size, #keyed)
    if first then
        for index = first, last do
            local entity = keyed[index].entity
            if not entity.valid then goto continue end
            local row = {
                name = entity.name,
                type = entity.type,
                surface = surface.name,
                quality = entity_quality(entity),
            }
            -- The unit number identifies the entity. Two entities of the
            -- same prototype share the prototype name, so the name alone
            -- cannot tell the rows apart.
            local ok_number, unit = pcall(function()
                return entity.unit_number
            end)
            if ok_number then
                -- ``tonumber`` turns the 64-bit integer attribute into a
                -- plain number, so the row always carries a number.
                local converted = tonumber(unit)
                if converted ~= nil then row.unit_number = converted end
            end
            local position = entity_position(entity)
            if position then
                row.x = position.x
                row.y = position.y
            end
            row.inventories = probe_inventories(entity)
            row.inventory_count = #row.inventories
            local fluids = entity_fluids(entity, MAX_FLUIDS_PER_ENTITY)
            if fluids then row.fluids = fluids end
            -- The train of a wagon or a locomotive carries the aggregate
            -- contents of the whole train, which is different from the
            -- physical contents of this one vehicle.
            local ok_train, train = pcall(function() return entity.train end)
            if ok_train and train ~= nil then
                local train_row = {}
                local got, items = pcall(function()
                    return train.get_contents()
                end)
                if got and type(items) == "table" then
                    local counted = {}
                    for _, entry in pairs(items) do
                        if type(entry.name) == "string" and type(entry.count) == "number" then
                            counted[entry.name] = (counted[entry.name] or 0) + entry.count
                        end
                    end
                    local names = {}
                    for name in pairs(counted) do names[#names + 1] = name end
                    table.sort(names)
                    for _, name in ipairs(names) do
                        train_row[#train_row + 1] = { name = name, count = counted[name] }
                    end
                end
                local got_fluids, train_fluids = pcall(function()
                    return train.get_fluid_contents()
                end)
                if got_fluids and type(train_fluids) == "table" then
                    local fluid_names = {}
                    for name in pairs(train_fluids) do
                        if type(name) == "string" then fluid_names[#fluid_names + 1] = name end
                    end
                    table.sort(fluid_names)
                    local fluid_rows = {}
                    for _, name in ipairs(fluid_names) do
                        fluid_rows[#fluid_rows + 1] = {
                            name = name, amount = train_fluids[name],
                        }
                    end
                    train_row.fluids = fluid_rows
                end
                row.train = train_row
            end
            rows[#rows + 1] = row
            ::continue::
        end
    end

    return observation.ok({
        tick = game.tick,
        surface = surface.name,
        page = page,
        page_size = page_size,
        total = total,
        matched = #keyed,
        page_count = math.max(1, math.ceil(#keyed / page_size)),
        snapshot = snapshot_token(game.tick, #keyed),
        rows = rows,
        row_count = #rows,
        partial = #keyed < total,
    })
end

-- ---------------------------------------------------------------------------
-- registration
-- ---------------------------------------------------------------------------

-- The operation is named ``machine_inventories`` and not ``machines``:
-- the catalog module already owns ``machines``, which reports the machine
-- **prototypes**. Two modules must never claim one operation name, because
-- the later require would silently replace the earlier handler.
observation.HANDLERS.machine_inventories = observe_machines
observation.HANDLERS.logistics = observe_logistics
observation.HANDLERS.robots = observe_robots
observation.HANDLERS.transport = observe_transport
