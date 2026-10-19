# Factorio 2.x edge cases and regression-test catalog (base + Space Age)

Updated 2026-10-18. Companion to [mechanics source hub](FACTORIO_MECHANICS_REFERENCE.md), [Lua scripting and mod API reference](FACTORIO_SCRIPTING_API_REFERENCE.md) (including LUA-01 through LUA-20 test candidates), [gap register](FACTORIO_COVERAGE_GAP_REGISTER.md), [R01-R20 roadmap](../ROADMAP.md) and [acceptance requirements](PLANNING_REQUIREMENTS.md).

**Purpose:** Detect surprising but legitimate gameplay behavior before AutoEngineer makes a wrong plan, claims a mechanic is covered or moves the player. This is a **curated, growing catalog**, not a claim that every quirk in every Factorio version has been discovered.

**Evidence marks:** **W** = source-supported expected rule, subject to exact version verification; **T** = proposed test/operational failure mode not yet independently validated for this project; **V** = explicitly measured in an authorized game fixture (none claimed here). A YouTube demonstration alone is not V.

**Record for every test:** case ID, R milestone, version/build, enabled first-party components and other mods, force/surface/research, recipe/prototype fingerprint, initial state, exact inputs/units, permission mode, expected result, measured result, elapsed ticks/time, stop behavior, source URL, and follow-up defect or passing test. Never change a real save to collect evidence without approval.

## Standard/base Factorio 2.x cases (ordinary Factorio is NOT assumed easy)

| ID | R | Case or quirk to test | Evidence status |
|---|---|---|---|
| **B01** | R01/R05 | Player manually takes over while an action is pending or the model replies late: no new dispatch, stale permits rejected | T |
| **B02** | R03/R09 | Game or agent crashes between issuing an action and receiving confirmation: re-observe instead of repeating an irreversible action | T |
| **B03** | R04/R08 | Remote map shows an uncharted/unobserved area: no invented entity/recipe/resource visibility or building permission | T |
| **B04** | R05/R18 | Character death, respawn, item recovery or vehicle entry changes the available controller, inventory, surface or force context | T |
| **B05** | R06 | Multiple recipe alternatives, multiple outputs or returned catalyst ingredients: mass balances avoid double credit/free loops | T |
| **B06** | R06 | Recycling/reprocessing cycles: solver detects cycles and cannot claim perpetual free material generation | T |
| **B07** | R06 | Probabilistic products: expected rate and variance differ from guaranteed item counts; do not promise precise output | T |
| **B08** | R06 | Machine module permissions, beacons, productivity, speed, energy and research levels alter legal output and power budget | W/T |
| **B09** | R06/R08 | Belts have **two lanes**; a saturated/compressed lane cannot be treated like two independently free lanes | W |
| **B10** | R06/R08 | Inserter pickup geometry, hand size, drop side, belt compression and upstream gaps change observed transfers | W |
| **B11** | R06/R13 | Blocked machine outputs/filled buffers stall throughput even when inputs and machines are sufficient | T |
| **B12** | R05/R13 | A drill on exhausted ore or with missing required mining fluid produces nothing; blocked output/low power has a different cause | W/T |
| **B13** | R06/R13 | Mining productivity vs resource drain: drill patch lifetime and production rate must be accounted for separately | W |
| **B14** | R06/R13 | Fluid **2.x segments** share fluid over a segment but connections and machine buffers still have limits; never reuse 1.x flow formula | W |
| **B15** | R06/R13 | A new game version changes extreme fluid-connection limits; do not hardcode one universal 6000/s cap | W/T |
| **B16** | R06/R13 | Heat pipes and fluid pipes are different; temperature thresholds, thermal inertia and throughput affect steam/nuclear load | W |
| **B17** | R13 | Separate electric networks, disconnected poles, accumulator priorities, low-power slowdown and feedback brownouts | W/T |
| **B18** | R07 | Imported compressed blueprint string is malformed, oversized, nested too deep, has unknown fields or version differences: reject/bound and preserve valid data | W/T |
| **B19** | R07/R08 | Blueprint ghost is not a physical machine; item inventory, delivery and connected power must be independently verified | W/T |
| **B20** | R07/R08 | Upgrade/deconstruction planner can change ghosts or queue independent robot tasks; Stop cannot magically undo completed work | W/T |
| **B21** | R10 | Red vs green wire signal isolation, feedback cycles, multi-combinator tick delay, simultaneous changes and power loss | W/T |
| **B22** | R11 | Train on wrong-way or unsignalled rail; signals on wrong side; 'no path' despite nearby track | W |
| **B23** | R11 | Chain signals protect intersections; using regular signals inside crossings can deadlock trains | W |
| **B24** | R11 | Full/closed/disabled station, route interrupt, insufficient station capacity, empty fuel tank and schedule thrashing | W/T |
| **B25** | R11 | Train/wagon/platform lengths and train limits reduce throughput compared with a perfect payload / journey-time ratio | T |
| **B26** | R12 | Logistic area vs construction area differ; linked orange areas define network; physically nearby robots may belong to separate networks | W |
| **B27** | R12 | Undercharged robots fly slowly and queues overload roboports; projected logistics rate assumes enough charging | W |
| **B28** | R12 | Personal roboport does **not** share the static network's robot inventory; entity's equipment and item supply matter | W |
| **B29** | R12/R14 | Combat follower robots are temporary and **not** interchangeable with construction/logistic bots | T |
| **B30** | R13/R14 | Pollution cloud drives attacks, but total production, not cloud containment alone, affects enemy evolution | W |
| **B31** | R14 | Ammo, turret orientation/priority, enemy resistances, friendly-fire and player retreat; no unapproved combat escalation | T |
| **B32** | R05/R14 | Spidertron remote issues direct movement orders; obstacles, queueing, invalid target and equipment must be evaluated | W/T |
| **B33** | R18 | Long runs with resource depletion, output backups, changing research, network restart and user takeover: no invented stability proof | T |

