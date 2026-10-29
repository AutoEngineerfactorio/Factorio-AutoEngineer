-- Single-player-only catalog export with a persistent identity per world/save.
-- Exported pages are namespaced by save identity and mod signature.
local observation = require("observation")
local PAGE_SIZE = 32
local PERIOD = 60

local function mods_signature()
    local names = {}
    for name, version in pairs(script.active_mods) do
        names[#names + 1] = name .. "=" .. version
    end
    table.sort(names)
    return table.concat(names, ";")
end

local function ensure_job()
    storage.ae_export = storage.ae_export or {}
    local job = storage.ae_export
    if not job.id then
        local generator = game.create_random_generator()
        job.id = tostring(game.tick) .. "-" .. tostring(generator(1, 2147483647))
    end
    job.page = job.page or 1
    job.generation = job.generation or 0
    if job.complete == nil then job.complete = false end
    return job
end

local resumed_save = false
script.on_load(function()
    resumed_save = true
end)
script.on_init(function()
    ensure_job()
end)
script.on_configuration_changed(function()
    local job = ensure_job()
    job.page, job.complete, job.signature = 1, false, nil
    job.generation = job.generation + 1
end)

script.on_nth_tick(PERIOD, function()
    if game.is_multiplayer() then return end
    local player = game.connected_players[1]
    if not player or not player.character then return end
    local job = ensure_job()
    if resumed_save then
        resumed_save = false
        if not job.complete then
            job.page = 1
            job.generation = job.generation + 1
        end
    end
    local signature = mods_signature()
    if game.tick % 600 == 0 then
        helpers.write_file("autoengineer/catalog/current.json",
            helpers.table_to_json({save_id=job.id, mod_signature=signature,
                generation=job.generation,
                game_version=script.active_mods.base, tick=game.tick}),
            false, player.index)
    end
    if job.complete then return end
    if job.signature ~= signature then
        job.page, job.complete, job.signature = 1, false, signature
        job.generation = job.generation + 1
    end
    local document = observation.run(
        "capabilities page=" .. job.page .. " page_size=" .. PAGE_SIZE)
    local catalog = document.catalog_status
    if document.status ~= "ok" or not catalog or catalog.status ~= "ok" then
        return
    end
    local prefix = "autoengineer/catalog/" .. job.id ..
        "/g" .. job.generation .. "/"
    helpers.write_file(prefix .. "page-" .. job.page .. ".json",
        helpers.table_to_json(document), false, player.index)
    job.page = job.page + 1
    if catalog.total_pages and job.page > catalog.total_pages then
        job.complete = true
        helpers.write_file(prefix .. "complete.json",
            helpers.table_to_json({
                save_id = job.id, generation = job.generation,
                total_pages = catalog.total_pages,
                game_version = script.active_mods.base,
                mod_signature = signature, tick = game.tick,
            }), false, player.index)
    end
end)

commands.add_command("autoengineer-export-reset",
    "Refresh the single-player AI Helper catalog.",
    function(command)
        if not command.player_index or game.is_multiplayer() then return end
        if storage.ae_export then
            local job = storage.ae_export
            job.page, job.complete = 1, false
            job.generation = (job.generation or 0) + 1
        end
    end)

-- Research unlocks change the enabled recipe set within the same save.
local function invalidate_for_research()
    local job = ensure_job()
    job.page, job.complete = 1, false
    job.generation = job.generation + 1
end
script.on_event(defines.events.on_research_finished, invalidate_for_research)
script.on_event(defines.events.on_research_reversed, invalidate_for_research)
