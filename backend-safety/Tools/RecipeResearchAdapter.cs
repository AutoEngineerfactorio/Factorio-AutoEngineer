namespace FactorioMCP.Tools;

internal static class RecipeResearchAdapter
{
    internal static string BuildLua(int page, int pageSize)
    {
        if (page is < 1 or > 10000) throw new ArgumentOutOfRangeException(nameof(page));
        if (pageSize is < 1 or > 32) throw new ArgumentOutOfRangeException(nameof(pageSize));

        return $$"""
            local capabilities, catalog_status = nil, {page={{page}},page_size={{pageSize}},status="unavailable"}
            local telemetry = {schema=1,tick=game.tick,
                production={status="unavailable",reason="Production telemetry not collected"},
                power={status="unavailable",reason="Power telemetry not collected"}}
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
                    local research_truncated, unlock_data_truncated = false, false
                    local unlock_by_recipe, effect_count = {}, 0
                    for _, name in ipairs(technology_names) do
                        local technology = force.technologies[name]
                        if technology.researched then
                            if #research < 256 then research[#research+1] = name
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
                                    ingredients=ingredients,products=products,
                                    unlock_technologies=unlock_by_recipe[name] or {}}
                            else
                                recipes_truncated = true
                            end
                        end
                        local truncated = research_truncated or unlock_data_truncated or #mod_names > 32
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

                local function finite_number(value)
                    return type(value) == "number" and value == value
                        and value ~= math.huge and value ~= -math.huge
                end
                local function collect_production(prototypes, statistics, limit, tracked_limit)
                    local names = sorted_names(prototypes, 10000)
                    if not names then return nil, "Prototype catalog exceeds telemetry bounds" end
                    local bucket_count = math.max(1, math.ceil(#names / limit))
                    local bucket = math.floor(game.tick / 7200) % math.max(bucket_count, 1)
                    local first = bucket * limit + 1
                    local last = math.min(first + limit - 1, #names)
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
                        partial=#names>limit,series=result}
                end

                local item_ok, item_result = pcall(function()
                    return collect_production(
                        game.item_prototypes,
                        force.get_item_production_statistics(surface),128,4)
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
                        game.fluid_prototypes,
                        force.get_fluid_production_statistics(surface),64,2)
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
                    if telemetry.production.items.partial or telemetry.production.fluids.partial then
                        telemetry.production.status = "partial"
                        telemetry.production.reason = "Only one bounded prototype bucket is sampled"
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
                        status=#networks>0 and "ok" or "unavailable",
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
            end
            """;
    }
}
