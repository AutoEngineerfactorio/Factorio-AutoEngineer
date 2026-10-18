# Prototype setup and safety checks

This experimental source snapshot supports supervised testing on disposable Factorio worlds. It is not a validated public release or installer. Original AutoEngineer contributions use the [MIT License](../LICENSE). Preserve the backend attribution and other [third-party notices](../THIRD_PARTY_NOTICES.md).

## Included

Eight original Python prototype files, sanitized for credentials and installation paths, plus a shared configuration helper. No backend checkout, compiled binary, model weight, save, runtime data, log, credential, or backup is included. The repository also contains the project website and development roadmap.

## Prerequisites

- Windows and Python 3.12, with Tkinter (`python -m tkinter` checks availability).
- A separate Factorio 2.0 disposable test world with RCON configured by you.
- A separately obtained FactorioMCP backend targeting .NET 9, with the included [`backend-safety/backend-safety.patch`](../backend-safety/backend-safety.patch) applied to a **separate backend copy** and rebuilt. The controller refuses an unpatched backend. See [backend safety instructions](../backend-safety/README.md). Its exact upstream revision and other local patches remain to be established.
- A separately obtained llama.cpp server and model serving an OpenAI-compatible API. The example uses the model identifier from the prototype; set it to the identifier actually served by your local instance.
- `requirements.txt` pins the direct MCP dependency to the version found in the local prototype's Python installation. This is not a transitive lockfile or proof of compatibility on a fresh machine.

## Local setup (PowerShell 7, from the repository root)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config.example.json config.local.json
```

Edit `config.local.json` to point to your separately built backend DLL. Relative DLL and custom configuration paths resolve from this project folder, regardless of the current working directory. `dotnet_command` defaults to `dotnet` found on PATH; an executable path may be supplied in your ignored local configuration. Set `AUTOENGINEER_CONFIG` only if using a different configuration filename. JSON configuration never contains the RCON password. `.env` files are not loaded.

Set the password interactively in the same terminal rather than putting its value into command history:

```powershell
$env:FACTORIO_RCON_PASSWORD = Read-Host 'Test-world RCON password' -MaskInput
```

The dashboard inherits this environment and passes it to its controller. Missing passwords, backend files, or dotnet fail before the backend launches. Do not share `config.local.json` or environment dumps.

## Entry points — read before running

- `agent/autoengineer_dashboard.py`: primary dashboard; its Start button launches the supervised controller. Each proposed movement requires approval.
- `agent/supervised_agent.py`: same controller from the console, up to three proposal cycles.
- `agent/live_planner.py`: observations and model planning.
- `agent/test_mcp_readonly.py`: live backend integration diagnostic; not an offline unit test.
- `agent/inspect_mcp_tools.py`: backend tool schema inspection.
- `agent/ai_movement.py` and `agent/safe_executor.py`: earlier experiments; `--execute` allows movement without the dashboard's per-action approval prompt. Omit that flag for dry-run mode.
- `agent/main.py`: early simulated-observation model planning example, not the main controller.

After reviewing the remaining safety limitations, a disposable-world session can be started with:

```powershell
.\.venv\Scripts\python.exe agent/autoengineer_dashboard.py
```

Remove the password from the terminal environment after the dashboard and its child processes have exited:

```powershell
Remove-Item Env:FACTORIO_RCON_PASSWORD
```

## Emergency stopping

`q`, `stop`, input closure, Ctrl+C, or the dashboard Stop button now cancel the supervised session during any phase. The controller requests a game-side stop on cancellation, normal completion and failure. It reports acknowledgement separately from an unconfirmed stop. Closing the dashboard uses this same shutdown path, with force termination only after a ten-second grace period.

The backend patch requires a session-owned lease for walking, renews it through safety calls outside the gameplay queue, and clears walking/mining in the game tick handler when the lease expires or is stopped. Expiry is 120 game ticks (about two simulation seconds at 60 ticks/second), not a wall-clock deadline. It cannot be revived by a late heartbeat. A fresh explicit arm starts a new session. Exactly one connected player is required; multiplayer targeting is not implemented. Older movement experiments and other backend navigation paths without a lease owner now fail closed with this backend patch.

Controller heartbeats run every 0.3 seconds and safety cleanup has a 1.5-second overall timeout. Stop confirmation is retried on later ticks within that budget, because Factorio can initially report the previous walking state. If transport is lost or the controller dies, the installed handler stops movement when the lease expires. Paused or slowed simulations affect wall-clock expiry time. Other code that replaces the game handler can invalidate this protection. This is a supervised safety improvement, not a hardened backend sandbox.

## Offline checks and remaining release blockers

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

The 34 offline tests use fake sessions, temporary configuration and a task-only event loop that cannot open network sockets. They cover cancellation, heartbeat failure, EOF, stale approvals, shutdown acknowledgement and dashboard session isolation. The backend patch was compiled in a separate local source copy using cached dependencies.

Live checks subsequently passed in a newly generated disposable Factorio 2.0.77 world, with a separate patched backend and independent observer: Stop (7 observed game ticks), controller kill (107), backend kill (103) and backend RCON connection loss (107). Position remained stable for a further 72 game ticks after each observed stop. The fixture used slowed, deterministic five-tile movement rather than model-generated actions. Follow-up actual dashboard Stop and confirmed Close tests also passed during movement, with zero position drift over 120 further game ticks. A Close-dialog/controller-exit race was found and fixed; the window now closes even if its controller exits during confirmation. Pause/resume, stale-owner behavior and manual takeover remain follow-ups. No main save was used, and test processes were shut down afterward. These measurements are single-case observations, not universal real-time guarantees.

Backend startup installs a game chat listener even for observation diagnostics. The existing backend dependency warnings, broader execution-boundary review, dependency provenance, clean installation, and authorship review remain open. Do not use important saves or unattended servers. Third-party components retain their existing licenses.
