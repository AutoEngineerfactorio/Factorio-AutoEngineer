"""Version-scoped base-game iron gear production-chain fixture (OFFLINE only).

The rates are normal-quality vanilla/first-party base recipes, with no modules,
beacons, productivity, quality bonuses, interruptions or logistic bottlenecks.
Values must be independently checked against the installed Factorio profile.
"""
import math


def _valid_positive(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("Requested rate must be finite and positive")
    return float(value)


def machine_stage(demand_per_second, *, cycle_seconds, crafting_speed,
                  yield_per_cycle, active_kw, drain_kw, prototype):
    demand_per_second = _valid_positive(demand_per_second)
    cycle_seconds = _valid_positive(cycle_seconds)
    crafting_speed = _valid_positive(crafting_speed)
    yield_per_cycle = _valid_positive(yield_per_cycle)
    active_kw = _valid_positive(active_kw)
    if type(drain_kw) not in (int, float) or not math.isfinite(drain_kw) or drain_kw < 0:
        raise ValueError("Invalid machine idle draw")
    per_machine = crafting_speed * yield_per_cycle / cycle_seconds
    count = math.ceil(demand_per_second / per_machine)
    utilization = demand_per_second / (count * per_machine)
    # Active power is scaled by occupancy; idle drain applies to each machine.
    avg_kw = (count * active_kw * utilization) + (count * drain_kw)
    return {
        "prototype": prototype,
        "machines": count,
        "per_machine_items_per_second": per_machine,
        "stage_capacity_items_per_second": count * per_machine,
        "demand_items_per_second": demand_per_second,
        "utilization_fraction": utilization,
        "estimated_average_power_kw": avg_kw,
        "installed_active_power_kw": active_kw * count,
        "installed_idle_draw_kw": drain_kw * count,
    }


def base_gears_chain(gears_per_minute: float = 300):
    """Conservative 2-stage gears and smelting fixture; no world simulation.

    Recipe: gear 2 iron plates -> 1 gear in 0.5s.
    Iron ore 1 -> 1 iron plate in 3.2s.
    Assembler 2: crafting speed 0.75; 150kW active + 5kW drain.
    Electric furnace: crafting speed 2; 180kW active + 6kW drain.
    """
    target_gear_rate = _valid_positive(gears_per_minute) / 60
    plate_rate = target_gear_rate * 2
    stage_gears = machine_stage(
        target_gear_rate, cycle_seconds=0.5, crafting_speed=0.75,
        yield_per_cycle=1, active_kw=150, drain_kw=5,
        prototype="assembling-machine-2",
    )
    stage_plates = machine_stage(
        plate_rate, cycle_seconds=3.2, crafting_speed=2,
        yield_per_cycle=1, active_kw=180, drain_kw=6,
        prototype="electric-furnace",
    )
    return {
        "evidence": "offline-math-only",
        "profile": "Factorio 2.x base recipes; no modules/bonuses; normal quality",
        "target_gears_per_minute": float(gears_per_minute),
        "target_gears_per_second": target_gear_rate,
        "required_iron_plates_per_second": plate_rate,
        "required_iron_ore_per_second": plate_rate,
        "stages": [stage_plates, stage_gears],
        "total_machine_count": stage_plates["machines"] + stage_gears["machines"],
        "estimated_average_power_kw": (
            stage_plates["estimated_average_power_kw"]
            + stage_gears["estimated_average_power_kw"]
        ),
        "preconditions": [
            "Complete research and access to both machines",
            "Sustained ore input and legal smelting/furnace inventory",
            "Sufficient connected electric supply and fuel where required",
            "Real belts/inserters/outputs must sustain stated rates",
            "No modules, beacons, output bonuses or downtime",
            "No gameplay/live throughput verification implied",
        ],
    }
