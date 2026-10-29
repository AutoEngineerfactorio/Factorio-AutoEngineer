using System.Text.Json;
using FactorioMCP.Rcon;

namespace FactorioMCP.Tools;

/// <summary>
/// Composes the dashboard's view frame from the mod's read-only observations.
///
/// The backend never asks the game for one enormous scan. It asks the
/// registered <c>autoengineer-observe</c> mod command for the small pieces it
/// needs and merges them here into the frame shape the dashboard has always
/// consumed.
///
/// Every request is a fixed command with a validated operation selector, so
/// nothing in this path is a Lua console command and nothing can widen a
/// read. A missing or incompatible mod raises and the tool fails closed.
/// </summary>
internal sealed class ViewComposer(RconClient rcon)
{
    /// <summary>
    /// Compose the fast view frame: the player, the surface, the inventory and
    /// the control lease. It never reads terrain, entities or the catalog.
    /// </summary>
    public async Task<string> ComposeFast(CancellationToken cancellationToken)
    {
        var status = await ModObservation.ObserveAsync(
            rcon, "status", Array.Empty<(string, int)>(), cancellationToken);
        var inventory = await ModObservation.ObserveAsync(
            rcon, "inventory", Array.Empty<(string, int)>(), cancellationToken);
        return Frame(status, inventory, null);
    }

    /// <summary>
    /// Compose the map view frame: the player, the inventory, the terrain
    /// raster, the entities and the overlays of one aligned chunk.
    /// </summary>
    public async Task<string> ComposeMap(
        int chunkX,
        int chunkY,
        CancellationToken cancellationToken)
    {
        var arguments = new (string, int)[] { ("chunk_x", chunkX), ("chunk_y", chunkY) };
        var status = await ModObservation.ObserveAsync(
            rcon, "status", Array.Empty<(string, int)>(), cancellationToken);
        var inventory = await ModObservation.ObserveAsync(
            rcon, "inventory", Array.Empty<(string, int)>(), cancellationToken);
        var terrain = await ModObservation.ObserveAsync(
            rcon, "terrain", arguments, cancellationToken);
        var entities = await ModObservation.ObserveAsync(
            rcon, "map", arguments, cancellationToken);
        var overlays = await ModObservation.ObserveAsync(
            rcon, "overlay", arguments, cancellationToken);
        return Frame(status, inventory, (terrain, entities, overlays));
    }

    /// <summary>
    /// Compose the catalog frame: the player, the surface, the inventory and
    /// one bounded page of the recipe and research catalogs.
    /// </summary>
    public async Task<string> ComposeCatalog(
        int page,
        int pageSize,
        CancellationToken cancellationToken)
    {
        var status = await ModObservation.ObserveAsync(
            rcon, "status", Array.Empty<(string, int)>(), cancellationToken);
        var inventory = await ModObservation.ObserveAsync(
            rcon, "inventory", Array.Empty<(string, int)>(), cancellationToken);
        var arguments = new (string, int)[] { ("page", page), ("page_size", pageSize) };
        var catalog = await ModObservation.ObserveAsync(
            rcon, "capabilities", arguments, cancellationToken);
        // The mod amortizes prototype capture across ticks. Await readiness
        // off the game/UI thread; paused games return explicit pending state.
        for (var attempt = 0; attempt < 32
            && (ReadString(catalog, "reason") as string) == "catalog_building"; attempt++)
        {
            await Task.Delay(250, cancellationToken);
            catalog = await ModObservation.ObserveAsync(
                rcon, "capabilities", arguments, cancellationToken);
        }
        if (!ModObservation.IsUsable(catalog))
        {
            var reason = ReadString(catalog, "reason") as string ?? "catalog_unavailable";
            return JsonSerializer.Serialize(new {
                status = reason == "catalog_building" ? "pending" : "unavailable",
                reason,
            });
        }
        var frame = JsonSerializer.Deserialize<Dictionary<string, object?>>(
            Frame(status, inventory, null))!;
        frame["capabilities"] = null;
        frame["catalog_status"] = new { status = "unavailable", page, page_size = pageSize };
        if (ModObservation.IsUsable(catalog)
            && catalog.TryGetProperty("capabilities", out var rich)
            && rich.ValueKind == JsonValueKind.Object
            && catalog.TryGetProperty("player_status", out var snapshotStatus)
            && catalog.TryGetProperty("player_inventory", out var snapshotInventory)
            && ModObservation.IsUsable(snapshotStatus)
            && ModObservation.IsUsable(snapshotInventory))
        {
            frame = JsonSerializer.Deserialize<Dictionary<string, object?>>(
                Frame(snapshotStatus, snapshotInventory, null))!;
            frame["capabilities"] = rich;
            frame["catalog_status"] = ReadObject(catalog, "catalog_status");
            frame["tick"] = ReadNumber(rich, "tick");
            frame["surface"] = ReadString(rich, "surface");
        }
        return JsonSerializer.Serialize(frame);
    }

