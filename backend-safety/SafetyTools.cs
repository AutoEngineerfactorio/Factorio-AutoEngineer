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
}
