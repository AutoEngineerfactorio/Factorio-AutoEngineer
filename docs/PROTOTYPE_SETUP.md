# Tested source installation — Windows, Python 3.12

This is a supervised experimental source package, not an unattended agent or installer. Use a disposable Factorio 2.0 world only. Main saves must not be connected. MIT and third-party attribution are included separately.

## Prerequisites

Windows; Python 3.12 with Tkinter; Git; the .NET 9 SDK/runtime used by this prototype; a local llama.cpp server (Phi-4-mini by default, Qwen optional) serving an OpenAI-compatible API; and a separately configured, localhost-only disposable Factorio server with exactly one connected player. Game files, models, backend vendor checkout and binaries are not bundled. These installation checks used existing OS/runtime prerequisites; they are not a clean-OS test or a certification of the underlying runtime's security support.

## Install Python dependencies

From the extracted project folder, in PowerShell 7:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```

The lock was resolved and tested for Windows CPython 3.12. Other platforms require separate validation. `requirements.txt` records the direct dependency; use the hash-pinned `requirements.lock` for installation. The package contains no virtual environment or downloaded wheels.

## Obtain and build the separately attributed backend

```powershell
git clone https://github.com/sbarisic/FactorioMCP.git external/FactorioMCP
git -C external/FactorioMCP checkout f2fca61707efe3107e7a3738bb83d1505b0126f7
git -C external/FactorioMCP apply --check ../../backend-safety/backend-safety.patch
git -C external/FactorioMCP apply ../../backend-safety/backend-safety.patch
dotnet restore external/FactorioMCP/FactorioMCP/FactorioMCP.csproj --locked-mode
dotnet build external/FactorioMCP/FactorioMCP/FactorioMCP.csproj -c Release --no-restore
```

Apply the current combined patch once to the exact upstream revision. Do not first apply an older safety patch or force patch mismatches. Preserve the upstream license and attribution. The patch adds a NuGet lockfile, disables broad tool/resource registration and removes image processing from this restricted profile. The default example DLL path matches these commands. The full backend checkout and its other tools are separate vendor source, excluded from this package.

## Isolate configuration and credentials

```powershell
Copy-Item config.example.json config.local.json
```

Edit only this ignored configuration to set the disposable server's RCON port and the identifier actually reported by your local model server. RCON and model hosts must remain loopback. Paths in local JSON resolve from the extracted project, not the terminal's current folder. The default DLL path uses `external/FactorioMCP`; `dotnet` must be available on PATH or configured locally.

Use a new, high-entropy password for the separately isolated disposable server. In the terminal that will launch the dashboard:

```powershell
$env:FACTORIO_RCON_PASSWORD = Read-Host 'Disposable-world RCON password' -MaskInput
```

The server must already be running with that same new password, a separate writable data directory and test-only save path, and localhost-only game/RCON bindings. Never start it with the normal client config or a main save. Do not put its password in project JSON or commit server settings. `.env` files are not loaded. This test rotated the retired disposable credentials, kept them only in private runtime files/environment, and used a fresh isolated world. Production or main-game credentials were not changed.

## Run and stop

```powershell
.\.venv\Scripts\python.exe agent/autoengineer_dashboard.py
```

Start a supervised session. Each proposed move requires Approve; Reject never dispatches movement. Stop cancels planning, approvals, movement and route recovery. Closing the dashboard uses cooperative stopping with a bounded fallback. Check for game-side stop acknowledgement, not merely a closed window. Lease expiry is 120 advancing simulation ticks; it is not a fixed wall-clock deadline.

After the dashboard and backend exit:

```powershell
Remove-Item Env:FACTORIO_RCON_PASSWORD
```

Structured per-session events are in `.local/events/`; backend working state is in `.local/backend/`. Both are ignored and excluded from packages. Events avoid model text and credentials. Review [dispatch audit](DISPATCH_AUDIT.md) for the exact boundary and remaining limits, and [hardening validation](HARDENING_VALIDATION.md) for evidence. No legacy execution experiments are shipped in the approved package.

## Model and movement update

Use [model selection](MODEL_SELECTION.md) to launch Phi-4-mini or retain Qwen. This release requires the policy-v8 backend rebuild. For smooth local scripted movement, the tested configuration hosts the same disposable save in the graphical game using private loopback RCON; see [normal movement and hosting](NORMAL_MOVEMENT.md). A joined multiplayer client can still show prediction corrections. Keep separate test data and main saves isolated.

## Input helper required for policy 8

Copy `factorio-mod/autoengineer-input_2.1.22` into the isolated game profile's mods directory. Enable `autoengineer-input` in that profile and fully restart Factorio. This input-only adapter preserves normal controls and lets human input immediately revoke the AI lease. Without it, observation works but gameplay leases fail closed. See [launcher setup](LAUNCHER.md) and [foundation validation](FOUNDATION_VALIDATION.md).
