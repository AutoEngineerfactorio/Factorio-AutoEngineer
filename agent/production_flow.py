"""Bounded steady-state flow math; estimates never establish physical buildability.

Materials are caller-qualified identities (including fluid/quality/temperature).
Supplies are sustained units/second. Seed inventory only allows startup; it is
never counted as a renewable input. Surplus requires explicit disposal capacity.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Mapping


def nonnegative(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e12:
        raise ValueError("Finite nonnegative bounded quantity required")
    return float(value)


def quantities(values: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(values, Mapping) or len(values) > 50000:
        raise ValueError("Bounded material mapping required")
    result = {}
    for name, value in values.items():
        if not isinstance(name, str) or not name or len(name) > 240:
            raise ValueError("Bounded material identity required")
        result[name] = nonnegative(value)
    return result


@dataclass(frozen=True)
class FlowProcess:
    name: str
    inputs: Mapping[str, float]
    outputs: Mapping[str, float]
    crafts_per_second: float
    working_watts: float = 0
    idle_watts: float = 0
    max_machines: int = 1000000
    source_observed: bool = False
    basis: str = "deterministic"
    machine_group: str = ""

    def __post_init__(self):
        quantities({self.name: 0})
        if self.machine_group:
            quantities({self.machine_group: 0})
        object.__setattr__(self, "inputs", quantities(self.inputs))
        object.__setattr__(self, "outputs", quantities(self.outputs))
        if not any(self.outputs.values()) or nonnegative(self.crafts_per_second) <= 0:
            raise ValueError("Positive process capacity and output required")
        if not any(self.inputs.values()) and self.source_observed is not True:
            raise ValueError("Input-free sources require explicit observation")
        nonnegative(self.working_watts)
        nonnegative(self.idle_watts)
        if type(self.max_machines) is not int or not 0 <= self.max_machines <= 1000000:
            raise ValueError("Bounded integer machine limit required")
        if self.basis not in ("deterministic", "expected"):
            raise ValueError("Unsupported yield basis")


@dataclass(frozen=True)
class FlowRequest:
    demands: Mapping[str, float]
    supplies: Mapping[str, float]
    surplus_capacity: Mapping[str, float] = field(default_factory=dict)
    seed_inventory: Mapping[str, float] = field(default_factory=dict)
    power_budget_watts: float | None = None
    time_limit: float = 5

    def __post_init__(self):
        for name in ("demands", "supplies", "surplus_capacity", "seed_inventory"):
            object.__setattr__(self, name, quantities(getattr(self, name)))
        if not any(self.demands.values()):
            raise ValueError("Positive demand required")
        if self.power_budget_watts is not None:
            nonnegative(self.power_budget_watts)
        if not 0 < nonnegative(self.time_limit) <= 30:
            raise ValueError("Solver time limit must be between zero and 30 seconds")


def startable(processes: list[FlowProcess], request: FlowRequest) -> list[FlowProcess]:
    """Remove processes that cannot start without inventing catalyst stock."""
    available = dict(request.seed_inventory)
    available.update({name: math.inf for name, rate in request.supplies.items() if rate > 0})
    waiting: dict[str, list[int]] = defaultdict(list)
    missing = [0] * len(processes)
    for index, process in enumerate(processes):
        for name, amount in process.inputs.items():
            if available.get(name, 0) < amount:
                waiting[name].append(index)
                missing[index] += 1
    pending = deque(i for i, p in enumerate(processes) if missing[i] == 0 and p.max_machines)
    ready = []
    while pending:
        index = pending.popleft()
        process = processes[index]
        ready.append(process)
        for name, amount in process.outputs.items():
            if amount <= process.inputs.get(name, 0) or available.get(name) == math.inf:
                continue
            available[name] = math.inf
            for dependent in waiting.pop(name, ()):
                missing[dependent] -= 1
                if missing[dependent] == 0 and processes[dependent].max_machines:
                    pending.append(dependent)
    return ready


def solve_flow(processes: list[FlowProcess], request: FlowRequest,
               *, objective: str = "machines", machine_limits: Mapping[str, int] | None = None) -> dict:
    """Solve sparse mixed-integer balances; return only independently checked optima."""
    from importlib import import_module

    np = import_module("numpy")
    sparse = import_module("scipy.sparse")
    optimize = import_module("scipy.optimize")
    if objective not in ("machines", "power"):
        raise ValueError("Unknown flow objective")
    if len(processes) > 10000 or len({p.name for p in processes}) != len(processes):
        raise ValueError("Bounded unique processes required")
    edge_count = sum(len(p.inputs) + len(p.outputs) for p in processes)
    if edge_count > 200000:
        raise ValueError("Material edge budget exceeded")
    group_limits = quantities(machine_limits or {})
    if any(type(value) is not int or value > 1000000 for value in (machine_limits or {}).values()):
        raise ValueError("Shared machine limits must be bounded integers")
    groups = {name: index for index, name in enumerate(sorted(group_limits))}
    usable = startable(processes, request)
    names = set(request.demands) | set(request.supplies) | set(request.surplus_capacity)
    for process in usable:
        names.update(process.inputs)
        names.update(process.outputs)
    if len(names) > 50000:
        raise ValueError("Material budget exceeded")
    materials = sorted(names)
    index = {name: i for i, name in enumerate(materials)}
    imports, surplus = sorted(request.supplies), sorted(request.surplus_capacity)
    n = len(usable)
    size = 2 * n + len(imports) + len(surplus)
    if not size:
        return {"status": "infeasible", "reason": "No startable process or sustained supply"}
    balance = sparse.lil_matrix((len(materials), size))
    capacity = sparse.lil_matrix((n + 1 + len(groups), size))
    bounds: list[tuple[float, float | None]] = [(0, None)] * size
    power, cost = np.zeros(size), np.full(size, 1e-7)
    integers = np.zeros(size)
    for j, process in enumerate(usable):
        for name, amount in process.inputs.items():
            balance[index[name], j] -= amount
        for name, amount in process.outputs.items():
            balance[index[name], j] += amount
        capacity[j, j] = 1
        capacity[j, n + j] = -process.crafts_per_second
        bounds[n + j] = (0, process.max_machines)
        integers[n + j] = 1
        if process.machine_group in groups:
            capacity[n + 1 + groups[process.machine_group], n + j] = 1
        power[j] = process.working_watts / process.crafts_per_second
        power[n + j] = process.idle_watts
        cost[n + j] = 1
    for j, name in enumerate(imports, 2 * n):
        balance[index[name], j] = 1
        bounds[j] = (0, request.supplies[name])
    for j, name in enumerate(surplus, 2 * n + len(imports)):
        balance[index[name], j] = -1
        bounds[j] = (0, request.surplus_capacity[name])
    if objective == "power":
        cost = power + cost * 1e-3
    rhs = np.array([request.demands.get(name, 0) for name in materials])
    limits = np.zeros(n + 1 + len(groups))
    for name, row in groups.items():
        limits[n + 1 + row] = group_limits[name]
    if request.power_budget_watts is not None:
        capacity[n, :] = power
        limits[n] = request.power_budget_watts
    result = optimize.linprog(cost, A_ub=capacity.tocsr(), b_ub=limits,
        A_eq=balance.tocsr(), b_eq=rhs, bounds=bounds, integrality=integers,
        method="highs", options={"time_limit": request.time_limit, "mip_rel_gap": 0})
    if not result.success:
        return {"status": "infeasible" if result.status == 2 else "unavailable",
                "reason": str(result.message), "solver_status": int(result.status)}
    x = np.maximum(result.x, 0)
    residual = np.max(np.abs(balance @ x - rhs) / np.where(rhs > 0, rhs, 1.0), initial=0)
    violation = np.max((capacity @ x - limits) / (1 + np.abs(limits)), initial=0)
    integer_error = np.max(np.abs(x[n:2*n] - np.rint(x[n:2*n])), initial=0)
    active_without_machine = any(x[j] > 0 and round(x[n+j]) < 1 for j in range(n))
    bounds_error = any(x[j] > upper + 1e-6 * (1 + upper)
                       for j, (_, upper) in enumerate(bounds) if upper is not None)
    if (not np.all(np.isfinite(x)) or min(x) < -1e-6 or bounds_error or active_without_machine
            or max(residual, violation, integer_error) > 1e-6):
        return {"status": "unavailable", "reason": "Independent solution residual check failed"}
    return {"status": "estimated", "basis": "expected" if any(
                p.basis == "expected" and x[j] > 1e-8 for j, p in enumerate(usable)) else "deterministic",
        "crafts_per_second": {p.name: float(x[j]) for j, p in enumerate(usable) if x[j] > 0},
        "machines": {p.name: int(round(x[n+j])) for j, p in enumerate(usable) if x[n+j] > .5},
        "imports_per_second": {name: float(x[2*n+j]) for j, name in enumerate(imports)},
        "surplus_per_second": {name: float(x[2*n+len(imports)+j]) for j, name in enumerate(surplus)},
        "working_and_idle_watts": float(power @ x), "max_relative_residual": float(residual),
        "scope": "Steady-state estimate; transport, transient buffering and physical buildability require validation"}
