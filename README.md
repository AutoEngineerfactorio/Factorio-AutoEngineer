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

The target is **legitimate gameplay**—no teleporting, item spawning, or hidden creative-mode advantages. The existing MCP backend exposes capabilities broader than those approved for agent use; a tool allowlist in a prototype client should not be treated as a hardened sandbox. Keep the agent supervised and use an isolated test world.

Never commit passwords, API keys, saves, model weights, downloaded binaries, local configuration, build artifacts, or vendor source code without checking its license.

## Getting started

Installation instructions will be published **after** we assemble and test a clean public distribution. Until then, follow development in the [roadmap](ROADMAP.md).

## Contributing

Suggestions, testing feedback, bug reports, and contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Project website

The project website is published at [autoengineerfactorio.github.io/Factorio-AutoEngineer](https://autoengineerfactorio.github.io/Factorio-AutoEngineer/). Its source is `index.html` at the repository root. GitHub Pages deploys from the `main` branch, `/ (root)` folder.

## Licensing

The project licensing decision is pending review of code ownership and third-party dependencies. Until a license is added, no broad reuse rights are granted for original code in this repository. We will keep dependencies as separately attributed projects.

Factorio is developed by Wube Software. Factorio AutoEngineer is an independent community project and is not affiliated with or endorsed by Wube Software.
