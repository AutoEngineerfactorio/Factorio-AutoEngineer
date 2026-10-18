if not remote.interfaces.autoengineer_control then
    remote.add_interface("autoengineer_control",{takeover=function(index)
        local s=storage.autoengineer_safety
        if not s or s.stopped or s.player~=index then return end
        s.stopped=true;s.reason='human_takeover'
        local p=game.get_player(index)
        local c=p and p.character
        local n=storage.autoengineer_nav
        local owned_walk=n and n.owner==s.owner and n.status=='running'
        if owned_walk then n.status='stopped' end
        local op=storage.operation
        if c and c.valid then
            if owned_walk or storage.walk_dir~=nil then c.walking_state={walking=false,direction=defines.direction.north} end
            if storage.mine_state~=nil or (op and not op.status and op.kind=='mine') then c.mining_state={mining=false} end
            if op and not op.status and op.kind=='craft' then
                local q=c.crafting_queue
                local inv=c.get_main_inventory()
                local gained=inv and inv.get_item_count{name=op.name,quality='normal'}-op.initial or 0
                local units=op.name=='copper-cable' and 2 or 1
                local remaining=math.max(0,op.want-math.floor(math.max(0,gained)/units))
                if q and q[1] and q[1].recipe==op.name and remaining>0 then c.cancel_crafting{index=1,count=math.min(q[1].count,remaining)} end
            end
        end
        if op and not op.status then op.status='stopped' end
        storage.walk_dir=nil;storage.mine_state=nil
    end})
