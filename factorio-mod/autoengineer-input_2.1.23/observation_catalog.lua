-- AutoEngineer read-only observation API - catalog.
--
-- The recipe, research and machine observations are paginated and bounded.
-- They enumerate prototypes, which is the expensive part of an observation,
-- so they are never part of a frequent poll: the backend asks for one page
-- on demand.
--
-- Every page reports its own position and the total, and the overflow flag
-- reports that the collection bound was reached, so a partial index is
-- never presented as a complete one.
--
-- Factorio 2.1.23 API only.

local observation = require("observation")

-- The rich recipe/research catalog the read-only planner consumes. It was
-- ported from the backend's recipe/research adapter so the planner keeps
-- receiving the exact shape it validates.
require("observation_capabilities")

-- Hard bounds for one page and for the collected name index.
local MAX_PAGE = 10000
local MAX_RECIPES_PER_PAGE = 32
local MAX_TECHNOLOGIES_PER_PAGE = 32
local MAX_MACHINES_PER_PAGE = 32
local MAX_RECIPE_NAMES = 100000
local MAX_TECHNOLOGY_NAMES = 100000
local MAX_MACHINE_NAMES = 20000

--- Collect and sort the names of a prototype collection.
--- The overflow flag reports that the collection bound was reached, so a
--- partial index is never presented as a complete one.
local function paged_names(source, limit)
    local names = {}
    local overflow = false
    for name in pairs(source) do
        if type(name) ~= "string" or #name < 1 or #name > 128 then return nil, true end
        names[#names + 1] = name
        if #names > limit then overflow = true end
    end
    table.sort(names)
    return names, overflow
end

--- Resolve the requested page and page size.
local function page_bounds(arguments, maximum)
    local page = 1
    local page_size = maximum
    if arguments.page then
        page = observation.integer_argument(arguments.page, 1, MAX_PAGE)
        if page == nil then return nil, nil, "invalid_page" end
    end
    if arguments.page_size then
        page_size = observation.integer_argument(arguments.page_size, 1, maximum)
        if page_size == nil then return nil, nil, "invalid_page_size" end
    end
    return page, page_size, nil
end

--- Return the first and last index of the requested page.
local function page_range(page, page_size, total)
    local first = (page - 1) * page_size + 1
    if first > total then return nil, nil end
    return first, math.min(first + page_size - 1, total)
end

local function observe_recipes(arguments)
    local player = observation.observed_player()
    if not player then
        return observation.unavailable("no_connected_player_with_character")
    end
    local page, page_size, page_error = page_bounds(arguments, MAX_RECIPES_PER_PAGE)
    if page_error then return observation.error_status(page_error) end

    local force = player.force
    local names, overflow = paged_names(force.recipes, MAX_RECIPE_NAMES)
    if not names then
        return observation.error_status("recipe_names_unavailable")
    end
    local rows = {}
    local first, last = page_range(page, page_size, #names)
    if first then
        for index = first, last do
            local name = names[index]
            local recipe = force.recipes[name]
            local row = { name = name, enabled = recipe.enabled }
            if type(recipe.categories) == "table" then
                row.categories = recipe.categories
            end
            row.energy = recipe.energy
            row.ingredients = #recipe.ingredients
            row.products = #recipe.products
            rows[#rows + 1] = row
        end
    end
    return observation.ok({
        page = page,
        page_size = page_size,
        total = #names,
        page_count = math.ceil(#names / page_size),
        rows = rows,
        partial = overflow,
    })
end

local function observe_research(arguments)
    local player = observation.observed_player()
    if not player then
        return observation.unavailable("no_connected_player_with_character")
    end
    local page, page_size, page_error = page_bounds(arguments, MAX_TECHNOLOGIES_PER_PAGE)
    if page_error then return observation.error_status(page_error) end

    local force = player.force
    local names, overflow = paged_names(force.technologies, MAX_TECHNOLOGY_NAMES)
    if not names then
        return observation.error_status("technology_names_unavailable")
    end
    local rows = {}
    local first, last = page_range(page, page_size, #names)
    if first then
        for index = first, last do
            local name = names[index]
            local technology = force.technologies[name]
            local row = {
                name = name,
                researched = technology.researched,
                enabled = technology.enabled,
                level = technology.level,
            }
            if type(technology.prerequisites) == "table" then
                row.prerequisites = technology.prerequisites
            end
            rows[#rows + 1] = row
        end
    end
    return observation.ok({
        page = page,
        page_size = page_size,
        total = #names,
        page_count = math.ceil(#names / page_size),
        current_research = force.current_research,
        rows = rows,
        partial = overflow,
    })
end

local function observe_machines(arguments)
    local player = observation.observed_player()
    if not player then
        return observation.unavailable("no_connected_player_with_character")
    end
    local page, page_size, page_error = page_bounds(arguments, MAX_MACHINES_PER_PAGE)
    if page_error then return observation.error_status(page_error) end

    local names, overflow = paged_names(prototypes.entity, MAX_MACHINE_NAMES)
    if not names then
        return observation.error_status("machine_names_unavailable")
    end
    local rows = {}
    local first, last = page_range(page, page_size, #names)
    if first then
        for index = first, last do
            local name = names[index]
            local prototype = prototypes.entity[name]
            if prototype and prototype.type == "assembling-machine" then
                local row = {
                    name = name,
                    crafting_categories = prototype.crafting_categories,
                    module_slots = prototype.module_inventory_size,
                    energy_usage = prototype.energy_usage * 60,
                    speed = prototype.get_crafting_speed(),
                }
                if prototype.fluidbox_prototypes then
                    local boxes = {}
                    for box_name, box in pairs(prototype.fluidbox_prototypes) do
                        boxes[#boxes + 1] = { name = box_name, volume = box.volume }
                    end
                    table.sort(boxes, function(a, b) return a.name < b.name end)
                    row.fluid_boxes = boxes
                end
                if prototype.allowed_module_categories then
                    row.allowed_module_categories = prototype.allowed_module_categories
                end
                rows[#rows + 1] = row
            end
        end
    end
    return observation.ok({
        page = page,
        page_size = page_size,
        total = #names,
        page_count = math.ceil(#names / page_size),
        rows = rows,
        partial = overflow,
    })
end

observation.HANDLERS.recipes = observe_recipes
observation.HANDLERS.research = observe_research
observation.HANDLERS.machines = observe_machines

--- Read the rich capability envelope the read-only planner consumes.
---
--- The envelope carries the game version, the force, the surface, the tick,
--- the researched technologies, the enabled content, the recipe rows, the
--- machine rows and the source fingerprint. The planner validates every
--- field and fails closed on an unrecognised one.
local function observe_capabilities(arguments)
    local page, page_size, page_error = page_bounds(arguments, 128)
    if page_error then return observation.error_status(page_error) end
    local envelope, status, player_status, player_inventory =
        observation.catalog_snapshot(page, page_size)
    if envelope == nil then
        return observation.unavailable(status and status.status or "catalog_unavailable")
    end
    return observation.ok({
        tick = envelope.tick,
        capabilities = envelope,
        catalog_status = status,
        player_status = player_status,
        player_inventory = player_inventory,
    })
end

observation.HANDLERS.capabilities = observe_capabilities
