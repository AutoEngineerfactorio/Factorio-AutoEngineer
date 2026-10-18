# Windows one-folder test build

Use the project's Python 3.12 hashed runtime lockfile in an isolated environment, then the separately pinned `requirements-build.txt` for PyInstaller and psutil. Build from the project root:

```powershell
python -m PyInstaller --noconfirm --distpath outputs --workpath work/launcher-build packaging/AutoEngineer.spec
```

The spec produces AutoEngineer.exe (windowed) and AutoEngineerWorker.exe (console-capable, launched without console windows) sharing _internal. Console-capable workers preserve stdin/stdout cancellation and MCP transport. Never replace them with windowed workers. Game, models, .NET and policy-8 backend are separate installed prerequisites. Install the input-only helper in the isolated profile. Local profiles and credentials are excluded from public source/build manifests. Record build tool/runtime versions, source hashes and output hashes; this local build is not bit-for-bit reproducibility or code signing proof.

Profiles explicitly opt into an isolated test root, valid ZIP save, unlisted/private host and loopback RCON. Graphical hosting uses the private Factorio INI local-rcon keys; the launcher verifies them without writing secrets. Dedicated-server mode is retained but is not qualified by the new graphical-host tests.

Test the complete source suite, frozen profile validation, policy probe, idle live telemetry, owned cold start/save/stop, pre-existing attach preservation, profile locking, collisions, cancellation and actual worker approval/Stop behavior before distribution. Include project/upstream notices and licenses of bundled Python components. Do not bundle credentials, proprietary game data, model weights or test saves.
