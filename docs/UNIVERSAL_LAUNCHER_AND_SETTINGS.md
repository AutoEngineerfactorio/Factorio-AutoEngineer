# Universal launcher and Settings (2026-10-28)

This document describes the Windows launcher, the profile manager and the
Settings screen of the AutoEngineer dashboard.

**Supported game version: Factorio 2.1.23 only.**

## Starting the application

Double-click **`Launch AutoEngineer.cmd`** in the project root. It starts
the pinned `.venv` and opens the Qt dashboard. The dashboard opens without
Factorio running: the game is only started when the user asks for it.

If the `.venv` is missing, the script says so and stops. Repair the
environment first; do not point the script at a different Python.

The window opens with the size and the state the Settings saved. The
Settings live in **`.local/settings.json`** and the profiles live in
**`.local/factorio-profiles/`**. Both are plain files and folders: they
can be inspected, backed up and moved.

## Profiles

A **profile** is one Factorio installation plus one mod configuration plus
its own saves, configuration and cache. The two documented test profiles,
Vanilla/Space Age and Pyanodons, are only two profiles; any compatible
modpack works the same way.

### What the profile manager does

| action | what happens |
| --- | --- |
| **Detect installations** | the common Steam and standalone folders are searched, and the executable's version is read from the Windows file-version resource |
| **Create** | a new profile with its own `saves`, `config` and `cache` folders. The Factorio installation is only *read* |
| **Edit / Rename** | the name and the notes. The identifier and the owned folders are immutable, so two profiles can never share a save |
| **Duplicate** | a full copy, including the saves, as a **separate** profile with its own folders |
| **Import / Export** | a profile definition as a JSON file. An import never overwrites an existing profile |
| **Delete** | removes the profile and its own saves, configuration and cache, after an explicit confirmation. The Factorio installation is never touched |
| **Select** | chooses the active profile. Selecting never modifies a profile and never modifies another profile |

The **profile root** can be changed with the environment variable
`AUTOENGINEER_PROFILE_ROOT`.

### What it reports truthfully

* the game version, read from the executable, or **unknown** — never
  guessed from the folder name, because that name is routinely stale;
* the enabled mods with their versions, read from the installation's own
  `mod-list.json` and the mods' own `info.json`;
* a mod that is enabled but **not installed**;
* a mod whose **dependency** is not enabled;
* a **fingerprint** over the game version and the mod identity. A mod
  change changes the fingerprint, so a cached catalog is invalidated
  correctly.

### Two kinds of installation

* **usable** — the folder holds a Factorio executable. A profile can be
  created for it.
* **valid** — the version was read *and* it is the supported 2.1.23.

An installation with a working executable and an unreadable version is
**usable** but not valid. The version mismatch is reported as a problem
the user has to see; it never blocks the profile.

## The game controls

The strip above the workspace carries the profile and the game controls.

* **Launch** is enabled only when a profile is selected, the game is not
  running and **no other Factorio instance exists** — from any
  installation.
* **Stop** is enabled only when the game is running **and AutoEngineer
  started it**. A game the user started by hand is never stopped.
* Both ask for a confirmation first.

The rule is the same one the isolated test-host launcher uses: a game
AutoEngineer started may be stopped, and only after a save was requested;
an attached game is never adopted, stopped or saved.

The game is started with the profile's **own** `config.ini`, which points
Factorio at the profile's own write-data directory. The game therefore
uses the profile's own saves, configuration and mods, and never the user's
own Factorio profile. The installation is only ever read.

Only the mod's **registered** commands are used (`/autoengineer-status`,
`/autoengineer-save`, `/autoengineer-observe status`). The project never
sends console Lua.

## Settings

The Settings screen is reachable from the sidebar and from the header.
It has seven sections: **General**, **Factorio and Profiles**, **AI
Models**, **AI Helper and Blueprints**, **Performance and Telemetry**,
**Safety** and **Diagnostics**.

### General
Startup behaviour, the default workspace, the window size, the theme and
the interface scale.