    /// <summary>
    /// Compose the inventory and logistics frame.
    /// </summary>
    /// <remarks>
    /// The four R10-B observations are read here and merged into one
    /// frame. They are read **separately** and **never** merged with each
    /// other: the machine inventories, the logistic networks, the robot
    /// counters and the transport inventories are four distinct facts and
    /// combining them would invent relationships the game never reported.
    ///
    /// Every request is bounded by the mod, so the frame stays small even
    /// in a very large factory. A request that fails contributes an
    /// explicit unavailable marker instead of an empty list, so the
    /// dashboard can tell "not observed" from "observed and empty".
    /// </remarks>
    public async Task<string> ComposeInventory(
        int machinePage,
        int machinePageSize,
        int logisticsPage,
        int logisticsPageSize,
        CancellationToken cancellationToken)
    {
        var status = await ModObservation.ObserveAsync(
            rcon, "status", Array.Empty<(string, int)>(), cancellationToken);
        if (!ModObservation.IsUsable(status))
        {
            return JsonSerializer.Serialize(new {
                status = "unavailable",
                reason = status.TryGetProperty("reason", out var reason)
                    ? reason.GetString()
                    : "observation_unavailable",
                protocol = 1,
            });
        }

        var pageArguments = new (string, int)[]
        {
            ("page", machinePage), ("page_size", machinePageSize),
        };
        var logisticsArguments = new (string, int)[]
        {
            ("page", logisticsPage), ("page_size", logisticsPageSize),
        };

        var machines = await ModObservation.ObserveAsync(
            rcon, "machine_inventories", pageArguments, cancellationToken);
        var logistics = await ModObservation.ObserveAsync(
            rcon, "logistics", logisticsArguments, cancellationToken);
        var robots = await ModObservation.ObserveAsync(
            rcon, "robots", Array.Empty<(string, int)>(), cancellationToken);
        var transport = await ModObservation.ObserveAsync(
            rcon, "transport", pageArguments, cancellationToken);

        var frame = new Dictionary<string, object?>
        {
            ["status"] = "ok",
            ["protocol"] = 1,
            ["tick"] = ReadNumber(status, "tick"),
            ["surface"] = ReadString(status, "surface"),
            ["machine_inventories"] = Section(machines),
            ["logistics"] = Section(logistics),
            ["robots"] = Section(robots),
            ["transport"] = Section(transport),
        };
        return JsonSerializer.Serialize(frame);
    }