### Base-game references for B cases

- Belts and inserters: https://wiki.factorio.com/Transport_belts/Physics and https://wiki.factorio.com/inserters
- Mining/resource drain and productivity: https://wiki.factorio.com/Mining and https://wiki.factorio.com/Mining_productivity_%28research%29
- Module/productivity: https://wiki.factorio.com/Module and https://wiki.factorio.com/Productivity
- Fluid 2.x and changed connection behavior: https://wiki.factorio.com/fluid_system and https://factorio.com/blog/post/fff-442
- Power and heat: https://wiki.factorio.com/Electric_system and https://wiki.factorio.com/Heat_pipe
- Rails and signals/interrupts: https://wiki.factorio.com/Railway and https://wiki.factorio.com/Rail_chain_signal
- Roboports: https://wiki.factorio.com/Logistic_network and https://wiki.factorio.com/Roboport
- Blueprints/planners: https://wiki.factorio.com/Blueprint_string_format and https://wiki.factorio.com/Upgrade_planner and https://wiki.factorio.com/Deconstruction_planner
- Circuits: https://wiki.factorio.com/Circuit_network (cross-check current version; some older cookbook tutorials require updates)
- Pollution/enemies: https://wiki.factorio.com/Pollution and https://wiki.factorio.com/Enemies

## First-party expansion and planet-specific cases

| ID | R | Case or quirk to test | Evidence status |
|---|---|---|---|
| **S01** | R04/R16 | Space Age may be enabled without Quality on supported newer versions; test actual enabled component set | W |
| **S02** | R06/R08 | Space Age recipe requires a special machine or surface: candidate valid on one planet but illegal on another | W/T |
| **S03** | R15 | Platform foundation must be connected; holes and unsupported islands invalid; hub loss means platform loss | W |
| **S04** | R15 | Asteroid collector and thruster edge-placement restrictions; platform geometry and travel resilience | W |
| **S05** | R15 | Rocket deliveries and platform automatic requests have item-type/payload restrictions, staging and source-orbit constraints | W |
| **S06** | R15 | Hub full on unloading / landing pad full / requests unsatisfied may stall logistics or spill items; distinguish actual delivery from expected | W |
| **S07** | R15 | Fuel/oxidizer, power, turret ammo, asteroid distribution and platform damage differ by route; validate reserves and return | T |
| **S08** | R06/R15 | Asteroid processing and reprocessing have alternate/probabilistic outputs and waste loops; no perpetual free stock | T |
| **S09** | R06/R13 | Vulcanus lava recipes produce stone byproduct that can clog casting if not discharged | W/T |
| **S10** | R08/R14 | Demolisher territories: placement inside hostile territory can trigger destruction; player approval and defense required | W |
| **S11** | R06 | Tungsten ore requires big mining drill; small drills may not be legal despite physical accessibility | W |
| **S12** | R06/R13 | Fulgora scrap recycling creates several output streams; backlog of one product blocks effective throughput unless dealt with | W/T |
| **S13** | R08/R11 | Fulgora **deep** oil-ocean rail supports need special support-foundation research; ordinary oil ocean is different | W |
| **S14** | R13 | Fulgora lightning generation/intermittency needs charged storage and fail-safe electrical planning | T |
| **S15** | R06/R13 | Gleba spoilage occurs in inventory, belts, machines **and inserter hands**; buffer assumptions fail | W |
| **S16** | R06/R13 | Spoilage can go into machine trash slots but full outputs may block trash removal; dedicated extraction required | W |
| **S17** | R06/R13 | Stack inserter can wait for full hand, then immediately discard on spoilage/filter change; throughput/freshness varies | W |
| **S18** | R06/R13 | Biochambers rely on nutrient fuel that itself spoils; a stalled nutrient loop may need safe restart input | W |
| **S19** | R14 | Pentapod eggs/captive spawners can spoil/starve or release enemies; alarm, relocation, disposal and authorization matter | W/T |
| **S20** | R08/R13 | Aquilo buildings can freeze without sufficient adjacent heat; tile/build restrictions require ice platform/concrete | W |
| **S21** | R13 | Heat pipe load may lower downstream temperature; heating an adjacent pipe is not equivalent to guaranteeing full building heat | W/T |
| **S22** | R16 | Quality items of the same item name are different inventory/recipe variants; mixing wrong qualities may block crafting | W |
| **S23** | R16 | Fluids **do not have quality**, unlike items/entities; no bogus quality fluid stacks | W |
| **S24** | R16 | Quality output rolls, research tier caps, productivity, recycler losses and feedback loops require expected yield + variance, not certainty | W |
| **S25** | R11 | Elevated rail ramps require ground footprint and support geometry; deep oil rail supports differ from standard water | W |
| **S26** | R20 | A future third-party mod can redefine recipes/prototypes; Space Exploration spaceships are not Space Age platforms | T |