end
script.on_event(defines.events.on_tick, function()
    local s = storage.autoengineer_safety
    local p = s and game.get_player(s.player) or game.connected_players[1]
    local selected = game.connected_players[1]
    local active = s and not s.stopped and game.tick < s.deadline
        and #game.connected_players == 1 and selected and selected.index == s.player
        and p and p.valid and p.character and p.character.valid
        and p.controller_type==defines.controllers.character and not p.driving
    if not active then
        if p and p.character and p.character.valid then
            local n=storage.autoengineer_nav
            if (n and n.status=='running') or storage.walk_dir~=nil then p.character.walking_state={walking=false,direction=defines.direction.north} end
            if storage.mine_state~=nil then p.character.mining_state={mining=false} end
        end
        local n=storage.autoengineer_nav
        if n and n.status=='running' then
            n.status='stopped'
            if p and p.valid and p.controller_type==defines.controllers.character then p.walking_state={walking=false,direction=defines.direction.north} end
        end
        local op=storage.operation
    if op and not op.status then
        if op.kind=='craft' and p and p.valid then
            local q=p.crafting_queue
            local inv=p.get_main_inventory()
            local gained=inv and inv.get_item_count{name=op.name,quality='normal'}-op.initial or 0
            local units=op.name=='copper-cable' and 2 or 1
            local remaining=math.max(0,op.want-math.floor(math.max(0,gained)/units))
            if q and q[1] and q[1].recipe==op.name and remaining>0 then
                p.cancel_crafting{index=1,count=math.min(q[1].count,remaining)}
            end
        end
        op.status='stopped'
    end
        if s then s.stopped = true end
        if storage.walk_dir ~= nil or storage.mine_state ~= nil then
            if p and p.valid and p.controller_type==defines.controllers.character then
                p.walking_state = {walking=false, direction=defines.direction.north}
                p.mining_state = {mining=false}
            end
        end
        storage.walk_dir = nil
        storage.mine_state = nil
        return
    end
    local n=storage.autoengineer_nav
    if n and n.status=='running' then
        local function dist(a,b) return ((a.x-b.x)^2+(a.y-b.y)^2)^0.5 end
        local function finish(status)
            n.status=status;storage.walk_dir=nil
            p.walking_state={walking=false,direction=defines.direction.north}
        end
        if n.owner~=s.owner or n.surface~=p.surface.index or game.tick>=n.deadline then
            finish('stopped')
        else
            local pos=p.position
            local delta=dist(pos,n.previous)
            n.travel=n.travel+delta
            if delta>0.001 then n.last_progress=game.tick end
            n.previous={x=pos.x,y=pos.y}
            local speed=p.character_running_speed
            if dist(pos,n.origin)>5 or n.travel>5 then finish('limit_reached')
            elseif dist(pos,n.target)<=n.tolerance then finish('arrived')
            elseif game.tick-n.last_progress>180 then finish('stuck')
            elseif not speed or speed<=0 or speed~=speed then finish('stuck')
            else
                -- Advance only when physically near a corner, never by a projection
                -- that can skip the corner while the player is laterally offset.
                local reach=math.max(0.12,math.min(0.3,speed*0.8))
                while n.index<=#n.route and dist(pos,n.route[n.index])<=reach do n.index=n.index+1 end
                local target=n.route[n.index] or n.target
                local dx,dy=target.x-pos.x,target.y-pos.y
                -- Use Factorio's native sixteen walking directions, avoiding rapid
                -- cardinal/diagonal toggles on shallow bearings. Retain heading on ties.
                local best=nil;local score=math.huge
                for direction=0,15 do
                    local angle=direction*math.pi/8
                    local nx=pos.x+math.sin(angle)*speed
                    local ny=pos.y-math.cos(angle)*speed
                    local value=(target.x-nx)^2+(target.y-ny)^2
                    if n.direction and direction~=n.direction then value=value+0.008 end
                    if value<score-0.000001 or (math.abs(value-score)<0.000001 and direction==n.direction) then
                        best=direction;score=value
                    end
                end
                -- Check the next physical step before permitting it; retain headroom
                -- for fixed-point rounding. No player speed modifier is changed.
                local reserve=math.max(speed,delta)*1.1+0.01
                if n.travel+reserve>5 or dist(pos,n.origin)+reserve>5 then finish('limit_reached')
                else
                    n.direction=best;storage.walk_dir=nil
                    p.walking_state={walking=true,direction=best}
                end
            end
        end
    end
    local d = storage.walk_dir
    if d ~= nil then
        p.walking_state = {walking=true, direction=d}
    end
    local op=storage.operation
    if op and not op.status then
        local inv=p.get_main_inventory()
        local function amount(item) return inv and inv.get_item_count{name=item,quality='normal'} or 0 end
        local gained=amount(op.name)-op.initial
        local status=nil
        if p.surface.index~=op.surface or game.tick>=op.deadline then status='timeout'
        elseif op.kind=='mine' then
            local e=op.entity
            if gained>=op.expected then
                op.resource_after=e and e.valid and e.amount or 0
                status=gained==op.expected and op.resource_initial-op.resource_after==op.expected and 'verified' or 'verification_failed'
            elseif not e or not e.valid or (p.position.x-e.position.x)^2+(p.position.y-e.position.y)^2>4 then status='target_changed'
            else
                p.update_selected_entity(e.position)
                if p.selected~=e then status='target_obstructed'
                else p.mining_state={mining=true,position=e.position} end
            end
        elseif p.crafting_queue_size==0 then
            status=gained==op.expected and op.input_initial-amount(op.input)==op.input_expected and 'verified' or 'verification_failed'
        end
        if status then
            if op.kind=='craft' and p.crafting_queue_size>0 then
                local q=p.crafting_queue
                local units=op.name=='copper-cable' and 2 or 1
                local remaining=math.max(0,op.want-math.floor(math.max(0,gained)/units))
                if q and q[1] and q[1].recipe==op.name and remaining>0 then p.cancel_crafting{index=1,count=math.min(q[1].count,remaining)} end
            end
            op.status=status;op.after=amount(op.name);op.input_after=amount(op.input)
            storage.mine_state=nil;p.mining_state={mining=false}
        end
    end
    if storage.mine_state and not storage.mine_state.operation then
        p.update_selected_entity(storage.mine_state.position)
        p.mining_state = {mining=true, position=storage.mine_state.position}
    end
end)
