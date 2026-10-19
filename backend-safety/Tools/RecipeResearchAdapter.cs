namespace FactorioMCP.Tools;

internal static class RecipeResearchAdapter
{
    internal static string BuildLua(int page, int pageSize)
    {
        if (page is < 1 or > 10000) throw new ArgumentOutOfRangeException(nameof(page));
        if (pageSize is < 1 or > 32) throw new ArgumentOutOfRangeException(nameof(pageSize));

        return $$"""
            local capabilities, catalog_status = nil, {page={{page}},page_size={{pageSize}},status="unavailable"}
            do
                local force, surface = p.force, c.surface
                local game_version = script.active_mods["base"]
                local function sorted_names(source, limit)
                    local names = {}
                    for name in pairs(source) do
                        if type(name) ~= "string" or #name < 1 or #name > 128 then return nil end
                        names[#names+1] = name
                        if #names > limit then return nil end
                    end
                    table.sort(names)
                    return names
                end
                local recipe_names = sorted_names(force.recipes, 10000)
                local technology_names = sorted_names(force.technologies, 10000)
                local mod_names = sorted_names(script.active_mods, 1000)
                if not recipe_names or not technology_names or not mod_names
                    or type(game_version) ~= "string" then
                    catalog_status.status = "catalog_limit"
                else
                    local research, enabled_content = {}, {}
                    local research_truncated = false
                    for _, name in ipairs(technology_names) do
                        local technology = force.technologies[name]
                        if technology.researched then
                            if #research < 256 then research[#research+1] = name
                            else research_truncated = true end
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
                        hash_text(tostring(technology.level))
                    end
                    for _, name in ipairs(recipe_names) do
                        local recipe = force.recipes[name]
                        hash_text("recipe")
                        hash_text(name)
                        hash_text(tostring(recipe.enabled))
                        hash_text(tostring(recipe.hidden))
                        hash_text(tostring(recipe.energy))
                        hash_text(tostring(recipe.category))
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

                    local total, total_pages = #recipe_names, math.ceil(#recipe_names / {{pageSize}})
                    catalog_status = {page={{page}},page_size={{pageSize}},total_count=total,total_pages=total_pages,status="ok"}
                    if {{page}} > total_pages and (total_pages > 0 or {{page}} > 1) then
                        catalog_status.status = "page_out_of_range"
                    else
                        local recipes, recipes_truncated = {}, false
                        local first = ({{page}} - 1) * {{pageSize}} + 1
                        local last = math.min(first + {{pageSize}} - 1, total)
                        local function normalized_parts(source, limit)
                            if type(source) ~= "table" then return nil end
                            local result, count = {}, 0
                            for key, part in pairs(source) do
                                if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then return nil end
                                count = count + 1
                                if count > limit then return nil end
                                if type(part) ~= "table" or type(part.name) ~= "string"
                                    or #part.name < 1 or #part.name > 128
                                    or (part.type ~= "item" and part.type ~= "fluid")
                                    or type(part.amount) ~= "number" or part.amount <= 0
                                    or part.amount ~= part.amount or part.amount == math.huge then return nil end
                                for field in pairs(part) do
                                    if field ~= "name" and field ~= "type" and field ~= "amount" then return nil end
                                end
                                result[#result+1] = {name=part.name,type=part.type,amount=part.amount}
                            end
                            if count ~= #source then return nil end
                            table.sort(result, function(a,b)
                                if a.name ~= b.name then return a.name < b.name end
                                if a.type ~= b.type then return a.type < b.type end
                                return a.amount < b.amount
                            end)
                            return result
                        end
                        for i=first,last do
                            local name = recipe_names[i]
                            local recipe = force.recipes[name]
                            local ingredients = normalized_parts(recipe.ingredients, 16)
                            local products = normalized_parts(recipe.products, 8)
                            local crafting_time = recipe.energy
                            if ingredients and products and #products > 0 and type(crafting_time) == "number"
                                and type(recipe.category) == "string" and #recipe.category > 0
                                and #recipe.category <= 128
                                and crafting_time > 0 and crafting_time == crafting_time
                                and crafting_time ~= math.huge then
                                local hidden = recipe.hidden == true
                                local simple = recipe.enabled
                                    and not hidden and recipe.category == "crafting"
                                    and #products == 1
                                for _, part in ipairs(ingredients) do if part.type ~= "item" then simple = false end end
                                for _, part in ipairs(products) do if part.type ~= "item" then simple = false end end
                                recipes[#recipes+1] = {
                                    name=name,enabled=recipe.enabled,hidden=hidden,simple=simple,
                                    category=recipe.category,crafting_time=crafting_time,
                                    ingredients=ingredients,products=products}
                            else
                                recipes_truncated = true
                            end
                        end
                        local truncated = research_truncated or #mod_names > 32
                        local fingerprint
                        if fingerprint_complete then
                            fingerprint = "poly31x131-v1:" .. string.format("%010.0f-%010.0f", hash_a, hash_b)
                        else
                            truncated = true
                        end
                        capabilities = {
                            schema=1,game_version=game_version,force=force.name,surface=surface.name,
                            tick=game.tick,research=research,enabled_content=enabled_content,
                            truncated=truncated or recipes_truncated,recipes=recipes,
                            source_fingerprint=fingerprint}
                    end
                end
            end
            """;
    }
}
