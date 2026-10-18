# Windows launcher preview

Download the Windows x64 ZIP from GitHub Releases and extract the entire folder. Open AutoEngineer.exe. Keep AutoEngineerWorker.exe and _internal together. Python is bundled. This is an unsigned, experimental one-folder preview, not a standalone installer.

## First setup

You must separately install Factorio, llama.cpp with a compatible GGUF model, .NET 9 and the policy-7 backend built from this repository's current combined patch. No game assets, model weights, credentials, saves or vendor backend binaries are distributed in this preview. See PROTOTYPE_SETUP.md for the pinned backend build.

Copy launcher.example.json from the extracted ZIP (or packaging/launcher.example.json from source) to launcher.local.json beside the executable. Set every path to your installed prerequisites and an isolated test-world folder; relative profile paths resolve beside the JSON. Create a reusable disposable save named test-world.zip under test-world/data/saves. Both INI fields can reference the same test-world/config.ini. Set [path] write-data to the absolute test-world/data directory and read-data to your installed Factorio data directory. Create the mods directory and server-settings.json with visibility.public=false and visibility.lan=false. Keep passwords out of public files.

Create the private secret file referenced by secret_file with an rcon_password field containing a unique password. In the private INI [other], set local-rcon-socket=127.0.0.1:27108 and local-rcon-password to the same password, matching the selected profile port. Use no spaces around the INI equals sign. Set enable-blueprint-storage-cloud-sync=false in this isolated INI to avoid loading an incompatible Steam cloud library; leave your normal game profile alone. The game port, RCON port and model port must be different. test_profile must explicitly be true. Full Autonomy remains locked.

Use Choose setup to select the private JSON, then Start / attach everything. The launcher verifies the save ZIP, isolation paths, private host visibility, loopback RCON configuration, single connected character, model API, restricted policy 7 and live Helper observation. Factorio may require its one-time Lua warning to be acknowledged in the disposable save. The graphical client hosts multiplayer directly; this avoids the movement prediction snap-back seen with a separate joined client.

## Ownership and stopping

AI Helper is read-only; Semi-Autonomous actions require approval. The five-tile movement bound and normal game speed remain active. Emergency Stop cancels startup or cooperatively stops/closes the owned dashboard/controller, leaving the game and model running. Stop launcher-owned services saves and checks a stationary owned test game before closing it, then stops the owned model. Existing attached services are never adopted or closed. If cleanup or saving cannot be confirmed, services stay running and the error is shown. Closing the launcher uses the same shutdown path.

The launcher detects lost services and duplicate starts. It does not automatically approve actions, reconnect a gameplay session or restart failed services. Manual takeover arbitration, a full setup wizard, provider catalog, clean-PC certification, code signing and a public installer remain roadmap work. Dedicated-server mode exists but this preview was qualified with graphical hosting on Windows and Factorio 2.0.77.

Local JSON, credentials and runtime logs must not be uploaded. The release example contains placeholders only. The local setup used during development is excluded from release assets.

Gameplay leases require direct character control outside vehicles. Remote view remains read-only: its camera position is never used as the character position, and entering remote view or driving revokes active walking. Stop clears the character directly even when the camera is elsewhere.
