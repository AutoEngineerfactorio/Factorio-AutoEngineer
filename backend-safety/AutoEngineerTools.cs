using FactorioMCP.Services;
using FactorioMCP.Rcon;
using ModelContextProtocol.Server;
using System.ComponentModel;

namespace FactorioMCP.Tools;

[McpServerToolType]
internal sealed class AutoEngineerTools(FactorioService factorio, PathfindingService pathfinding, GameCommandQueue queue, RconClient rcon)
{
    internal static readonly Dictionary<string, string[]> Allowed = new()
    {
        ["autoengineer_operation_preview"] = ["kind", "name", "count"],
        ["autoengineer_operation"] = ["kind", "name", "count", "safetyOwner", "targetX", "targetY"],
        ["autoengineer_view"] = [], ["autoengineer_policy"] = [], ["get_player_position"] = [],
        ["scan_resources"] = ["radius"], ["get_nearby_entities"] = ["radius"],
        ["walk_to_position"] = ["targetX", "targetY", "safetyOwner", "tolerance", "timeoutSeconds"],
        ["autoengineer_status"] = ["owner"], ["autoengineer_arm"] = ["owner"], ["autoengineer_renew"] = ["owner"], ["autoengineer_stop"] = ["owner"]
    };

    [McpServerTool(Name = "autoengineer_policy"), Description("Report the restricted AutoEngineer dispatch policy.")]
    public string Policy() => System.Text.Json.JsonSerializer.Serialize(new {
        version=8, max_walk=5, restricted=true,
        mode=Environment.GetEnvironmentVariable("AUTOENGINEER_BACKEND_MODE") ?? "helper" });

