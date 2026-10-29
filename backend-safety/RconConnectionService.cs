using System;
using FactorioMCP.Rcon;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace FactorioMCP.Services;

/// <summary>
/// Hosted service that connects and authenticates the RCON client on application startup.
/// Reads connection settings from environment variables.
/// Retries connection with exponential backoff if the server is not yet available.
///
/// Connecting never sends a Lua console command. Factorio 2.1.23 holds the first
/// raw Lua console command of a fresh server and asks the operator to repeat it,
/// because running Lua from the console disables achievements. The backend never
/// answers that confirmation on the operator's behalf; all observations travel
/// over registered mod commands.
/// </summary>
internal sealed class RconConnectionService(
    RconClient rcon,
    FactorioService factorioService,
    IConfiguration configuration,
    ILogger<RconConnectionService> logger) : IHostedService
{
    private const int MaxStartupAttempts = 5;
    private static readonly TimeSpan InitialBackoff = TimeSpan.FromSeconds(2);

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

                // No startup console probe. Factorio 2.1.23 holds the first raw
                // Lua console command of a fresh server and asks the operator to
                // repeat it to confirm that achievements may be disabled. The
                // backend never answers that confirmation on the operator's
                // behalf: all observations travel over registered mod commands,
                // which are not Lua console commands.
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
}