    /// <summary>
    /// Return one observation section of the frame.
    /// </summary>
    /// <remarks>
    /// A section that the mod could not produce keeps its own status and
    /// reason, so an unavailable section is never shown as an empty one.
    /// </remarks>
    private static Dictionary<string, object?> Section(JsonElement observation)
    {
        if (!ModObservation.IsUsable(observation))
        {
            return new Dictionary<string, object?>
            {
                ["available"] = false,
                ["status"] = "unavailable",
                ["reason"] = observation.TryGetProperty("reason", out var reason)
                    ? reason.GetString()
                    : "observation_unavailable",
            };
        }
        var section = new Dictionary<string, object?>
        {
            ["available"] = true,
            ["status"] = "ok",
        };
        foreach (var name in new[]
        {
            "tick", "surface", "force", "page", "page_size", "total",
            "page_count", "row_count", "matched", "inspected", "partial",
            "truncated", "snapshot", "networks", "total_logistic_robots",
            "available_logistic_robots", "total_construction_robots",
            "available_construction_robots", "robot_limit",
        })
        {
            if (observation.TryGetProperty(name, out var value))
            {
                section[name] = value.ValueKind switch
                {
                    JsonValueKind.Number => value.GetDouble(),
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.String => value.GetString(),
                    _ => value,
                };
            }
        }
        foreach (var name in new[] { "rows" })
        {
            if (observation.TryGetProperty(name, out var value)
                && value.ValueKind == JsonValueKind.Array)
            {
                section[name] = value.EnumerateArray()
                    .Select(item => (object)item).ToArray();
            }
        }
        return section;
    }

    /// <summary>
    /// Build the shared part of a view frame.
    /// </summary>
    private static string Frame(
        JsonElement status,
        JsonElement inventory,
        (JsonElement Terrain, JsonElement Entities, JsonElement Overlays)? map)
    {
        if (!ModObservation.IsUsable(status))
        {
            return JsonSerializer.Serialize(new {
                status = "unavailable",
                reason = status.TryGetProperty("reason", out var reason)
                    ? reason.GetString()
                    : "observation_unavailable",
                protocol = 1,
            });
        }

        var frame = new Dictionary<string, object?>
        {
            ["status"] = "ok",
            ["protocol"] = 1,
            ["gameVersion"] = ReadString(status, "game_version"),
            ["force"] = ReadString(status, "force"),
            ["player"] = new { name = ReadString(status, "player_name") },
            ["tick"] = ReadNumber(status, "tick"),
            ["x"] = ReadNumber(status, "x"),
            ["y"] = ReadNumber(status, "y"),
            ["position"] = Position(status),
            ["surface"] = ReadString(status, "surface"),
            ["inventory"] = ModObservation.IsUsable(inventory)
                ? ReadArray(inventory, "inventory")
                : Array.Empty<object>(),
            ["inventory_available"] = ModObservation.IsUsable(inventory),
            ["truncated"] = false,
            ["capacity"] = ModObservation.IsUsable(inventory)
                ? ReadNumber(inventory, "capacity") : 0,
            ["slots"] = ModObservation.IsUsable(inventory)
                ? ReadArray(inventory, "slots")
                : Array.Empty<object>(),
            ["slots_truncated"] = ModObservation.IsUsable(inventory)
                && inventory.TryGetProperty("slots_truncated", out var truncated)
                && truncated.ValueKind == JsonValueKind.True,
        };
        if (map is not null)
        {
            frame["terrain"] = ComposeTerrain(
                map.Value.Terrain, map.Value.Entities, map.Value.Overlays);
        }
        return JsonSerializer.Serialize(frame);
    }

    /// <summary>
    /// Merge the terrain raster, the entities and the overlays into the one
    /// terrain object the dashboard validates.
    /// </summary>
    /// <summary>
    /// Return the observed player position as one object.
    /// </summary>
    /// <remarks>
    /// The planner validates the position as a single object with an
    /// ``x`` and a ``y``. The frame carries the flat ``x`` and ``y`` as
    /// well, so both spellings are present and neither consumer has to
    /// know which one the other uses.
    /// </remarks>
    private static Dictionary<string, object?> Position(JsonElement status)
    {
        return new Dictionary<string, object?>
        {
            ["x"] = ReadNumber(status, "x"),
            ["y"] = ReadNumber(status, "y"),
        };
    }

