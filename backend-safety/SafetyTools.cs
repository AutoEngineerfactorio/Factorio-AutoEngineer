using System.ComponentModel;
using System.Text.Json;
using FactorioMCP.Rcon;
using FactorioMCP.Services;
using ModelContextProtocol.Server;

namespace FactorioMCP.Tools;

// Safety calls bypass GameCommandQueue so a queued walk cannot delay a stop.
// The RCON client's own connection lock still applies; expiry handles transport loss.
[McpServerToolType]
internal sealed class SafetyTools(RconClient rcon)
{
    private static string Owner(string owner)
    {
        if (!Guid.TryParseExact(owner, "N", out _))
            throw new ArgumentException("Invalid safety session identifier");
        return JsonSerializer.Serialize(owner);
    }

    [McpServerTool(Name = "autoengineer_arm"), Description("Arm a short movement lease for a supervised AutoEngineer session.")]
    public Task<string> Arm(string owner, CancellationToken cancellationToken = default)
    {
        var id = Owner(owner);
        return rcon.ExecuteLuaAsync(FactorioService.LuaOnTickHandler + $$"""

            local old = storage.autoengineer_safety
            if old and not old.stopped and game.tick < old.deadline and old.owner ~= {{id}} then
                rcon.print('{"version":1,"status":"busy"}') return
            end
            local p = game.connected_players[1]
            if #game.connected_players ~= 1 or not p or not p.character or not p.character.valid then
                rcon.print('{"version":1,"status":"single_player_required"}') return
            end
            storage.walk_dir = nil
            storage.mine_state = nil
            p.walking_state = {walking=false, direction=defines.direction.north}
            p.mining_state = {mining=false}
            storage.operation=nil
            storage.autoengineer_safety = {owner={{id}}, player=p.index, deadline=game.tick+120, stopped=false}
            rcon.print('{"version":1,"status":"active"}')
            """, cancellationToken);
    }

    [McpServerTool(Name = "autoengineer_renew"), Description("Renew an unexpired AutoEngineer movement lease; never revive a stopped lease.")]
    public Task<string> Renew(string owner, CancellationToken cancellationToken = default)
    {
        var id = Owner(owner);
        return rcon.ExecuteLuaAsync($$"""
            local s = storage.autoengineer_safety
            local p = game.connected_players[1]
            if not s or s.owner ~= {{id}} or s.stopped or game.tick >= s.deadline or #game.connected_players ~= 1 or not p or p.index ~= s.player then
                rcon.print('{"version":1,"status":"expired"}') return
            end
            s.deadline = game.tick + 120
            rcon.print('{"version":1,"status":"active"}')
            """, cancellationToken);
    }

    [McpServerTool(Name = "autoengineer_stop"), Description("Latch stop and clear game-side walking/mining for the owning AutoEngineer session.")]
    public Task<string> Stop(string owner, CancellationToken cancellationToken = default)
    {
        var id = Owner(owner);
        return rcon.ExecuteLuaAsync($$"""
            local s = storage.autoengineer_safety
            if not s or s.owner ~= {{id}} then
                rcon.print('{"version":1,"status":"not_owner"}') return
            end
            s.stopped = true
            storage.walk_dir = nil
            storage.mine_state = nil
            local p = game.get_player(s.player)
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
            if p and p.valid then
                p.walking_state = {walking=false, direction=defines.direction.north}
                p.mining_state = {mining=false}
                if p.walking_state.walking then
                    rcon.print('{"version":1,"status":"unconfirmed"}') return
                end
            end
            rcon.print('{"version":1,"status":"stopped","walking":false}')
            """, cancellationToken);
    }
    [McpServerTool(Name = "autoengineer_status"), Description("Read owning lease movement state outside the gameplay queue.")]
    public Task<string> Status(string owner, CancellationToken cancellationToken = default)
    {
        var id = Owner(owner);
        return rcon.ExecuteLuaAsync($$"""
            local s = storage.autoengineer_safety
            local p = s and game.get_player(s.player)
            if not s or s.owner ~= {{id}} or s.stopped or game.tick >= s.deadline or not p or not p.character or #game.connected_players ~= 1 then
                rcon.print('{"version":1,"status":"inactive"}') return
            end
            rcon.print(helpers.table_to_json({version=1,status="active",x=p.position.x,y=p.position.y,tick=game.tick,walking=p.walking_state.walking}))
            """, cancellationToken);
    }
}