### Factorio and Profiles
The default profile, an additional installation directory and the launch
and stop confirmations. The Profiles card below the tabs lists every
profile with its version, its mod count and its problems, and offers
Select, Rename, Duplicate and Delete.

### AI Models
The provider, the endpoint, the model, the context window, the largest
answer, the request timeout and the number of parallel requests.

**Credentials are never stored here.** A setting whose name looks like a
credential is refused, and a credential that was hand-edited into the
file is ignored. The RCON password stays in the `FACTORIO_RCON_PASSWORD`
environment variable. The Settings only report whether a credential is
**present**.

The existing FrogNano model is supported like any other: the model name
is a setting, not a hardcoded choice.

**Test connection** checks the configured endpoint and reports exactly
what was verified:

| the report says | what it means |
| --- | --- |
| the endpoint is reachable | the endpoint answered an HTTP request |
| the models are discovered | the endpoint listed its models |
| the inference succeeded | the model answered a completion |
| the tool calling is verified | the model produced a tool call |
| the model is compatible | all of the above succeeded |

A reachable endpoint is **not** a capable model: each step is reported
separately, and a step that was not checked is never shown as verified.
The test starts nothing: it only speaks HTTP to the loopback endpoint.

The **CPU** limit is applied as the priority of the model process
AutoEngineer owns. The **memory** limit is **advisory**: it bounds the
application's own caches and histories and is not a hard cap on the
model's memory.

### AI Helper and Blueprints
The production unit, the blueprint spacing, columns and machine limit,
the blueprint library folder, whether a complete observed catalog is
required, and the research restriction.

### Performance and Telemetry
The UPS target (**60** by default) and its three thresholds, the
observation intervals and the request budget, the cache limits, the
history retention, the modded-catalog paging and the CPU and memory
limits.

### Safety
The read-only AI Helper, the per-action approval, the emergency stop and
the supervisor timeout.

**Fully Autonomous stays locked.** The Settings show the real permission
mode from `mode_policy`; they cannot unlock it.

### Diagnostics
The **real** state: whether the compiled backend DLL exists, the
configured model endpoint, whether the RCON credential is present and the
real permission mode. A control whose backend is missing is disabled and
says why; it never looks operational.

## How a change reaches the service

A saved setting is written to `.local/settings.json` atomically, and the
environment still wins over the file, because that is how the launcher
already configures the backend and the model. An environment value that
is invalid is reported with the **name of the variable**.

The stored values are **overlaid** onto `config.local.json` by
`autoengineer_config.get_settings()`, so every service that reads its
configuration through that one function picks up a change made in the
interface. The base configuration is validated **first**, so an invalid
`config.local.json` is always refused even when the Settings would have
replaced the offending value.

| section | reaches | when |
| --- | --- | --- |
| AI Models | the model endpoint, the model name, the request timeout | at the next request |
| Performance and Telemetry | the observation interval, the request budget, the concurrency limit | when the observer is created |
| Performance and Telemetry | the UPS thresholds | at the next guard sample |
| General | the window size, the maximized preference | at the next start |

The Settings screen shows **Apply settings**, **Discard changes** and
**Restore defaults**, reports how many changes are unsaved, and names the
settings that need a restart. Restoring the defaults only **shows** them;
they are stored when they are applied.

## What is not claimed

* The dashboard opens without Factorio. The game is only started on
  request.
* The profile manager reads the installation; it never writes into it.
* The game controls follow the verified process state, never an
  assumption.
* The Settings report the real state of the services; a missing backend
  is reported as missing.
* A live acceptance run — a real Factorio start, a real save, a real
  observation — has **not** been performed for this increment. The
  evidence so far is offline.

## The live acceptance preflight

Before the live acceptance, run:

```
python -B tests/live_m4_acceptance_preflight.py
```

It checks every installation it can find, the profile isolation, the
running Factorio processes, the stop ownership rule, the settings and the
saves. It never launches Factorio and never touches a save. The exit
code is zero when every check passed.

The live acceptance itself needs one thing the preflight cannot create:
a **profile** for one of the detected installations.
