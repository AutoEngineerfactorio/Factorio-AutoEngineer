namespace FactorioMCP.Tools;

internal static class RecipeResearchAdapter
{
    internal static string BuildLua(int page, int pageSize, bool catalogOnly = false)
    {
        if (page is < 1 or > 10000) throw new ArgumentOutOfRangeException(nameof(page));
        if (pageSize is < 1 or > 32) throw new ArgumentOutOfRangeException(nameof(pageSize));

        return $$$"""
            local AUTOENGINEER_CATALOG_ONLY={{{(catalogOnly ? "true" : "false")}}}
            local capabilities, catalog_status = nil, {page={{{page}}},page_size={{{pageSize}}},status="unavailable"}
            local telemetry = {schema=1,tick=game.tick,
                production={status="unavailable",reason="Production telemetry not collected"},
                power={status="unavailable",reason="Power telemetry not collected"}}
            do
                local force, surface = p.force, c.surface
                local game_version = script.active_mods["base"]
                local function recipe_categories(recipe)
                    if game_version:match("^2%.1%.") then return recipe.categories end
                    return {recipe.category}
                end
                local function sorted_names(source, limit)
                    -- A large modpack has far more recipes than the base game.
                    -- The name list is the paging index, so it is never capped
                    -- away: it is collected in full and the page count is
                    -- derived from it. The limit only bounds the *memory* of
                    -- one collection pass; exceeding it is reported, not
                    -- fatal, because a partial index would silently hide
                    -- recipes from the catalog.
                    local names = {}
                    local overflow = false
                    for name in pairs(source) do
                        if type(name) ~= "string" or #name < 1 or #name > 128 then return nil end
                        names[#names+1] = name
                        if #names > limit then overflow = true end
                    end
                    table.sort(names)
                    return names, overflow
                end
                local recipe_names, recipe_overflow = sorted_names(force.recipes, 100000)
                local technology_names, technology_overflow = sorted_names(force.technologies, 100000)
                local mod_names, mod_overflow = sorted_names(script.active_mods, 1000)
                if not recipe_names or not technology_names or not mod_names
                    or type(game_version) ~= "string" then
                    catalog_status.status = "catalog_limit"
                else
                    local research, enabled_content = {}, {}
                    local research_truncated, unlock_data_truncated = false, false
                    -- A modpack can carry more names than the collection
                    -- bound. The catalog still pages over the collected names,
                    -- but the overflow is reported so the coverage is not
                    -- presented as complete.
                    if recipe_overflow or technology_overflow then
                        unlock_data_truncated = true
                    end
                    local unlock_by_recipe, effect_count = {}, 0
                    for _, name in ipairs(technology_names) do
                        local technology = force.technologies[name]
                        if technology.researched then
                            if #research < 16384 then research[#research+1] = name
                            else research_truncated = true end
                        end
                        local effects = technology.prototype.effects
                        if type(effects) ~= "table" then
                            unlock_data_truncated = true
                        else
                            for _, effect in ipairs(effects) do
                                effect_count = effect_count + 1
                                if effect_count > 50000 then
                                    unlock_data_truncated = true
                                    break
                                end
                                if type(effect) ~= "table" then
                                    unlock_data_truncated = true
                                elseif effect.type == "unlock-recipe" then
                                    local recipe_name = effect.recipe
                                    if type(recipe_name) ~= "string"
                                        or #recipe_name < 1 or #recipe_name > 128
                                        or not force.recipes[recipe_name] then
                                        unlock_data_truncated = true
                                    else
                                        local candidates = unlock_by_recipe[recipe_name]
                                        if not candidates then
                                            candidates = {}
                                            unlock_by_recipe[recipe_name] = candidates
                                        end
                                        local already_listed = false
                                        for _, candidate in ipairs(candidates) do
                                            if candidate.name == name then
                                                already_listed = true
                                                break
                                            end
                                        end
                                        if not already_listed then
                                            if #candidates < 8 then
                                                candidates[#candidates+1] = {
                                                    name=name,researched=technology.researched,
                                                    enabled=technology.enabled}
                                            else
                                                unlock_data_truncated = true
                                            end
                                        end
                                    end
                                end
                            end
                        end
                    end
                    for i=1,math.min(#mod_names,32) do
                        enabled_content[#enabled_content+1] = mod_names[i]
                    end

                    local hash_a, hash_b, hash_bytes = 2166136261, 2246822519, 0
                    local fingerprint_complete = true
                    local function hash_text(text)
                        if not fingerprint_complete then return end
                        hash_bytes = hash_bytes + #text + 1
                        if hash_bytes > 2000000 then
                            fingerprint_complete = false
                            return
                        end
                        for i=1,#text do
                            local byte = string.byte(text, i)
                            hash_a = (hash_a * 31 + byte) % 4294967291
                            hash_b = (hash_b * 131 + byte) % 4294967279
                        end
                        hash_a = (hash_a * 31 + 10) % 4294967291
                        hash_b = (hash_b * 131 + 10) % 4294967279
                    end
                    hash_text("game")
                    hash_text(game_version)
                    hash_text(force.name)
                    hash_text(surface.name)
                    local canonical_bytes, canonical_nodes = 0, 0
                    local function canonical(value, depth)
                        canonical_nodes = canonical_nodes + 1
                        if canonical_nodes > 100000 or not fingerprint_complete then
                            fingerprint_complete = false
                            return nil
                        end
                        local kind = type(value)
                        if kind == "nil" then return "nil"
                        elseif kind == "boolean" then return kind .. ":" .. tostring(value)
                        elseif kind == "string" then
                            canonical_bytes = canonical_bytes + #value
                            if canonical_bytes > 2000000 then
                                fingerprint_complete = false
                                return nil
                            end
                            return kind .. ":" .. value
                        elseif kind == "number" then
                            if value ~= value or value == math.huge or value == -math.huge then return nil end
                            return "number:" .. string.format("%.17g", value)
                        elseif kind ~= "table" or depth > 5 then return nil end
                        local keys = {}
                        for key in pairs(value) do
                            if type(key) ~= "string" and type(key) ~= "number" then return nil end
                            if type(key) == "string" then
                                canonical_bytes = canonical_bytes + #key
                                if canonical_bytes > 2000000 then
                                    fingerprint_complete = false
                                    return nil
                                end
                            end
                            canonical_nodes = canonical_nodes + 1
                            if canonical_nodes > 100000 then
                                fingerprint_complete = false
                                return nil
                            end
                            keys[#keys+1] = key
                        end
                        table.sort(keys, function(a,b)
                            if type(a) ~= type(b) then return type(a) < type(b) end
                            return tostring(a) < tostring(b)
                        end)
                        local parts = {}
                        for _, key in ipairs(keys) do
                            local child = canonical(value[key], depth + 1)
                            if not child then return nil end
                            parts[#parts+1] = type(key) .. ":" .. tostring(key) .. "=" .. child
                        end
                        return "{" .. table.concat(parts, ";") .. "}"
                    end
                    for _, name in ipairs(mod_names) do
                        hash_text("mod")
                        hash_text(name)
                        hash_text(tostring(script.active_mods[name]))
                    end
                    for _, name in ipairs(technology_names) do
                        local technology = force.technologies[name]
                        hash_text("technology")
                        hash_text(name)
                        hash_text(tostring(technology.researched))
                        hash_text(tostring(technology.enabled))
                        hash_text(tostring(technology.level))
                        if fingerprint_complete then
                            local effects = canonical(technology.prototype.effects, 0)
                            if effects then hash_text(effects)
                            else fingerprint_complete = false end
                        end
                    end
                    for _, name in ipairs(recipe_names) do
                        local recipe = force.recipes[name]
                        hash_text("recipe")
                        hash_text(name)
                        hash_text(tostring(recipe.enabled))
                        hash_text(tostring(recipe.hidden))
                        hash_text(tostring(recipe.energy))
                        local category_list = recipe_categories(recipe)
                        if fingerprint_complete then
                            local category_data = canonical(category_list, 0)
                            if category_data then hash_text(category_data)
                            else fingerprint_complete = false end
                        end
                        if fingerprint_complete then
                            local ingredients = canonical(recipe.ingredients, 0)
                            local products = canonical(recipe.products, 0)
                            if ingredients and products then
                                hash_text(ingredients)
                                hash_text(products)
                            else
                                fingerprint_complete = false
                            end
                        end
                    end

                    local total, total_pages = #recipe_names, math.ceil(#recipe_names / {{{pageSize}}})
                    catalog_status = {page={{{page}}},page_size={{{pageSize}}},total_count=total,total_pages=total_pages,status="ok"}
                    if {{{page}}} > total_pages and (total_pages > 0 or {{{page}}} > 1) then
                        catalog_status.status = "page_out_of_range"
                    else
                        local recipes, recipes_truncated = {}, false
                        local first = ({{{page}}} - 1) * {{{pageSize}}} + 1
                        local last = math.min(first + {{{pageSize}}} - 1, total)
                        local function normalized_parts(source, limit, is_product)
                            if type(source) ~= "table" then return nil end
                            local result, count = {}, 0
                            for key, part in pairs(source) do
                                if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then return nil end
                                count = count + 1
                                if count > limit then return nil end
                                if type(part) ~= "table" or type(part.name) ~= "string"
                                    or #part.name < 1 or #part.name > 128
                                    or (part.type ~= "item" and part.type ~= "fluid")
                                    or type(part.amount) ~= "number"
                                    or part.amount ~= part.amount or part.amount == math.huge then return nil end
                                -- Factorio 2.1 adds quality and probability fields to
                                -- products. They are accepted only for products, only
                                -- with valid bounded values, and they mark the row as
                                -- not deterministic. Unknown fields stay rejected.
                                -- Observed 2.1.23 shapes: affected_by_quality is a
                                -- boolean, independent_probability is a number in
                                -- 0..1, and shared_probability is a {min,max} table.
                                -- A product may legitimately have amount 0 when the
                                -- real yield comes from a probability. An ingredient
                                -- must consume a positive amount.
                                if is_product then
                                    if part.amount < 0 then return nil end
                                else
                                    if part.amount <= 0 then return nil end
                                end
                                local deterministic = true
                                for field, value in pairs(part) do
                                    if field == "name" or field == "type" or field == "amount" then
                                        -- already validated
                                    elseif field == "affected_by_quality" then
                                        if not is_product then return nil end
                                        if type(value) ~= "boolean" then return nil end
                                    elseif field == "independent_probability" then
                                        if not is_product then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value < 0 or value > 1 or value == math.huge then return nil end
                                        if value < 1 then deterministic = false end
                                    elseif field == "shared_probability" then
                                        if not is_product then return nil end
                                        if type(value) ~= "table" then return nil end
                                        local low, high = value.min, value.max
                                        if type(low) ~= "number" or type(high) ~= "number"
                                            or low ~= low or high ~= high
                                            or low < 0 or high > 1
                                            or low > high
                                            or low == math.huge or high == math.huge then return nil end
                                        if high < 1 then deterministic = false end
                                    elseif field == "ignored_by_stats" then
                                        -- Factorio 2.1.23 declares ignored_by_stats as a
                                        -- uint16 on the item prototypes and as a
                                        -- FluidAmount on the fluid prototypes. It is the
                                        -- amount excluded from the production or
                                        -- consumption statistics, so it is a number and
                                        -- is preserved exactly. It is declared on both
                                        -- products and ingredients.
                                        if type(value) ~= "number" or value ~= value
                                            or value < 0 or value == math.huge
                                            or value == -math.huge then return nil end
                                        if part.type == "item" then
                                            -- A uint16 holds a whole number in 0..65535.
                                            if value % 1 ~= 0 or value > 65535 then return nil end
                                        end
                                    elseif field == "spoil_weight" then
                                        -- Ingredient fluid spoilage weight.
                                        if type(value) ~= "number" or value ~= value
                                            or value < 0 or value == math.huge then return nil end
                                    elseif field == "fluidbox_multiplier" or field == "fluidbox_index" then
                                        -- Ingredient fluid-box placement hints.
                                        if type(value) ~= "number" or value ~= value
                                            or value == math.huge or value == -math.huge then return nil end
                                    elseif field == "temperature" then
                                        -- Factorio 2.1.23 fluid temperature. Declared by
                                        -- FluidProductPrototype and FluidIngredientPrototype
                                        -- as a float in degrees Celsius. It is a
                                        -- fluid-only field: an item part carrying one is
                                        -- not a valid 2.1.23 shape.
                                        if part.type ~= "fluid" then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value == math.huge or value == -math.huge then return nil end
                                    elseif field == "minimum_temperature" or field == "maximum_temperature" then
                                        -- Factorio 2.1.23 fluid temperature window, declared
                                        -- by FluidIngredientPrototype only. A recipe that
                                        -- accepts a fluid inside a temperature range is a
                                        -- real mechanic and must not be dropped.
                                        if part.type ~= "fluid" then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value == math.huge or value == -math.huge then return nil end
                                    elseif field == "quality_min" or field == "quality_max" then
                                        -- Factorio 2.1.23 quality bounds, declared by
                                        -- ItemProductPrototype and ItemIngredientPrototype as
                                        -- a QualityID name. A mod may add its own quality
                                        -- tier, so the observed name is kept verbatim and
                                        -- is never checked against the vanilla tiers.
                                        if part.type ~= "item" then return nil end
                                        if type(value) ~= "string" or #value < 1 or #value > 128 then return nil end
                                    elseif field == "quality_change" then
                                        -- Factorio 2.1.23 quality change, declared by
                                        -- ItemProductPrototype and ItemIngredientPrototype as
                                        -- an int8: the number of quality levels the result
                                        -- is adjusted by.
                                        if part.type ~= "item" then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value % 1 ~= 0 or value == math.huge
                                            or value == -math.huge then return nil end
                                    elseif field == "amount_min" or field == "amount_max" then
                                        -- Factorio 2.1.23 quantity range, declared by
                                        -- ItemProductPrototype and FluidProductPrototype as
                                        -- uint16. A ranged product has no fixed yield, so
                                        -- it is marked not deterministic and the bounds are
                                        -- reported instead of a guessed amount.
                                        if not is_product then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value % 1 ~= 0 or value < 0
                                            or value == math.huge or value == -math.huge then return nil end
                                    elseif field == "extra_count_fraction" then
                                        -- Factorio 2.1.23 extra count fraction, declared by
                                        -- ItemProductPrototype as a float: the probability
                                        -- that a craft yields one additional product.
                                        if not is_product then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value < 0 or value > 1 or value == math.huge then return nil end
                                        if value < 1 then deterministic = false end
                                    elseif field == "ignored_by_productivity" then
                                        -- Factorio 2.1.23 productivity restriction, declared
                                        -- by ItemProductPrototype and FluidProductPrototype
                                        -- as a uint16: the amount deducted from a
                                        -- productivity-induced bonus craft.
                                        if not is_product then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value % 1 ~= 0 or value < 0
                                            or value == math.huge or value == -math.huge then return nil end
                                    elseif field == "always_fresh" or field == "reset_freshness_on_craft" then
                                        -- Factorio 2.1.23 freshness flags, declared by
                                        -- ItemProductPrototype as booleans.
                                        if not is_product then return nil end
                                        if type(value) ~= "boolean" then return nil end
                                    elseif field == "percent_spoiled" then
                                        -- Factorio 2.1.23 spoilage, declared by
                                        -- ItemProductPrototype as a float that must be
                                        -- >= 0 and < 1.
                                        if not is_product then return nil end
                                        if type(value) ~= "number" or value ~= value
                                            or value < 0 or value >= 1
                                            or value == math.huge or value == -math.huge then return nil end
                                    elseif field == "optional_fluidbox_indexes" then
                                        -- Factorio 2.1.23 additional fluid boxes, declared
                                        -- by FluidProductPrototype and
                                        -- FluidIngredientPrototype as an array of uint32.
                                        -- A fluid that may occupy more than one box is a
                                        -- real mechanic and must not be dropped.
                                        if part.type ~= "fluid" then return nil end
                                        if type(value) ~= "table" then return nil end
                                        local index_count = 0
                                        for _, index in pairs(value) do
                                            index_count = index_count + 1
                                            if index_count > 16 then return nil end
                                            if type(index) ~= "number" or index ~= index
                                                or index % 1 ~= 0 or index < 0
                                                or index == math.huge or index == -math.huge then return nil end
                                        end
                                    elseif field == "show_details_in_recipe_tooltip" then
                                        -- Factorio 2.1.23 display flag, declared by
                                        -- ProductPrototypeBase, so it belongs to the
                                        -- product prototypes only.
                                        if not is_product then return nil end
                                        if type(value) ~= "boolean" then return nil end
                                    else
                                        return nil
                                    end
                                end
                                local row = {name=part.name,type=part.type,amount=part.amount}
                                if not deterministic then row.deterministic = false end
                                -- Preserve the observed productivity and freshness fields.
                                if part.ignored_by_productivity ~= nil then
                                    row.ignored_by_productivity = part.ignored_by_productivity
                                end
                                if part.always_fresh ~= nil then row.always_fresh = part.always_fresh end
                                if part.reset_freshness_on_craft ~= nil then
                                    row.reset_freshness_on_craft = part.reset_freshness_on_craft
                                end
                                if part.percent_spoiled ~= nil then
                                    row.percent_spoiled = part.percent_spoiled
                                end
                                -- Preserve the observed fluidbox indexes and the
                                -- tooltip display flag.
                                if part.optional_fluidbox_indexes ~= nil then
                                    local indexes = {}
                                    for _, index in pairs(part.optional_fluidbox_indexes) do
                                        indexes[#indexes+1] = index
                                    end
                                    table.sort(indexes)
                                    row.optional_fluidbox_indexes = indexes
                                end
                                if part.show_details_in_recipe_tooltip ~= nil then
                                    row.show_details_in_recipe_tooltip = part.show_details_in_recipe_tooltip
                                end
                                -- Preserve the observed statistics-exclusion amount.
                                if part.ignored_by_stats ~= nil then
                                    row.ignored_by_stats = part.ignored_by_stats
                                end
                                -- Preserve the observed probability fields.
                                -- Factorio 2.1.23 ProductPrototypeBase declares
                                -- independent_probability as a double and
                                -- shared_probability as a {min,max} definition.
                                -- Without these values a probabilistic product
                                -- only reports "deterministic: false", which is
                                -- not enough to compute an expected yield, so
                                -- the observed probability must be preserved.
                                if part.independent_probability ~= nil then
                                    row.independent_probability = part.independent_probability
                                end
                                if part.shared_probability ~= nil then
                                    local shared = part.shared_probability
                                    row.shared_probability = {
                                        min = shared.min, max = shared.max}
                                end
                                -- Preserve the observed quality-affect flag.
                                if part.affected_by_quality ~= nil then
                                    row.affected_by_quality = part.affected_by_quality
                                end
                                -- A quantity range means the yield is not a fixed amount.
                                if part.amount_min ~= nil or part.amount_max ~= nil then
                                    local low, high = part.amount_min, part.amount_max
                                    if type(low) ~= "number" or type(high) ~= "number" then return nil end
                                    if low > high then return nil end
                                    deterministic = false
                                    row.deterministic = false
                                    if low ~= nil then row.amount_min = low end
                                    if high ~= nil then row.amount_max = high end
                                end
                                -- Preserve the observed extra count fraction.
                                if part.extra_count_fraction ~= nil then
                                    row.extra_count_fraction = part.extra_count_fraction
                                end
                                -- Preserve the observed temperature fields verbatim so the
                                -- planner can report the fluid requirement instead of
                                -- guessing it.
                                if part.temperature ~= nil then row.temperature = part.temperature end
                                if part.minimum_temperature ~= nil then
                                    row.minimum_temperature = part.minimum_temperature
                                end
                                if part.maximum_temperature ~= nil then
                                    row.maximum_temperature = part.maximum_temperature
                                end
                                -- Preserve the observed quality bounds and change.
                                if part.quality_min ~= nil then row.quality_min = part.quality_min end
                                if part.quality_max ~= nil then row.quality_max = part.quality_max end
                                if part.quality_change ~= nil then row.quality_change = part.quality_change end
                                result[#result+1] = row
                            end
                            if count ~= #source then return nil end
                            table.sort(result, function(a,b)
                                if a.name ~= b.name then return a.name < b.name end
                                if a.type ~= b.type then return a.type < b.type end
                                return a.amount < b.amount
                            end)
                            return result
                        end
                        -- A recipe that the bounded adapter cannot represent is
                        -- dropped silently. That makes the gap between the
                        -- reported total and the emitted rows impossible to
                        -- explain, so the page reports the dropped names with
                        -- the reason that was actually observed. The reason is
                        -- proven from the game's own recipe prototype; when it
                        -- cannot be proven it stays "unclassified" and is never
                        -- guessed.
                        local accepted_part_fields = {
                            name=true,type=true,amount=true,
                            affected_by_quality=true,independent_probability=true,
                            shared_probability=true,ignored_by_stats=true,
                            spoil_weight=true,fluidbox_multiplier=true,
                            fluidbox_index=true,temperature=true,
                            minimum_temperature=true,maximum_temperature=true,
                            quality_min=true,quality_max=true,quality_change=true,
                            amount_min=true,amount_max=true,extra_count_fraction=true,
                            ignored_by_productivity=true,always_fresh=true,
                            reset_freshness_on_craft=true,percent_spoiled=true,
                            optional_fluidbox_indexes=true,
                            show_details_in_recipe_tooltip=true,
                        }
                        local function part_field_reason(parts, is_product)
                            -- The first unaccepted field on any part, or nil.
                            if type(parts) ~= "table" then return nil end
                            for _, part in pairs(parts) do
                                if type(part) ~= "table" then return nil end
                                for field in pairs(part) do
                                    if not accepted_part_fields[field] then
                                        return "unknown_field:" .. tostring(field)
                                    end
                                end
                                if not is_product then
                                    if type(part.amount) ~= "number" or part.amount <= 0 then
                                        return "ingredient_shape:amount"
                                    end
                                end
                            end
                            return nil
                        end
                        local function exclusion_reason(recipe, ingredients, products,
                                                        crafting_time, category)
                            if type(recipe) ~= "table" then return "recipe_shape" end
                            if type(crafting_time) ~= "number" or crafting_time ~= crafting_time
                                or crafting_time <= 0 or crafting_time == math.huge then
                                return "bad_crafting_time"
                            end
                            if type(category) ~= "string" or #category < 1 or #category > 128 then
                                return "no_category"
                            end
                            if type(recipe.products) ~= "table" or #recipe.products == 0 then
                                return "no_products"
                            end
                            local field_reason = part_field_reason(recipe.products, true)
                                or part_field_reason(recipe.ingredients, false)
                            if field_reason then return field_reason end
                            if ingredients == nil then return "ingredient_shape" end
                            if products == nil then return "product_shape" end
                            if #products == 0 then return "no_products" end
                            return "unclassified"
                        end
                        local excluded = {}
                        for i=first,last do
                            local name = recipe_names[i]
                            local recipe = force.recipes[name]
                            local ingredients = normalized_parts(recipe.ingredients, 16, false)
                            local products = normalized_parts(recipe.products, 8, true)
                            local crafting_time = recipe.energy
                            local category_list = recipe_categories(recipe)
                            -- Factorio 2.1 recipes may declare several categories.
                            -- The first is the primary category; the full bounded
                            -- list is reported alongside it so nothing is hidden.
                            local categories = {}
                            if type(category_list) == "table" then
                                for i = 1, math.min(#category_list, 8) do
                                    local entry = category_list[i]
                                    if type(entry) ~= "string" or #entry < 1 or #entry > 128 then
                                        categories = nil
                                        break
                                    end
                                    categories[#categories+1] = entry
                                end
                                if categories and #category_list > #categories then categories = nil end
                            else
                                categories = nil
                            end
                            local category = categories and #categories > 0 and categories[1] or nil
                            if ingredients and products and #products > 0 and type(crafting_time) == "number"
                                and type(category) == "string" and #category > 0
                                and #category <= 128
                                and crafting_time > 0 and crafting_time == crafting_time
                                and crafting_time ~= math.huge then
                                local hidden = recipe.hidden == true
                                local simple = recipe.enabled
                                    and not hidden and category == "crafting"
                                    and #products == 1
                                for _, part in ipairs(ingredients) do if part.type ~= "item" then simple = false end end
                                for _, part in ipairs(products) do
                                    if part.type ~= "item" then simple = false end
                                    if part.deterministic == false then simple = false end
                                end
                                recipes[#recipes+1] = {
                                    name=name,enabled=recipe.enabled,hidden=hidden,simple=simple,
                                    category=category,categories=categories,
                                    crafting_time=crafting_time,
                                    ingredients=ingredients,products=products,
                                    unlock_technologies=unlock_by_recipe[name] or {}}
                            else
                                recipes_truncated = true
                                -- The dropped recipe is reported with the reason
                                -- that was actually observed, so the gap between
                                -- the declared total and the emitted rows can be
                                -- explained instead of only counted.
                                excluded[#excluded+1] = {
                                    name=name,
                                    reason=exclusion_reason(recipe, ingredients, products,
                                        crafting_time, category)}
                            end
                        end
                        local truncated = research_truncated or unlock_data_truncated or #mod_names > 32
                        -- The machine catalog is what turns a recipe category
                        -- into an actual machine. It is read from the game's
                        -- own entity prototypes, so vanilla, Space Age and
                        -- modded machines are all covered without naming any
                        -- of them. A machine that the game does not expose
                        -- keeps an unknown speed and energy, and the planner
                        -- refuses to invent either.
                        local machines, machines_truncated = {}, false
                        do
                            -- Factorio 2.1.23 exposes the prototype tables
                            -- through the runtime global "prototypes". The live
                            -- 2.1.23 server rejected "game.entity_prototypes"
                            -- with "LuaGameScript doesn't contain key
                            -- entity_prototypes", and the pinned 2.1.23 archive
                            -- declares no such attribute on LuaGameScript.
                            -- "prototypes.entity" is the declared
                            -- LuaPrototypes.entity table.
                            local entity_prototypes = prototypes and prototypes.entity or {}
                            -- Factorio 2.1.23 raises an error when an absent
                            -- prototype member is read, so every optional
                            -- member is read through this safe accessor instead
                            -- of directly. Reading
                            -- LuaEntityPrototype.crafting_speed raises
                            -- "doesn't contain key crafting_speed" on the live
                            -- 2.1.23 server, because the declared speed
                            -- accessor is the METHOD get_crafting_speed and
                            -- not a plain member.
                            local function member(object, key)
                                local ok, value = pcall(function()
                                    return object[key]
                                end)
                                if ok then return value end
                                return nil
                            end
                            local machine_names = {}
                            for name in pairs(entity_prototypes) do
                                -- A prototype is a userdata object, not a table.
                                local categories = member(entity_prototypes[name],
                                    "crafting_categories")
                                if type(categories) == "table"
                                    and next(categories) ~= nil then
                                    machine_names[#machine_names+1] = name
                                end
                            end
                            table.sort(machine_names)
                            for _, name in ipairs(machine_names) do
                                if #machines >= 256 then
                                    machines_truncated = true
                                    break
                                end
                                local prototype = entity_prototypes[name]
                                -- Factorio 2.1.23 declares crafting_categories
                                -- as a dictionary of category name to a boolean,
                                -- not as an array, so the enabled keys are
                                -- collected with pairs and sorted.
                                local categories = {}
                                for category, enabled in pairs(
                                    member(prototype, "crafting_categories") or {}) do
                                    if type(category) == "string" and #category >= 1
                                        and #category <= 128 and enabled then
                                        categories[#categories+1] = category
                                    else
                                        categories = nil
                                        break
                                    end
                                end
                                if categories then table.sort(categories) end
                                -- Factorio 2.1.23 declares the crafting
                                -- speed on LuaEntityPrototype as the METHOD
                                -- get_crafting_speed(quality?), not as a
                                -- plain member. The pinned 2.1.23 runtime
                                -- archive declares no "crafting_speed"
                                -- attribute at all, and the live server
                                -- raised "doesn't contain key crafting_speed"
                                -- when it was read directly. The method is
                                -- therefore called, and only on a prototype
                                -- that actually declares it: the archive
                                -- restricts get_crafting_speed to the
                                -- CraftingMachine and Character subclasses,
                                -- so a prototype without the method is left
                                -- without a speed instead of raising.
                                local speed = nil
                                local has_speed_method = false
                                local ok_method = pcall(function()
                                    has_speed_method = type(prototype.get_crafting_speed)
                                        == "function"
                                end)
                                if ok_method and has_speed_method then
                                    local ok_speed, value = pcall(function()
                                        return prototype.get_crafting_speed()
                                    end)
                                    if ok_speed then speed = value end
                                end
                                local energy = member(prototype, "energy_usage")
                                local speed_known = type(speed) == "number"
                                    and speed == speed and speed ~= math.huge
                                    and speed ~= -math.huge
                                local energy_known = type(energy) == "number"
                                    and energy == energy and energy ~= math.huge
                                    and energy ~= -math.huge
                                if categories then
                                    local row = {name=name,
                                        crafting_categories=categories}
                                    if speed_known then row.crafting_speed = speed end
                                    -- Runtime power is J/tick; the wire contract uses watts.
                                    if energy_known then row.energy_usage = energy * 60 end
                                    local electric = member(prototype, "electric_energy_source_prototype")
                                    local drain = electric and member(electric, "drain")
                                    if type(drain) == "number" and drain == drain
                                        and drain >= 0 and drain < math.huge then
                                        row.energy_drain = drain * 60
                                    end
                                    -- The module slots and the allowed effects
                                    -- decide whether a module or a beacon can
                                    -- change the machine, so they are reported
                                    -- when the game declares them. The 2.1.23
                                    -- runtime API declares no module_slots
                                    -- member on LuaEntityPrototype; the
                                    -- declared names are
                                    -- module_inventory_size (the normal
                                    -- quality slot count) and
                                    -- get_inventory_size(index, quality?) for
                                    -- other qualities, so the slot count is
                                    -- reported only when the game provides
                                    -- one.
                                    local module_slots = member(prototype,
                                        "module_inventory_size")
                                    if type(module_slots) == "number"
                                        and module_slots >= 0
                                        and module_slots == math.floor(module_slots)
                                        and module_slots ~= math.huge then
                                        row.module_slots = module_slots
                                    end
                                    local quality_affects = member(prototype,
                                        "quality_affects_module_slots")
                                    if type(quality_affects) == "boolean" then
                                        row.quality_affects_module_slots = quality_affects
                                    end
                                    local speed_quality = member(prototype,
                                        "crafting_speed_quality_multiplier")
                                    if type(speed_quality) == "table" then
                                        local multipliers = {}
                                        for quality, factor in pairs(speed_quality) do
                                            if type(quality) == "string"
                                                and #quality >= 1 and #quality <= 128
                                                and type(factor) == "number"
                                                and factor == factor
                                                and factor ~= math.huge then
                                                multipliers[quality] = factor
                                            end
                                        end
                                        if next(multipliers) ~= nil then
                                            row.crafting_speed_quality_multiplier = multipliers
                                        end
                                    end
                                    -- The footprint of the machine, in tiles.
                                    -- Factorio 2.1.23 declares the entity
                                    -- size on the prototype as a
                                    -- width/height pair. The planner needs
                                    -- it to lay machines out without
                                    -- overlapping them, so it is reported
                                    -- only when the game declares both
                                    -- dimensions as positive whole
                                    -- numbers. An absent or unusable size
                                    -- is simply not reported: the planner
                                    -- then refuses to place that machine
                                    -- instead of guessing a footprint.
                                    local size = member(prototype, "size")
                                    if type(size) == "table" then
                                        local width = member(size, "x")
                                            or member(size, "width")
                                        local height = member(size, "y")
                                            or member(size, "height")
                                        if type(width) == "number" and type(height) == "number"
                                            and width >= 1 and height >= 1
                                            and width == math.floor(width)
                                            and height == math.floor(height)
                                            and width ~= math.huge and height ~= math.huge
                                            and width <= 64 and height <= 64 then
                                            row.size = {width=width, height=height}
                                        end
                                    end
                                    -- The orientations the machine
                                    -- supports. A prototype has no placed
                                    -- direction, so the planner chooses the
                                    -- orientation and records it.
                                    local directions = member(prototype, "direction")
                                    if type(directions) == "table" then
                                        local supported = {}
                                        for _, value in ipairs(directions) do
                                            if type(value) == "number"
                                                and value == math.floor(value) then
                                                supported[#supported+1] = value
                                            end
                                        end
                                        if #supported > 0 then
                                            table.sort(supported)
                                            row.directions = supported
                                        end
                                    end
                                    local fluidboxes = member(prototype, "fluidbox_prototypes")
                                    if type(fluidboxes) == "table" then
                                        -- Factorio 2.1.23 LuaEntityPrototype
                                        -- declares fluidbox_prototypes, an
                                        -- array of LuaFluidBoxPrototype. The
                                        -- live runtime exposes no fluid_boxes,
                                        -- so the declared name is used here.
                                        local boxes = {}
                                        for _, box in ipairs(fluidboxes) do
                                            local production_type = member(box, "production_type")
                                            local filter = member(box, "filter")
                                            local volume = member(box, "volume")
                                            if type(production_type) == "string" then
                                                local entry = {
                                                    production_type = production_type}
                                                if type(filter) == "string"
                                                    and #filter >= 1 and #filter <= 128 then
                                                    entry.filter = filter
                                                end
                                                if type(volume) == "number" then
                                                    entry.volume = volume
                                                end
                                                boxes[#boxes+1] = entry
                                            end
                                        end
                                        row.fluid_boxes = boxes
                                    end
                                    -- The module and beacon rules are what decide
                                    -- whether a module may change this machine,
                                    -- so the allowed effects and the allowed
                                    -- module categories are reported when the
                                    -- game declares them. Factorio 2.1.23
                                    -- declares both as a DICTIONARY of name to
                                    -- a boolean, so the enabled keys are
                                    -- collected with pairs and sorted.
                                    local effects = member(prototype, "allowed_effects")
                                    if type(effects) == "string" then
                                        row.allowed_effects = {effects}
                                    elseif type(effects) == "table" then
                                        local allowed = {}
                                        for effect, enabled in pairs(effects) do
                                            if type(effect) == "string" and #effect >= 1
                                                and #effect <= 32 and enabled then
                                                allowed[#allowed+1] = effect
                                            end
                                        end
                                        table.sort(allowed)
                                        row.allowed_effects = allowed
                                    end
                                    local module_categories = member(prototype,
                                        "allowed_module_categories")
                                    if type(module_categories) == "table" then
                                        local allowed = {}
                                        for category, enabled in pairs(module_categories) do
                                            if type(category) == "string" and #category >= 1
                                                and #category <= 128 and enabled then
                                                allowed[#allowed+1] = category
                                            end
                                        end
                                        table.sort(allowed)
                                        row.allowed_module_categories = allowed
                                    end
                                    machines[#machines+1] = row
                                end
                            end
                        end
                        local fingerprint
                        if fingerprint_complete then
                            fingerprint = "poly31x131-v1:" .. string.format("%010.0f-%010.0f", hash_a, hash_b)
                        else
                            truncated = true
                        end
                        capabilities = {
                            schema=1,game_version=game_version,force=force.name,surface=surface.name,
                            tick=game.tick,research=research,enabled_content=enabled_content,
                            truncated=truncated or recipes_truncated or machines_truncated,
                            recipes=recipes,
                            excluded=excluded,
                            machines=machines,
                            source_fingerprint=fingerprint}
                    end
                end

                if not AUTOENGINEER_CATALOG_ONLY then
                local function finite_number(value)
                    return type(value) == "number" and value == value
                        and value ~= math.huge and value ~= -math.huge
                end
                local function collect_production(prototypes, statistics, limit, tracked_limit)
                    local names = sorted_names(prototypes, 10000)
                    if not names then return nil, "Prototype catalog exceeds telemetry bounds" end
                    -- Scan the whole finite prototype catalog on each observation.
                    -- Bounded output history is selected only after the global scan.
                    local bucket_count, bucket = 1, 0
                    local first, last = 1, #names
                    local candidates = {}
                    for i=first,last do
                        local name = names[i]
                        local input = statistics.get_flow_count{
                            name=name,category="input",
                            precision_index=defines.flow_precision_index.ten_minutes}
                        local output = statistics.get_flow_count{
                            name=name,category="output",
                            precision_index=defines.flow_precision_index.ten_minutes}
                        if not finite_number(input) or not finite_number(output)
                            or input < 0 or output < 0 then
                            return nil, "Invalid production flow sample"
                        end
                        local score = input + output
                        if score > 0 then
                            candidates[#candidates+1] = {name=name,score=score}
                        end
                    end
                    table.sort(candidates,function(a,b)
                        if a.score ~= b.score then return a.score > b.score end
                        return a.name < b.name
                    end)
                    local result = {}
                    for i=1,math.min(#candidates,tracked_limit) do
                        local name = candidates[i].name
                        local input, output = {}, {}
                        for sample=60,1,-1 do
                            local input_value = statistics.get_flow_count{
                                name=name,category="input",
                                precision_index=defines.flow_precision_index.ten_minutes,
                                sample_index=sample}
                            local output_value = statistics.get_flow_count{
                                name=name,category="output",
                                precision_index=defines.flow_precision_index.ten_minutes,
                                sample_index=sample}
                            if not finite_number(input_value) or not finite_number(output_value)
                                or input_value < 0 or output_value < 0 then
                                return nil, "Invalid production history sample"
                            end
                            input[#input+1] = input_value
                            output[#output+1] = output_value
                        end
                        result[#result+1] = {name=name,input=input,output=output}
                    end
                    return {
                        status="ok",unit="units_per_minute",
                        precision="ten_minutes",sample_interval_seconds=2,
                        sample_count=60,window_seconds=120,
                        prototype_count=#names,candidate_cap=limit,
                        candidate_bucket=bucket+1,candidate_bucket_count=bucket_count,
                        partial=#candidates>tracked_limit,series=result}
                end

                local item_ok, item_result = pcall(function()
                    return collect_production(
                        prototypes.item,
                        force.get_item_production_statistics(surface),10000,16)
                end)
                if item_ok and item_result then
                    telemetry.production.items = item_result
                else
                    telemetry.production.items = {
                        status="unavailable",
                        reason=item_ok and "Item telemetry unavailable" or "Item statistics read failed"}
                end
                local fluid_ok, fluid_result = pcall(function()
                    return collect_production(
                        prototypes.fluid,
                        force.get_fluid_production_statistics(surface),10000,8)
                end)
                if fluid_ok and fluid_result then
                    telemetry.production.fluids = fluid_result
                else
                    telemetry.production.fluids = {
                        status="unavailable",
                        reason=fluid_ok and "Fluid telemetry unavailable" or "Fluid statistics read failed"}
                end
                if (telemetry.production.items.status == "ok"
                    or telemetry.production.fluids.status == "ok") then
                    telemetry.production.status = "ok"
                    telemetry.production.reason = nil -- Clear the initial unavailable reason.
                    if telemetry.production.items.partial or telemetry.production.fluids.partial
                        or telemetry.production.items.status ~= "ok"
                        or telemetry.production.fluids.status ~= "ok" then
                        telemetry.production.status = "partial"
                        telemetry.production.reason = "Active history cap reached or one flow type unavailable"
                    end
                else
                    telemetry.production.status = "unavailable"
                    telemetry.production.reason = "Production statistics unavailable"
                end

                local power_ok, power_result = pcall(function()
                    local ox = math.floor(p.position.x/4)*4-128
                    local oy = math.floor(p.position.y/4)*4-128
                    local area = { {ox,oy}, {ox+256,oy+256} }
                    local found = surface.find_entities_filtered{
                        area=area,force=force,type="electric-pole",limit=129}
                    local networks, network_poles, seen = {}, {}, {}
                    -- The instantaneous LuaElectricNetwork API is the supported
                    -- Factorio 2.1.23 path. The archived 2.0 historical
                    -- statistics fallback has been removed.
                    local partial = #found>128
                    for i=1,math.min(#found,128) do
                        local pole = found[i]
                        if pole.valid
                            and force.is_chunk_visible(surface,{
                                math.floor(pole.position.x/32),math.floor(pole.position.y/32)})
                            and pole.electric_network_id then
                            local id = pole.electric_network_id
                            if not seen[id] then
                                seen[id] = true
                                network_poles[id] = pole
                            end
                        end
                    end
                    local network_ids = {}
                    for id in pairs(network_poles) do
                        network_ids[#network_ids+1] = id
                    end
                    table.sort(network_ids)
                    if #network_ids > 8 then partial = true end
                    for i=1,math.min(#network_ids,8) do
                        local id = network_ids[i]
                        local pole = network_poles[id]
                        local sub_network = pole.electric_network
                        local parent = sub_network and sub_network.parent_network
                        local flow = parent and parent.flow_last_tick
                        if flow then
                            local fields = {
                                "maximum_production","maximum_consumption",
                                "consumption_satisfaction","production_satisfaction",
                                "accumulator_energy","accumulator_capacity"}
                            local row = {network_id=id,tick=game.tick}
                            local valid = true
                            for _,field in ipairs(fields) do
                                local value = flow[field]
                                if not finite_number(value) or value < 0
                                    or (field:find("satisfaction") and value > 1) then
                                    valid = false
                                    break
                                end
                                row[field] = value
                            end
                            if valid then
                                networks[#networks+1] = row
                            else
                                partial = true
                            end
                        else
                            partial = true
                        end
                    end
                    table.sort(networks,function(a,b) return a.network_id < b.network_id end)
                    local reason
                    if #networks == 0 then
                        reason = "No readable visible own electric network in the local chart window"
                    end
                    return {
                        status=#networks==0 and "unavailable" or "ok",
                        reason=reason,
                        unit="joules_per_tick",tick=game.tick,networks=networks,
                        partial=partial}
                end)
                if power_ok and power_result then
                    telemetry.power = power_result
                else
                    telemetry.power = {
                        status="unavailable",unit="joules_per_tick",tick=game.tick,
                        reason="Electric network statistics read failed",networks={},partial=false}
                end
                end -- Catalog-only reads never scan full production or electric networks.
            end
            """;
    }
}
