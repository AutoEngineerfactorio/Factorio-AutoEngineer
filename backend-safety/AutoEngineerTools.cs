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
        ["autoengineer_view"] = [], ["autoengineer_policy"] = [], ["get_player_position"] = [],
        ["scan_resources"] = ["radius"], ["get_nearby_entities"] = ["radius"],
        ["walk_to_position"] = ["targetX", "targetY", "safetyOwner", "tolerance", "timeoutSeconds"],
        ["autoengineer_status"] = ["owner"], ["autoengineer_arm"] = ["owner"], ["autoengineer_renew"] = ["owner"], ["autoengineer_stop"] = ["owner"]
    };

    [McpServerTool(Name = "autoengineer_policy"), Description("Report the restricted AutoEngineer dispatch policy.")]
    public string Policy() => "{\"version\":4,\"max_walk\":5,\"restricted\":true}";

    [McpServerTool(Name = "autoengineer_view"), Description("Read bounded single-player position and main inventory; no game actions.")]
    public Task<string> View(CancellationToken cancellationToken = default) =>
        rcon.ExecuteLuaAsync("""
            local p = game.connected_players[1]
            if #game.connected_players ~= 1 or not p or not p.character then
                rcon.print('{"status":"unavailable"}') return
            end
            local inv = p.get_main_inventory()
            local items, lookup, truncated = {}, {}, false
            if inv then
                for i=1,math.min(#inv,2000) do
                    local stack = inv[i]
                    if stack.valid_for_read then
                        local quality = stack.quality and stack.quality.name or "normal"
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
            rcon.print(helpers.table_to_json({status="ok",tick=game.tick,x=p.position.x,y=p.position.y,
                surface=p.surface.name,inventory=items,inventory_available=inv~=nil,truncated=truncated}))
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
}