    [McpServerTool(Name = "autoengineer_view"), Description("Read bounded single-player position and main inventory; no game actions.")]
    public Task<string> View(CancellationToken cancellationToken = default) =>
        rcon.ExecuteLuaAsync("""
            local p = game.connected_players[1]
            if #game.connected_players ~= 1 or not p or not p.character then
                rcon.print('{"status":"unavailable"}') return
            end
            local c = p.character
            local inv = c.get_inventory(defines.inventory.character_main)
            local items, lookup, truncated, slots = {}, {}, false, {}
            if inv then
                for i=1,math.min(#inv,2000) do
                    local stack = inv[i]
                    if stack.valid_for_read then
                        local quality = stack.quality and stack.quality.name or "normal"
                        if i<=200 then slots[#slots+1]={slot=i,name=stack.name,quality=quality,count=stack.count} end
                        local key = stack.name .. ":" .. quality
                        local item = lookup[key]
                        if item then item.count = item.count + stack.count
                        elseif #items < 64 then
                            item = {name=stack.name,quality=quality,count=stack.count}
                            lookup[key] = item
                            items[#items+1] = item
                        else truncated = true end
                    end
                end
                if #inv > 2000 then truncated = true end
            end
            -- Display only: do not chart, generate chunks, select entities or change player state.
            local tiles, entities = {}, {}
            local ox,oy=math.floor(c.position.x/4)*4-128,math.floor(c.position.y/4)*4-128
            local function visible(x,y)
                return p.force.is_chunk_visible(c.surface,{math.floor(x/32),math.floor(y/32)})
            end
            local function charted(x,y)
                return p.force.is_chunk_charted(c.surface,{math.floor(x/32),math.floor(y/32)})
            end
            -- Palette-indexed tile rows preserve one-tile detail without huge JSON cell objects.
            local rows,palette,colors,chunks={},{"#000000"},{["#000000"]=0},{}
            for y=oy,oy+255 do
                local row={}
                for x=ox,ox+255 do
                    local cx,cy=math.floor(x/32),math.floor(y/32)
                    local ck=cx..":"..cy
                    local chunk=chunks[ck]
                    if not chunk then
                        chunk={charted=charted(x,y),visible=visible(x,y)};chunks[ck]=chunk
                    end
                    local index=0
                    if chunk.charted then
                        local t=c.surface.get_tile(x,y)
                        local color=t.prototype.map_color
                        local shade=chunk.visible and 1 or 0.6667
                        local hex=string.format("#%02x%02x%02x",math.floor(color.r*shade),math.floor(color.g*shade),math.floor(color.b*shade))
                        index=colors[hex]
                        if not index then
                            if #palette<256 then index=#palette;palette[#palette+1]=hex;colors[hex]=index
                            else index=0 end
                        end
                    end
                    row[#row+1]=string.format("%02x",index)
                end
                rows[#rows+1]=table.concat(row)
            end
            local groups={
                {kind="resource",types={"resource"},limit=2048},
                {kind="nature",types={"tree","simple-entity"},limit=512},
                {kind="building",force=p.force.name,limit=256},
                {kind="enemy",force="enemy",limit=128}}
            local partial=false
            for _,g in ipairs(groups) do
                local found=c.surface.find_entities_filtered{area={{ox,oy},{ox+256,oy+256}},
                    type=g.types,force=g.force,limit=g.limit+1}
                if #found>g.limit then partial=true end
                for i=1,math.min(#found,g.limit) do
                    local e=found[i]
                    if e.valid and e.type~="character" and e.position.x>=ox and e.position.x<ox+256 and e.position.y>=oy and e.position.y<oy+256 and visible(e.position.x,e.position.y) then
                        entities[#entities+1]={x=e.position.x,y=e.position.y,name=e.name,kind=g.kind}
                    end
                end
            end
            -- Optional read-only overlays. No charting, connector creation or world mutation.
            local overlays={schema=1,available={},partial={},player_name=string.sub(p.name,1,128)}
            local area={{ox,oy},{ox+256,oy+256}}
            local function inside(pos)
                return pos.x>=ox and pos.x<ox+256 and pos.y>=oy and pos.y<oy+256
            end
            local function clean(text)
                return string.sub(string.gsub(text or "","%c"," "),1,128)
            end
            local function layer(name,read)
                local ok,result,partial=pcall(read)
                overlays.available[name]=ok
                overlays[name]=ok and result or {}
                overlays.partial[name]=ok and partial==true or false
            end
            layer("pollution",function()
                local result={}
                for cy=math.floor(oy/32),math.floor((oy+255)/32) do
                    for cx=math.floor(ox/32),math.floor((ox+255)/32) do
                        local x,y=math.max(ox,cx*32),math.max(oy,cy*32)
                        if charted(x,y) then
                            result[#result+1]={x=x,y=y,value=c.surface.get_pollution({x,y}),
                                width=math.min(ox+256,(cx+1)*32)-x,height=math.min(oy+256,(cy+1)*32)-y}
                        end
                    end
                end
                return result,false
            end)
            local function own(types,limit,read)
                local found=c.surface.find_entities_filtered{area=area,force=p.force,type=types,limit=limit+1}
                local result={}
                for i=1,math.min(#found,limit) do
                    local e=found[i]
                    if e.valid and inside(e.position) and visible(e.position.x,e.position.y) then read(e,result) end
                end
                return result,#found>limit
            end
            layer("electric",function()
                return own({"electric-pole"},128,function(e,result)
                    local lines={}
                    local connector=e.get_wire_connector(defines.wire_connector_id.pole_copper,false)
                    if connector then
                        for _,wire in pairs(connector.connections) do
                            local target=wire.target.owner
                            if #lines<16 and target.valid and inside(target.position) and visible(target.position.x,target.position.y) then
                                lines[#lines+1]={x=target.position.x,y=target.position.y}
                            end
                        end
                    end
                    result[#result+1]={x=e.position.x,y=e.position.y,radius=e.prototype.get_supply_area_distance(e.quality) or 0,connections=lines}
                end)
            end)
            layer("logistics",function()
                return own({"roboport"},64,function(e,result)
                    local cell=e.logistic_cell
                    if cell and cell.valid then
                        result[#result+1]={x=e.position.x,y=e.position.y,logistic=cell.logistic_radius,construction=cell.construction_radius,active=cell.transmitting}
                    end
                end)
            end)
            layer("turrets",function()
                return own({"ammo-turret","electric-turret","fluid-turret","artillery-turret"},128,function(e,result)
                    result[#result+1]={x=e.position.x,y=e.position.y,radius=e.prototype.turret_range or 0}
                end)
            end)
            layer("stations",function()
                return own({"train-stop"},128,function(e,result)
                    result[#result+1]={x=e.position.x,y=e.position.y,text=clean(e.backer_name)}
                end)
            end)
            layer("tags",function()
                local found=p.force.find_chart_tags(c.surface,area)
                local result={}
                for i=1,math.min(#found,128) do
                    local tag=found[i]
                    if tag.valid and inside(tag.position) and charted(tag.position.x,tag.position.y) then
                        result[#result+1]={x=tag.position.x,y=tag.position.y,text=clean(tag.text),icon=tag.icon and clean(tag.icon.name) or ""}
                    end
                end
                return result,#found>128
            end)
            local lease=storage.autoengineer_safety
            local control={lease_active=lease~=nil and not lease.stopped and game.tick<lease.deadline,walking=c.walking_state.walking,input_adapter=false,generation=0,character_control=p.controller_type==defines.controllers.character and not p.driving}
            if remote.interfaces.autoengineer_input then
                local ok,value=pcall(remote.call,'autoengineer_input','state',p.index)
                if ok and value.version==1 then control.input_adapter=true;control.generation=value.generation end
            end
            rcon.print(helpers.table_to_json({status="ok",tick=game.tick,x=c.position.x,y=c.position.y,
                surface=c.surface.name,control=control,overlays=overlays,inventory=items,inventory_available=inv~=nil,truncated=truncated,
                slots=slots,capacity=inv and #inv or 0,slots_truncated=inv and #inv>200 or false,
                terrain={origin={x=ox,y=oy},step=1,rows=rows,palette=palette,entities=entities,partial=partial}}))
            """, cancellationToken);

