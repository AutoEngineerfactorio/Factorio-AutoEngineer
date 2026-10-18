# Phi-4-mini versus Qwen: normal-speed navigation

2026-10-18. At test time Qwen remained the default. After review, the user selected Phi-4-mini as the new default, with Qwen retained as a configurable option. The license is unchanged.

## Results

| Model | Open tasks | Blocked tasks | Median model call | Median open task | Median blocked task | Recovery Stop checks |
|---|---:|---:|---:|---:|---:|---:|
| Qwen2.5-Coder 7B | 3/3 | 3/3 | 0.899 s | 23.1 s | 26.4 s | 2/2 |
| Phi-4-mini | 3/3 | 3/3 | 0.538 s | 18.0 s | 19.5 s | 2/2 |

## Test protocol

Sixteen live trials used the same reusable `hardening-uncleared` test save, hosted by the graphical game. Normal character speed (modifier 0) and game speed 1 were retained. Each ordinary trial had two objectives: 24 tiles east, then 16 south. Three open and three blocked trials per model alternated model order between rounds. These are repeated 40-tile tasks, not an unrestricted autonomy soak.

The actual production controller, dispatch boundary, one-use approvals, safety lease, movement watchdog and policy-v7 backend ran in isolated test processes. A test-only action cap of 20 per leg replaced the production three-cycle cap; production source limits and default model were unchanged. Both Q4_K_M models used the same llama.cpp runtime, 4096-token context, temperature 0.2 and 120-token response budget. Production sampling had no fixed seed. Timings exclude model loading; model latency includes cache effects and response-length differences.

Blocked trials created nine temporary walls around the initial waypoint and required real backend route failure and recovery. One blocked repeat per model rejected the first recovery proposal. Separate trials stopped each model while awaiting recovery approval and while walking during recovery. The authorized test operator supplied bounded approvals; models did not approve their own actions. Only fixture-created walls were removed. Position resets occurred between benchmark trials, not during the earlier five-move visual check. The original benchmark position and speed were restored, and test model processes were closed.

Five-tile request and planned-path checks remained active alongside game-tick cumulative travel and displacement bounds. The independent observer recorded displacement; it did not impose the earlier diagnostic's 4.5-tile Stop threshold. Stop confirmation and zero subsequent drift were mandatory for every trial.

## Movement correction and visual check

Earlier interrupted normal-speed diagnostics exposed shared movement overshoot and premature arrival reporting; those runs are excluded from the paired results above. The separate backend now steers on game ticks using sixteen native directions and heading hysteresis, reserves the next physical step within five tiles, and verifies actual stationary endpoint positions. Backend policy 7 is required. The separate backend built without warnings/errors; 130 offline Python checks passed, including exact Lua tick tests. The combined patch was verified against clean pinned upstream.

A joined multiplayer client's visual prediction still produced snap-back despite stable server positions. The same test save was therefore hosted directly in the graphical game with private loopback RCON. The user confirmed no snap-back, and five additional moves stopped without later drift or intervening teleports. This is evidence for the tested local-host setup, not every remote client.

## Interpretation

Completion and safe recovery matter alongside inference speed. Deterministic waypoint generation, failed-target memory, approval enforcement and path validation are shared components; recovery success is not solely a model capability. These trials do not establish mining, crafting, combat, factory building or long-term strategic autonomy. Fully Autonomous mode remains locked. The user selected Phi-4-mini after reviewing these results; Qwen remains available.

- **qwen**: 78 verified moves, 3 recovery events, 1 rejected recovery proposal(s); maximum requested step 4.000 tiles, maximum sampled displacement 3.991 tiles. All Stops confirmed with zero drift: True.
- **phi**: 78 verified moves, 3 recovery events, 1 rejected recovery proposal(s); maximum requested step 4.000 tiles, maximum sampled displacement 3.991 tiles. All Stops confirmed with zero drift: True.

## Final directional and limit checks

Ten additional normal-speed cardinal, diagonal and exact-five-tile requests produced 9 verified arrivals and 1 safe path rejection(s). Every request stopped without subsequent drift and stayed within five tiles. The independently tested host validator and backend both rejected a six-tile request, with zero movement.
