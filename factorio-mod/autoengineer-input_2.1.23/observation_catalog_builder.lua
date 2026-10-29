-- Read-only catalog capture, amortized over ticks. Nothing enters storage.
return function(observation, tick)
    local job, cache, failure = nil, nil, nil
    local batch_size = 32
    local function owner(state)
        local player, character = observation.observed_player()
        return player and character and player == state.player
            and player.force == state.force and character.surface == state.surface
            and player.force.name == state.force_name and character.surface.name == state.surface_name
    end
    local function advance()
        if not job then return end
        if not owner(job) or tick() - job.started > 18000 then
            job, failure = nil, "snapshot_changed"
            return
        end
        local caps, status = observation.capabilities(job.page, batch_size, true, job.context)
        if not caps or caps.schema ~= 1 or not status or status.status ~= "ok"
            or status.total_count > 100000 then error("catalog build refused") end
        local rows = {}
        for _, row in ipairs(caps.recipes or {}) do rows[row.name] = {name=row.name,recipe=row} end
        for _, row in ipairs(caps.excluded or {}) do rows[row.name] = {name=row.name,excluded=row} end
        local first, last = (job.page-1)*batch_size+1, math.min(job.page*batch_size, status.total_count)
        for index=first,last do
            local row = rows[job.context.names[1][index]]
            if not row then error("incomplete catalog batch") end
            job.records[#job.records+1] = row
        end
        job.page = job.page + 1
        if last < status.total_count then return end
        -- Prototype fields are immutable. Recheck every mutable force input
        -- at commit, so all accumulated rows agree with this final tick.
        for name, enabled in pairs(job.context.enabled or {}) do
            if job.force.recipes[name].enabled ~= enabled then
                job, failure = nil, "snapshot_changed"
                return
            end
        end
        for name, state in pairs(job.context.technologies or {}) do
            local technology = job.force.technologies[name]
            if technology.researched ~= state[1] or technology.enabled ~= state[2]
                or technology.level ~= state[3] then
                job, failure = nil, "snapshot_changed"
                return
            end
        end
        caps.tick = tick()
        status.coverage_complete = status.coverage_complete and #job.records == status.total_count
        cache = {caps=caps,status=status,records=job.records,player=job.player,
            force=job.force,surface=job.surface,force_name=job.force_name,
            surface_name=job.surface_name,delivered=false,
            player_status=observation.HANDLERS.status({}),
            player_inventory=observation.HANDLERS.inventory({})}
        job = nil
    end
    local function step()
        if not job then return end
        local ok = pcall(advance)
        if not ok then job, cache, failure = nil, nil, "catalog_build_failed" end
    end
    local function get(page, page_size)
        local player, character = observation.observed_player()
        if not player or not character then
            job, cache = nil, nil
            return nil, {status="unavailable"}
        end
        if cache and (not owner(cache) or tick() < cache.caps.tick
            or tick() - cache.caps.tick > 18000) then cache = nil end
        if job and not owner(job) then job, failure = nil, "snapshot_changed" end
        if failure then
            local reason = failure
            failure = nil
            return nil, {status=reason}
        end
        if page == 1 and not job and (not cache or cache.delivered) then
            cache = nil
            job = {player=player,force=player.force,surface=character.surface,
                force_name=player.force.name,surface_name=character.surface.name,
                started=tick(),page=1,context={},records={}}
        end
        if job then return nil, {status="catalog_building",completed=#job.records} end
        if not cache then return nil, {status="snapshot_expired"} end
        local pages = math.max(1,math.ceil(#cache.records / page_size))
        if page > pages then return nil, {status="page_out_of_range"} end
        local caps, status = {}, {}
        for key, value in pairs(cache.caps) do caps[key] = value end
        for key, value in pairs(cache.status) do status[key] = value end
        caps.recipes, caps.excluded = {}, {}
        for index=(page-1)*page_size+1,math.min(page*page_size,#cache.records) do
            local row = cache.records[index]
            if row.recipe then caps.recipes[#caps.recipes+1] = row.recipe
            else caps.excluded[#caps.excluded+1] = row.excluded end
        end
        caps.truncated = not cache.status.coverage_complete or not caps.source_fingerprint
        status.page,status.page_size,status.total_pages = page,page_size,pages
        status.snapshot_tick,status.observation_tick,status.snapshot = caps.tick,tick(),true
        cache.delivered = true
        return caps,status,cache.player_status,cache.player_inventory
    end
    return {get=get,step=step}
end