    [McpServerTool(Name = "get_player_position"), Description("Read the single connected player's position.")]
    public Task<string> Position(CancellationToken cancellationToken = default) =>
        queue.ExecuteAsync(nameof(Position), pathfinding.GetPlayerPositionAsync, cancellationToken);

    [McpServerTool(Name = "scan_resources"), Description("Scan resources around the player, at most 50 tiles.")]
    public Task<string> Resources(double radius = 50, CancellationToken cancellationToken = default)
    {
        if (!double.IsFinite(radius) || radius <= 0 || radius > 50) throw new ArgumentException("Resource radius rejected");
        return queue.ExecuteAsync(nameof(Resources), ct => factorio.ScanResourcesAsync(radius, null, null, ct), cancellationToken);
    }

    [McpServerTool(Name = "get_nearby_entities"), Description("Read entities around the player, at most 8 tiles.")]
    public Task<string> Nearby(double radius = 8, CancellationToken cancellationToken = default)
    {
        if (!double.IsFinite(radius) || radius <= 0 || radius > 8) throw new ArgumentException("Entity radius rejected");
        return queue.ExecuteAsync(nameof(Nearby), ct => factorio.GetNearbyEntitiesAsync(radius, null, null, ct), cancellationToken);
    }

    [McpServerTool(Name = "walk_to_position"), Description("Execute an approved short walk under the owning safety lease.")]
    public Task<string> Walk(double targetX, double targetY, string safetyOwner,
        double tolerance = 0.75, double timeoutSeconds = 20, CancellationToken cancellationToken = default)
    {
        if (!double.IsFinite(targetX) || !double.IsFinite(targetY) ||
            !double.IsFinite(tolerance) || tolerance <= 0 || tolerance > 0.75 ||
            !double.IsFinite(timeoutSeconds) || timeoutSeconds <= 0 || timeoutSeconds > 20)
            throw new ArgumentException("Movement parameters rejected");
        return queue.ExecuteAsync(nameof(Walk), ct =>
            pathfinding.WalkToAsync(targetX, targetY, tolerance, timeoutSeconds, ct, safetyOwner), cancellationToken);
    }
    [McpServerTool(Name = "autoengineer_operation_preview"), Description("Read preconditions for a starter mining or crafting batch of 1..3.")]
    public Task<string> OperationPreview(string kind, string name, int count = 1, CancellationToken cancellationToken = default) =>
        queue.ExecuteAsync(nameof(OperationPreview), ct => new OperationService(rcon).Preview(kind,name,count,ct), cancellationToken);

    [McpServerTool(Name = "autoengineer_operation"), Description("Execute an approved bounded starter operation under the owning safety lease.")]
    public Task<string> Operation(string kind, string name, int count, string safetyOwner,
        double targetX = 0, double targetY = 0, CancellationToken cancellationToken = default) =>
        queue.ExecuteAsync(nameof(Operation), ct => new OperationService(rcon).Execute(kind,name,count,safetyOwner,targetX,targetY,ct), cancellationToken);

}