    private static Dictionary<string, object?> ComposeTerrain(
        JsonElement terrain,
        JsonElement entities,
        JsonElement overlays)
    {
        var source = terrain.TryGetProperty("terrain", out var inner) ? inner : terrain;
        var merged = new Dictionary<string, object?>
        {
            ["origin"] = ReadObject(source, "origin"),
            ["step"] = ReadNumber(source, "step"),
            ["rows"] = ReadArray(source, "rows"),
            ["palette"] = ReadArray(source, "palette"),
            ["partial"] = ReadBoolean(source, "partial"),
            ["chunk_complete"] = ReadBoolean(source, "chunk_complete"),
            ["map_chunk"] = ReadObject(source, "map_chunk"),
            ["entities"] = ModObservation.IsUsable(entities)
                ? ReadArray(entities, "entities")
                : Array.Empty<object>(),
        };
        if (ModObservation.IsUsable(overlays)
            && overlays.TryGetProperty("overlays", out var layers))
        {
            merged["overlays"] = layers;
        }
        return merged;
    }

    /// <summary>
    /// Build the catalog frame from one bounded page of recipes and research.
    /// </summary>
    private static string CatalogFrame(
        JsonElement status,
        JsonElement inventory,
        JsonElement recipes,
        JsonElement research,
        int page,
        int pageSize)
    {
        if (!ModObservation.IsUsable(status))
        {
            return JsonSerializer.Serialize(new {
                status = "unavailable",
                reason = status.TryGetProperty("reason", out var reason)
                    ? reason.GetString()
                    : "observation_unavailable",
                protocol = 1,
            });
        }
        var frame = new Dictionary<string, object?>
        {
            ["status"] = "ok",
            ["protocol"] = 1,
            ["tick"] = ReadNumber(status, "tick"),
            ["x"] = ReadNumber(status, "x"),
            ["y"] = ReadNumber(status, "y"),
            ["position"] = Position(status),
            ["surface"] = ReadString(status, "surface"),
            ["inventory"] = ModObservation.IsUsable(inventory)
                ? ReadArray(inventory, "inventory")
                : Array.Empty<object>(),
            ["inventory_available"] = ModObservation.IsUsable(inventory),
            ["truncated"] = false,
            ["capacity"] = ModObservation.IsUsable(inventory)
                ? ReadNumber(inventory, "capacity") : 0,
            ["slots"] = ModObservation.IsUsable(inventory)
                ? ReadArray(inventory, "slots")
                : Array.Empty<object>(),
            ["slots_truncated"] = ModObservation.IsUsable(inventory)
                && inventory.TryGetProperty("slots_truncated", out var truncated)
                && truncated.ValueKind == JsonValueKind.True,
            ["catalog_status"] = new Dictionary<string, object?>
            {
                ["page"] = page,
                ["page_size"] = pageSize,
                ["status"] = ModObservation.IsUsable(recipes) ? "ok" : "unavailable",
                ["total"] = ReadNumber(recipes, "total"),
                ["page_count"] = ReadNumber(recipes, "page_count"),
                ["partial"] = ReadBoolean(recipes, "partial"),
            },
            ["capabilities"] = new Dictionary<string, object?>
            {
                ["recipes"] = ModObservation.IsUsable(recipes)
                    ? ReadArray(recipes, "rows")
                    : Array.Empty<object>(),
                ["research"] = ModObservation.IsUsable(research)
                    ? ReadArray(research, "rows")
                    : Array.Empty<object>(),
                ["current_research"] = ReadString(research, "current_research"),
            },
        };
        return JsonSerializer.Serialize(frame);
    }

    private static JsonElement ReadObject(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) ? value : default;

    private static object? ReadNumber(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number
            ? value.GetDouble()
            : null;

    private static object? ReadString(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static bool ReadBoolean(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;

    private static object[] ReadArray(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array
            ? value.EnumerateArray().Select(item => (object)item).ToArray()
            : Array.Empty<object>();
}
