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
        ["autoengineer_view"] = ["catalogPage", "catalogPageSize", "mapChunkX", "mapChunkY", "catalogOnly", "noCatalog"], ["autoengineer_telemetry"] = [], ["autoengineer_policy"] = [], ["get_player_position"] = [],
        ["autoengineer_inventory"] = ["machinePage", "machinePageSize", "logisticsPage", "logisticsPageSize"],
        ["scan_resources"] = ["radius"], ["get_nearby_entities"] = ["radius"],
        ["walk_to_position"] = ["targetX", "targetY", "safetyOwner", "tolerance", "timeoutSeconds"],
        ["autoengineer_status"] = ["owner"], ["autoengineer_arm"] = ["owner"], ["autoengineer_renew"] = ["owner"], ["autoengineer_stop"] = ["owner"]
    };

    [McpServerTool(Name = "autoengineer_policy"), Description("Report the restricted AutoEngineer dispatch policy.")]
    public string Policy() => System.Text.Json.JsonSerializer.Serialize(new {
        version=8, max_walk=5, restricted=true,
        mode=Environment.GetEnvironmentVariable("AUTOENGINEER_BACKEND_MODE") ?? "helper" });

    [McpServerTool(Name = "autoengineer_telemetry"), Description("Read bounded, map-free item flow and local electrical statistics; no terrain, entity-map or recipe scan.")]
    public async Task<string> Telemetry(CancellationToken cancellationToken = default)
    {
        try
        {
            // A registered mod command, not a Lua console command. No client
            // supplied Lua is involved, so nothing here can affect achievements.
            var command = ModObservation.BuildCommand("telemetry");
            var response = await rcon.ExecuteAsync(command, cancellationToken);
            using var document = ModObservation.ParseResponse(response);
            return document.RootElement.GetRawText();
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Return a safe diagnostic rather than a generic MCP invocation failure.
            // Never include RCON commands, exception messages, or credentials.
            return System.Text.Json.JsonSerializer.Serialize(new {
                status = "unavailable", reason = "telemetry_transport_failed",
                error_type = ex.GetType().Name
            });
        }
    }

    [McpServerTool(Name = "autoengineer_view"), Description("Read bounded single-player state, one aligned map chunk and a paged recipe/research catalog; no game actions.")]
    public async Task<string> View(int catalogPage = 1, int catalogPageSize = 16, int mapChunkX = int.MinValue, int mapChunkY = int.MinValue, bool catalogOnly = false, bool noCatalog = false, CancellationToken cancellationToken = default)
    {
        try
        {
            if (catalogOnly)
            {
                if (mapChunkX != int.MinValue || mapChunkY != int.MinValue)
                    throw new ArgumentException("Catalog reads must not request map chunks");
                if (noCatalog)
                    throw new ArgumentException("A catalog read cannot also suppress the catalog");
                return await CatalogOnly(catalogPage, catalogPageSize, cancellationToken);
            }
            // Optional read-only map chunk selection. The chunk indices are the
            // 64-tile aligned grid the dashboard caches. A negative sentinel means
            // "the chunk containing the player", which keeps the old behaviour.
            if ((mapChunkX == int.MinValue) != (mapChunkY == int.MinValue))
                throw new ArgumentException("Map chunk coordinates must be given together");
            if (mapChunkX != int.MinValue && (Math.Abs(mapChunkX) > 100000 || Math.Abs(mapChunkY) > 100000))
                throw new ArgumentException("Map chunk coordinates rejected");
            return await ViewCore(catalogPage, catalogPageSize, mapChunkX, mapChunkY, noCatalog, cancellationToken);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // Return a safe diagnostic rather than an opaque MCP invocation
            // failure. The dashboard must be able to show "unavailable" with a
            // reason instead of an error it cannot explain. The exception text
            // never contains an RCON command, a password or a save path.
            return System.Text.Json.JsonSerializer.Serialize(new {
                status = "unavailable",
                reason = "view_transport_failed",
                error_type = ex.GetType().Name,
                protocol = 1,
            });
        }
    }

    private Task<string> CatalogOnly(int catalogPage, int catalogPageSize, CancellationToken cancellationToken)
    {
        // The catalog page travels over the registered mod command, never as a
        // Lua console command. The composer asks the mod for one bounded page
        // of recipes and one of research and merges them into the frame.
        return new ViewComposer(rcon).ComposeCatalog(catalogPage, catalogPageSize, cancellationToken);
    }

    [McpServerTool(Name = "autoengineer_inventory"), Description("Read bounded machine inventories, logistic networks, robot counts and transport inventories; no game actions.")]
    public async Task<string> Inventory(
        int machinePage = 1,
        int machinePageSize = 16,
        int logisticsPage = 1,
        int logisticsPageSize = 16,
        CancellationToken cancellationToken = default)
    {
        try
        {
            // The pages are bounded on both sides. A page outside the range
            // is refused before the game is touched.
            if (machinePage < 1 || machinePage > 10000)
                throw new ArgumentException("Invalid machine page");
            if (machinePageSize < 1 || machinePageSize > 64)
                throw new ArgumentException("Invalid machine page size");
            if (logisticsPage < 1 || logisticsPage > 10000)
                throw new ArgumentException("Invalid logistics page");
            if (logisticsPageSize < 1 || logisticsPageSize > 64)
                throw new ArgumentException("Invalid logistics page size");
            return await new ViewComposer(rcon).ComposeInventory(
                machinePage, machinePageSize, logisticsPage, logisticsPageSize,
                cancellationToken);
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            // A safe diagnostic, never an opaque MCP invocation failure and
            // never the exception text.
            return System.Text.Json.JsonSerializer.Serialize(new {
                status = "unavailable",
                reason = "inventory_transport_failed",
                error_type = ex.GetType().Name,
                protocol = 1,
            });
        }
    }

    private Task<string> ViewCore(int catalogPage, int catalogPageSize, int mapChunkX, int mapChunkY, bool noCatalog, CancellationToken cancellationToken)
    {
        // The observation travels over the registered mod command, never as a
        // Lua console command. The composer asks the mod for the small
        // pieces it needs and merges them into the dashboard's frame.
        var composer = new ViewComposer(rcon);
        if (noCatalog)
        {
            // The fast path: the player, the surface, the inventory and the
            // control lease. It never reads terrain, entities or the catalog.
            return composer.ComposeFast(cancellationToken);
        }
        // A chunk selection names the chunk to observe. Without one the mod
        // observes the chunk the player is standing in.
        if (mapChunkX == int.MinValue)
        {
            return composer.ComposeFast(cancellationToken);
        }
        return composer.ComposeMap(mapChunkX, mapChunkY, cancellationToken);
    }

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
