# Factorio AutoEngineer

**Build together. Automate intelligently.**

Factorio AutoEngineer is an experimental, locally powered AI companion project for Factorio. The goal is to let an AI observe a running game, propose legitimate gameplay actions, and eventually help players explore, gather resources, plan production, and build factories—while keeping the player in control.

> **Development status: experimental prototype.** This is not yet a downloadable, fully autonomous Factorio agent. Do not connect it to important saves or unattended servers.

## What works in our development prototype

- Local Qwen model served through `llama.cpp` with Vulkan on an AMD GPU
- FactorioMCP connection to a Factorio 2.0 test server
- Live player position, inventory, resource scans, and recipe observations
- AI-generated movement proposals checked by a Python controller
- Supervised movement execution, followed by position verification
- A basic Windows dashboard that presents agent logs and approvals

These capabilities have been tested in a local development setup. We have **not** published a validated installer or reproducible public release yet.

## In development

- Stronger action validation, audit logs, and safer credential handling
- Goal-driven exploration with persistent map memory
- Mining, crafting, and factory construction through normal game mechanics
- Improved dashboard with map, inventory, objectives, and history
- Optional, expandable in-game AutoEngineer panel and player assistance
- Mod-aware prototype and recipe discovery, including Space Age and community overhauls
- Eventually, unattended autonomy with explicit limits and recovery behavior

## Architecture (prototype)

```text
Factorio game / isolated test server
         ⇅
FactorioMCP (separate third-party project)
         ⇅
Python supervised agent + action validation
         ⇅
Local llama.cpp server / Qwen model
         ⇅
Windows dashboard / player approvals
```

## Safety and scope

The target is **legitimate gameplay**—no teleporting, item spawning, or hidden creative-mode advantages. The required restricted backend exposes only nine reviewed tools and enforces movement bounds. RCON remains privileged; this is not an operating-system sandbox. See the [dispatch audit](docs/DISPATCH_AUDIT.md). Keep the agent supervised and use an isolated test world.

Never commit passwords, API keys, saves, model weights, downloaded binaries, local configuration, build artifacts, or vendor source code without checking its license.

## Getting started

The supervised prototype source is available in [`agent/`](agent/). Follow the [setup and safety instructions](docs/PROTOTYPE_SETUP.md), including the required [backend safety patch](backend-safety/README.md). Install the approved source package with the hashed Python lockfile and the combined restricted-backend patch. There is no installer or stable release.

The actual dashboard Stop and Close controls, process-loss behavior and connection-loss behavior were tested in a disposable Factorio world. Read the [validation record and its limits](docs/SAFETY_VALIDATION.md). Further development is tracked in the [roadmap](ROADMAP.md).

## Contributing

Persistent visited-area and failed-target memory is available locally; select a
world identifier before launching. See [exploration memory](docs/EXPLORATION_MEMORY.md)
for setup, reset behavior and limitations. Choose a resource or coordinate goal
with [objective navigation](docs/OBJECTIVE_NAVIGATION.md); the updated backend
validates each planned route before walking. See [resource discovery](docs/RESOURCE_DISCOVERY.md) for scan reuse and observation freshness.

Suggestions, testing feedback, bug reports, and contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Project website

The project website is published at [autoengineerfactorio.github.io/Factorio-AutoEngineer](https://autoengineerfactorio.github.io/Factorio-AutoEngineer/). Its source is `index.html` at the repository root. GitHub Pages deploys from the `main` branch, `/ (root)` folder.

## Licensing

Original Factorio-AutoEngineer code and documentation are licensed under the [MIT License](LICENSE). The separately obtained FactorioMCP backend retains its upstream MIT license and attribution; see [third-party notices](THIRD_PARTY_NOTICES.md), including the upstream license text for backend-derived patch material. Other dependencies and assets retain their own licenses.

Factorio is developed by Wube Software. Factorio AutoEngineer is an independent community project and is not affiliated with or endorsed by Wube Software.

The [live dashboard](docs/LIVE_DASHBOARD.md) displays a read-only observed map and main inventory during supervised sessions. It requires the current policy-v6 backend patch and rebuild.

[Verified starter mining and crafting](docs/VERIFIED_OPERATIONS.md) is available through the dashboard, with batch limits, preflight checks, inventory verification and owned-operation stopping.

Detailed future work: [reconciled handoff](docs/WORK_HANDOFF_2026-10-18.md) and [full-autonomy gap audit](docs/FULL_AUTONOMY_GAP_AUDIT_2026-10-18.md). Research candidates are not verified compatibility claims.

The game-style map and slot inventory stay live whenever the dashboard is open, independently of the AI. Rebuild the current backend patch; see [display setup](docs/LIVE_DASHBOARD.md) and [validation](docs/DASHBOARD_MAP_VALIDATION.md).

Operating modes are documented in [OPERATING_MODES.md](docs/OPERATING_MODES.md). The current mode-aware backend must be rebuilt before Semi-Autonomous sessions run.
