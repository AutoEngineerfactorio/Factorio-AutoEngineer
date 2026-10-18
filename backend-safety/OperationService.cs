using System.Globalization;
using System.Text.Json;
using FactorioMCP.Rcon;

namespace FactorioMCP.Services;

// Starter operations only. No building/entity mining, recursive crafting or arbitrary Lua.
internal sealed class OperationService(RconClient rcon)
{
    internal static void Validate(string kind, string name, int count)
    {
        if (count < 1 || count > 3 ||
            !(kind == "mine" && new[] { "iron-ore", "copper-ore", "coal", "stone" }.Contains(name) ||
              kind == "craft" && new[] { "iron-gear-wheel", "copper-cable" }.Contains(name)))
            throw new ArgumentException("Operation outside starter allowlist or count 1..3");
    }

    private string Prelude(string kind, string name, int count) => $$"""
        local kind,name,want = {{JsonSerializer.Serialize(kind)}},{{JsonSerializer.Serialize(name)}},{{count}}
        local p=game.connected_players[1]
        local function reply(status,extra)
            local out=extra or {}; out.status=status; rcon.print(helpers.table_to_json(out))
        end
        if #game.connected_players~=1 or not p or not p.character then reply('single_player_required') return end
        local inv=p.get_main_inventory()
        if not inv then reply('no_inventory') return end
        local function amount(item) return inv.get_item_count{name=item,quality='normal'} end
        local input=kind=='craft' and (name=='iron-gear-wheel' and 'iron-plate' or 'copper-plate') or name
        local units=name=='iron-gear-wheel' and 2 or 1
        local output_units=name=='copper-cable' and 2 or 1
        """;

    public Task<string> Preview(string kind, string name, int count, CancellationToken ct)
    {
        Validate(kind, name, count);
        return rcon.ExecuteLuaAsync(Prelude(kind,name,count) + """
            if p.walking_state.walking or p.mining_state.mining or p.crafting_queue_size>0 then reply('busy') return end
            if not inv.can_insert{name=name,count=want*output_units,quality='normal'} then reply('inventory_full') return end
            if kind=='craft' then
                local recipe=p.force.recipes[name]
                if not recipe or not recipe.enabled then reply('recipe_unavailable') return end
                if amount(input)<want*units then reply('missing_materials') return end
                if p.get_craftable_count(name)<want then reply('not_handcraftable') return end
                reply('ready',{kind=kind,name=name,count=want,product_before=amount(name),input_before=amount(input),expected=want*output_units,x=p.position.x,y=p.position.y})
            else
                local nearest=nil;local distance=math.huge
                for _,e in pairs(p.surface.find_entities_filtered{position=p.position,radius=2,type='resource',name=name,limit=128}) do
                    local d=(e.position.x-p.position.x)^2+(e.position.y-p.position.y)^2
                    if e.valid and e.minable and e.amount>=want and d<distance then nearest=e;distance=d end
                end
                if not nearest then reply('no_nearby_resource') return end
                reply('ready',{kind=kind,name=name,count=want,product_before=amount(name),expected=want,targetX=nearest.position.x,targetY=nearest.position.y,x=p.position.x,y=p.position.y})
            end
            """, ct);
    }

    public async Task<string> Execute(string kind, string name, int count, string owner, double x, double y, CancellationToken ct)
    {
        Validate(kind,name,count);
        if (!Guid.TryParseExact(owner,"N",out _) || !double.IsFinite(x) || !double.IsFinite(y))
            throw new ArgumentException("Invalid owner or target");
        var begin = await rcon.ExecuteLuaAsync(Prelude(kind,name,count) + string.Create(CultureInfo.InvariantCulture,$$"""
            local s=storage.autoengineer_safety
            if not s or s.owner~={{JsonSerializer.Serialize(owner)}} or s.stopped or game.tick>=s.deadline or s.player~=p.index then reply('not_owner') return end
            if p.walking_state.walking or p.mining_state.mining or p.crafting_queue_size>0 or storage.operation then reply('busy') return end
            if not inv.can_insert{name=name,count=want*output_units,quality='normal'} then reply('inventory_full') return end
            local op={owner=s.owner,kind=kind,name=name,want=want,initial=amount(name),input=input,input_initial=amount(input),expected=want*output_units,deadline=game.tick+600,player=p.index,surface=p.surface.index}
            if kind=='craft' then
                local recipe=p.force.recipes[name]
                if not recipe or not recipe.enabled then reply('recipe_unavailable') return end
                if amount(input)<want*units then reply('missing_materials') return end
                if p.get_craftable_count(name)<want then reply('not_handcraftable') return end
                op.input_expected=want*units
                storage.operation=op
                local queued=p.begin_crafting{recipe=name,count=want,silent=true}
                op.queued=queued
                if queued~=want then if queued>0 then p.cancel_crafting{index=1,count=queued} end;storage.operation=nil;reply('queue_rejected') return end
            else
                local tx,ty={{x}},{{y}}
                if (tx-p.position.x)^2+(ty-p.position.y)^2>4 then reply('out_of_range') return end
                local e=p.surface.find_entities_filtered{position={tx,ty},radius=0.01,type='resource',name=name,limit=1}[1]
                if not e or not e.valid or not e.minable or e.amount<want then reply('target_changed') return end
                p.update_selected_entity(e.position)
                if p.selected~=e then reply('target_obstructed') return end
                op.entity=e;op.resource_initial=e.amount
                storage.operation=op
                storage.mine_state={position=e.position,operation=true}
            end
            reply('started')
            """),ct);
        using(var doc=JsonDocument.Parse(begin))
            if(doc.RootElement.GetProperty("status").GetString()!="started") return begin;
        // The guarded on_tick handler completes or stops the operation independently
        // of this process. Cancellation does not leave an unbounded mining loop.
        for(int i=0;i<100;i++)
        {
            await Task.Delay(100,ct);
            var state=await rcon.ExecuteLuaAsync($$"""
                local op=storage.operation
                if op and op.owner~={{JsonSerializer.Serialize(owner)}} then rcon.print('{"status":"not_owner"}') return end
                rcon.print(helpers.table_to_json(op and {status=op.status or 'running',before=op.initial,after=op.after,input_before=op.input_initial,input_after=op.input_after,expected=op.expected,resource_before=op.resource_initial,resource_after=op.resource_after} or {status='stopped'}))
                """,ct);
            using var result=JsonDocument.Parse(state);
            if(result.RootElement.GetProperty("status").GetString()!="running")
            {
                await rcon.ExecuteLuaAsync($"if storage.operation and storage.operation.owner=={JsonSerializer.Serialize(owner)} then storage.operation=nil end; rcon.print('ok')",ct);
                return state;
            }
        }
        throw new TimeoutException("Operation observation timed out; safety cleanup required");
    }
}