### Expansion references for S cases

- Content / component versions: https://wiki.factorio.com/Space_Age and https://factorio.com/blog/post/fff-442
- Space platforms and cargo: https://wiki.factorio.com/Space_platform
- Vulcanus/demolishers and casting: https://wiki.factorio.com/Vulcanus and https://wiki.factorio.com/Lava
- Fulgora and support foundations: https://wiki.factorio.com/Oil_ocean and https://wiki.factorio.com/Rail_support_foundations_%28research%29
- Recycler: https://wiki.factorio.com/Recycler
- Gleba and spoilage: https://wiki.factorio.com/Gleba and https://wiki.factorio.com/Spoilage_mechanics
- Stack inserter: https://wiki.factorio.com/Stack_inserter
- Aquilo heating and terrain: https://wiki.factorio.com/Aquilo and https://wiki.factorio.com/Heat_pipe
- Quality and fluid exception: https://wiki.factorio.com/Quality and https://wiki.factorio.com/Quality_module
- Elevated rail ramps/supports: https://wiki.factorio.com/Rail_ramp and https://wiki.factorio.com/Rail_support

## Video-derived quirks: review queue, not acceptance

Check whether a video actually demonstrates any B/S case rather than assuming the episode title proves an exact mechanic. Record the timestamp and exact game version, then confirm it through official pages or a permitted fixture.

| Video | Cases worth investigating |
|---|---|
| https://www.youtube.com/watch?v=n3yTCmzb0xE (Nilaus; Gleba farms/spoilage) | S15-S18, blocked trash and throughput |
| https://www.youtube.com/watch?v=YYju-rfgr5k (Nilaus; Gleba science) | S15-S19, science freshness and hatch risk |
| https://www.youtube.com/watch?v=i4Y2JgpLnAs (Nilaus; Fulgora factory) | S12-S14, scrap outputs and constrained land |
| https://www.youtube.com/watch?v=-71DCrRIwF4 (Nilaus; Aquilo factory) | S20-S21, heat supply and resupply |
| https://www.youtube.com/watch?v=QK5M_W5q600 (Rkadindoubt; circuit network explanation, 2026) | B21, 2.x combinator signal meanings and practical circuit tests |
| https://www.youtube.com/watch?v=R05jSixhI24 (Yorven; circuit-network examples, 2025) | B17/B21/B24, oil cracking, power, train limits and circuit controls; check listed mods |

For future YouTube findings, append in this form:

```text
ID: VIDEO-<N>
URL and timestamp:
Channel / upload date:
Game version and active content/mods:
Claim / unusual behavior:
Official Wiki/API or changelog cross-check:
Reproducible isolated fixture (synthetic/offline/live):
Expected vs observed:
R milestone / B or S case affected:
Evidence status: hypothesis / source-supported / live-verified
```

## Zoo acceptance discipline

- A **W** reference is an expected behavior to check, not R05 gameplay verification; **T** is still a proposed test. Promote to **V** only after separately approved, instrumented gameplay evidence.
- Do **not** automate all this as 59 game actions. Select the few cases relevant to the current R task; batch CPU-only fixtures safely and gate live tests.
- Never remove failed scenarios because an implementation finds them inconvenient. Any real discrepancy must become a regression test with the exact source/profile.
- Keep full autonomy locked. Never operate a save, issue arbitrary console/Lua commands, or weaken takeover/Stop to collect evidence.
