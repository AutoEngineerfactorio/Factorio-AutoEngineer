using System.Globalization;
using System.Text;
using System.Text.Json;
using FactorioMCP.Rcon;

namespace FactorioMCP.Tools;

/// <summary>
/// Transport for the restricted backend's read-only observations.
///
/// Observations travel over the <c>autoengineer-observe</c> mod command that the
/// <c>autoengineer-input</c> mod registers with <c>commands.add_command()</c>.
/// A registered mod command is not a Lua console command: Factorio does not
/// treat it as achievement-affecting scripting and never asks the operator to
/// confirm that achievements may be disabled.
///
/// The backend therefore never sends <c>/c</c>, <c>/sc</c> or
/// <c>/silent-command</c> on any normal gameplay path. The only string this
/// class builds is the fixed command name plus a validated operation selector
/// and strictly numeric arguments; no client-supplied Lua can reach the game.
/// </summary>
internal static class ModObservation
{
    /// <summary>The registered mod command name. Fixed; never client-supplied.</summary>
    internal const string Command = "/autoengineer-observe";

    /// <summary>The observation protocol version the backend expects back.</summary>
    internal const int ProtocolVersion = 1;

    /// <summary>The complete set of operation selectors the backend may request.</summary>
    /// <remarks>
    /// This list must match the operation names the mod's request parser
    /// accepts in <c>observation_parse.lua</c>. A selector that is missing
    /// here is refused by <see cref="BuildCommand"/>, so a view that needs it
    /// fails closed instead of reading the game.
    ///
    /// The R10-A allowlist drift - the backend missing <c>inventory</c>,
    /// <c>terrain</c> and <c>overlay</c> while the mod accepted them - made
    /// every view fail with an opaque MCP error. The regression test in
    /// <c>tests/test_backend_adapter_contract.py</c> now pins this list
    /// against the mod's parser, so the two can never drift apart again.
    ///
    /// The R10-B inventory and logistics selectors are
    /// <c>machine_inventories</c>, <c>logistics</c>, <c>robots</c> and
    /// <c>transport</c>. <c>machine_inventories</c> is deliberately **not**
    /// called <c>machines</c>: the catalog operation <c>machines</c> reports
    /// the machine prototypes and already owns that name.
    /// </remarks>
    internal static readonly HashSet<string> AllowedOperations = new(StringComparer.Ordinal)
    {
        "status",
        "telemetry",
        "map",
        "terrain",
        "overlay",
        "inventory",
        "recipes",
        "research",
        "machines",
        "capabilities",
        "machine_inventories",
        "logistics",
        "robots",
        "transport",
    };

    /// <summary>
    /// Build the mod-command string for one observation.
    /// </summary>
    /// <param name="operation">
    /// The operation selector. It must be one of <see cref="AllowedOperations"/>.
    /// </param>
    /// <param name="arguments">
    /// Optional numeric arguments. Only integers are accepted, so no argument
    /// can carry Lua source or a command separator.
    /// </param>
    internal static string BuildCommand(string operation, params (string Name, int Value)[] arguments)
    {
        if (!AllowedOperations.Contains(operation))
        {
            throw new ArgumentException("Unknown observation operation", nameof(operation));
        }

        var builder = new StringBuilder(Command);
        builder.Append(' ').Append(operation);
        foreach (var (name, value) in arguments)
        {
            builder.Append(' ').Append(name).Append('=')
                .Append(value.ToString(CultureInfo.InvariantCulture));
        }
        return builder.ToString();
    }

    /// <summary>
    /// Parse the mod's structured response and enforce the protocol contract.
    /// </summary>
    /// <remarks>
    /// The mod answers with a single JSON document. A missing, malformed or
    /// wrong-version document is an error, never a silently empty success, so a
    /// broken observation can never be mistaken for real game data.
    /// </remarks>
    internal static JsonDocument ParseResponse(string? response)
    {
        if (string.IsNullOrWhiteSpace(response))
        {
            throw new InvalidOperationException(
                "The autoengineer-observe mod command returned no response. " +
                "Install and enable autoengineer-input 2.1.23 in the Factorio mod directory.");
        }

        var text = response.Trim();
        if (!text.StartsWith('{'))
        {
            throw new InvalidOperationException(
                "The autoengineer-observe mod command returned a non-JSON response. " +
                "The mod is missing, disabled or incompatible.");
        }

        var document = JsonDocument.Parse(text);
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object)
        {
            document.Dispose();
            throw new InvalidOperationException("The autoengineer-observe response is not a JSON object.");
        }

        if (!root.TryGetProperty("protocol", out var protocol) ||
            protocol.ValueKind != JsonValueKind.Number ||
            protocol.GetInt32() != ProtocolVersion)
        {
            document.Dispose();
            throw new InvalidOperationException(
                "The autoengineer-observe response does not match the supported protocol version.");
        }

        return document;
    }

    /// <summary>
    /// Ask the mod for one observation and return the parsed document.
    /// </summary>
    /// <remarks>
    /// The document is cloned so it stays valid after the reader is disposed.
    /// A missing, disabled or incompatible mod raises, so the caller fails
    /// closed instead of silently falling back to raw Lua execution.
    /// </remarks>
    internal static async Task<JsonElement> ObserveAsync(
        RconClient rcon,
        string operation,
        (string Name, int Value)[] arguments,
        CancellationToken cancellationToken)
    {
        var command = BuildCommand(operation, arguments);
        var response = await rcon.ExecuteAsync(command, cancellationToken);
        using var document = ParseResponse(response);
        return document.RootElement.Clone();
    }

    /// <summary>
    /// Return true when the mod answered with a usable observation.
    /// </summary>
    internal static bool IsUsable(JsonElement document) =>
        document.ValueKind == JsonValueKind.Object
        && document.TryGetProperty("status", out var status)
        && status.ValueKind == JsonValueKind.String
        && status.GetString() == "ok";
}
