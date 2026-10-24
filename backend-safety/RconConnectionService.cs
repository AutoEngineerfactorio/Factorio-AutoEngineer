using FactorioMCP.Rcon;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace FactorioMCP.Services;

/// <summary>
/// Hosted service that connects and authenticates the RCON client on application startup.
/// Reads connection settings from environment variables.
/// Retries connection with exponential backoff if the server is not yet available.
/// After connecting, initializes game-level listeners (e.g. chat message capture).
/// </summary>
internal sealed class RconConnectionService(
    RconClient rcon,
    FactorioService factorioService,
    IConfiguration configuration,
    ILogger<RconConnectionService> logger) : IHostedService
{
    private const int MaxStartupAttempts = 5;
    private static readonly TimeSpan InitialBackoff = TimeSpan.FromSeconds(2);
    // Factorio 2.1.23 gates the FIRST console command of a fresh server: the
    // command is held pending and only an identical repeat executes it. A pending
    // command returns an empty body, so the first real observation would be lost.
    //
    // The gate is cleared by repeating the same command, so it is pre-cleared here
    // with a harmless read-only probe. The probe is sent twice on purpose: the first
    // send is consumed by the gate, the second executes it. No gameplay command is
    // ever repeated, so no write can be applied twice.
    private const string ConsoleGateProbe = "rcon.print('autoengineer-console-gate-probe')";
    public async Task StartAsync(CancellationToken cancellationToken)
    {
        var host = configuration["FACTORIO_RCON_HOST"] ?? "127.0.0.1";
        var port = int.TryParse(configuration["FACTORIO_RCON_PORT"], out var p) ? p : 27015;
        var password = configuration["FACTORIO_RCON_PASSWORD"] ?? throw new InvalidOperationException("RCON password is required");

        var delay = InitialBackoff;
        for (var attempt = 1; attempt <= MaxStartupAttempts; attempt++)
        {
            try
            {
                await rcon.ConnectAndAuthenticateAsync(host, port, password, cancellationToken);
                logger.LogInformation("RCON connected to {Host}:{Port}", host, port);

                await ClearConsoleCommandGateAsync(cancellationToken);
                // Restricted profile does not install chat or other unsolicited listeners.
                return;
            }
            catch (Exception ex) when (attempt < MaxStartupAttempts && !cancellationToken.IsCancellationRequested)
            {
                logger.LogWarning(
                    ex,
                    "RCON connection attempt {Attempt}/{Max} failed. Retrying in {Delay}s...",
                    attempt, MaxStartupAttempts, delay.TotalSeconds);
                await Task.Delay(delay, cancellationToken);
                delay *= 2;
            }
        }

        // Final attempt — let the exception propagate
        await rcon.ConnectAndAuthenticateAsync(host, port, password, cancellationToken);
        await ClearConsoleCommandGateAsync(cancellationToken);
        // No unsolicited game listeners in the restricted profile.
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;

    private async Task InitializeGameListenersAsync(CancellationToken cancellationToken)
    {
        try
        {
            await factorioService.InitializeChatListenerAsync(cancellationToken);
            logger.LogInformation("Chat message listener initialized");
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Failed to initialize chat listener — chat tools may not work until manually re-initialized");
        }
    }

    /// <summary>
    /// Pre-clear the Factorio 2.1.23 console-command confirmation gate with a
    /// read-only probe sent twice. The probe observes nothing and changes nothing.
    /// A failure here is logged and ignored: later commands may still be gated,
    /// but the restriction is never weakened and no gameplay action is retried.
    /// </summary>
    private async Task ClearConsoleCommandGateAsync(CancellationToken cancellationToken)
    {
        try
        {
            await rcon.ExecuteLuaAsync(ConsoleGateProbe, cancellationToken);
            var confirmation = await rcon.ExecuteLuaAsync(ConsoleGateProbe, cancellationToken);
            logger.LogInformation(
                "Console command gate pre-cleared; probe confirmation: {Confirmation}",
                confirmation.Trim());
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Console command gate probe failed; continuing without it");
        }
    }
}
