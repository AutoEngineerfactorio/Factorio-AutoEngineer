# Objective navigation — implemented and tested locally

Added a dashboard objective field (resource name or x,y) and equivalent environment setting. Targets remain fixed within a session. Qwen selects bounded offered steps ranked toward the objective; failed targets remain excluded. Arrival stops further proposals, and unobserved resource goals stop without movement. Three-proposal session budget remains.

The separately patched backend validates Factorio's computed route before walking: finite waypoints, valid endpoint, <=128 points, <=5-tile planned length and start radius, and fresh-position drift <=.5 tiles. Policy v3 is required; older backends are refused. Human approvals remain in the production dashboard; only the disposable-world harness supplied approvals under explicit user authorization.

Validation:
- 74 Python tests and 10 backend route tests passed.
- Release backend build: zero warnings/errors.
- Combined patch applied to clean pinned upstream and reproduced tested sources.
- Live resource objective: three verified short moves, decreasing remaining distance, then session-budget stop.
- Live coordinate objective: reached after one approved move; no extra proposal.
- Live Stop while walking: stopped after about .36 tiles, acknowledged, zero drift over 180 advancing ticks.
- Unobserved resource: zero proposals, approvals or displacement; stop acknowledged.
- All live sessions exited normally and ended stationary.

Used the same dedicated disposable save and persistent map identifier. Main game untouched. These results describe the local validation before publication. Planned path length does not guarantee exact traveled distance; dynamic collisions and overshoot still require watchdog/final verification. Goals are session settings, not persistent missions. Actual GUI clicking was not repeated; dashboard invalid-goal validation and existing button safety tests passed offline.
