using FactorioMCP.Services;
using ModelContextProtocol.Server;
using System.ComponentModel;

namespace FactorioMCP.Tools;

[McpServerToolType]
internal sealed class AutoEngineerTools(FactorioService factorio, PathfindingService pathfinding, GameCommandQueue queue)
{
    internal static readonly Dictionary<string, string[]> Allowed = new()
    {
        ["autoengineer_policy"] = [], ["get_player_position"] = [],
        ["scan_resources"] = ["radius"], ["get_nearby_entities"] = ["radius"],
        ["walk_to_position"] = ["targetX", "targetY", "safetyOwner", "tolerance", "timeoutSeconds"],
        ["autoengineer_status"] = ["owner"], ["autoengineer_arm"] = ["owner"], ["autoengineer_renew"] = ["owner"], ["autoengineer_stop"] = ["owner"]
    };

    [McpServerTool(Name = "autoengineer_policy"), Description("Report the restricted AutoEngineer dispatch policy.")]
    public string Policy() => "{\"version\":3,\"max_walk\":5,\"restricted\":true}";

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
