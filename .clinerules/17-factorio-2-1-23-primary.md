# Primary development target: Factorio 2.1.23

**Current user decision: October 20, 2026.** The portable Factorio executable was updated in-place from 2.1.22 to **2.1.23**; the user wants to continue quickly on the latest 2.1 branch, without further work on 2.0.77.

- **Factorio 2.1.23 is the sole active target** for Zoo Code tasks, R05 mechanics evidence, R06 production solver, AI Helper, dashboard, future blueprints, development test fixtures and pY research/benchmarks.
- The verified updated executable is currently at `D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe`. **The enclosing folder name is historical; inspect the executable's ProductVersion or game log**, not its path, when verifying version. Do not rename, move, or replace its folder while the user's Factorio process is running.
- The canonical **new isolated development launcher profile** is `D:\AI\Factorio-AutoEngineer-Source\.local\launcher-profiles\2.1.23\launcher.local.json`, with independent `config.ini`, disposable save, mods and private test RCON secret. Never print credentials. Profile is created; *a game/mod compatibility smoke test is still required* before claiming a full live acceptance.
- Preserve the complete original `D:\AI\Factorio-Isolated-2.1.22\Factorio_2.1.22` as rollback. Old launcher profiles, 2.1.22 evidence captures and reports remain historical, not evidence that newly updated 2.1.23 passed.
- The current `autoengineer-input_2.1.22` directory name is **the mod's release version**, not a game-version lock; its `info.json` declares `factorio_version = "2.1"`. Do not rename/reversion it simply to match 2.1.23. Audit actual mod loading/behavior first.
- **Defer all 2.0.77 backport work** unless the user explicitly requests it. Preserve the already-passing 2.0 historical-power compatibility branch and dated evidence.
- Continue R05 mechanics evidence for 2.1.23 and R06/R04–R06 Helper acceptance. The 2.1.22 production/power test suite passed previously, but **2.1.23 live acceptance has not automatically inherited that result**.
- Verify Pyanodons' exact 2.1.23-compatible release/mod dependency set before loading a separate pinned test profile. Do not assume full pY compatibility. No regular save, login, personal game installation or Zoo task may be modified without reason/approval.
- Maintain Helper read-only rights, approvals, Stop, model-inference isolation and all prior safety instructions. R05 and Phase 1A remain separately gated.
