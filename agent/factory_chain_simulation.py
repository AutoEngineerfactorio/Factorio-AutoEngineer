"""Constrained *offline* Factorio-like recipe flow fixture, not a game simulation.

Models a fixed 2.1.23 ordinary-item production chain with input availability,
crafting machine capacity, short transport caps and a simplified common power
fraction. Ore enters as a specified available external mining rate; actual
mining, belts/inserters, buffers, machine state and electricity are NOT modeled.
No Factorio process, game save or RCON is used.
"""
from __future__ import annotations

import math

from factory_reality_test import TICKS_PER_SECOND


def _rate(value: object, name: str, *, allow_zero: bool = False) -> float:
    if not isinstance(value, (int, float)) or type(value) not in (int, float):
        raise ValueError(f"Invalid finite {name}")
    if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        raise ValueError(f"Invalid finite {name}")
    return float(value)


def constrained_second(*, iron_ore_per_second=13.0, copper_ore_per_second=4.5,
                       power_fraction=1.0, iron_furnaces=21, copper_furnaces=8,
                       gear_assemblers=4, circuit_assemblers=2, cable_assemblers=3,
                       iron_transport_capacity=15.0, copper_transport_capacity=8.0):
    """One steady-state second of finite ingredient flows, no starting stock.

    Reference base recipes: 1 ore -> 1 plate per 3.2 s (furnace speed 2);
    2 plates -> 1 gear per .5 s; 1 copper plate -> 2 cables per .5 s;
    1 iron plate + 3 cables -> 1 electronic circuit per .5 s.
    Assembling-machine 2 crafting speed .75; no modules/productivity.
    """
    for name, count in (("iron_furnaces", iron_furnaces),
                        ("copper_furnaces", copper_furnaces),
                        ("gear_assemblers", gear_assemblers),
                        ("circuit_assemblers", circuit_assemblers),
                        ("cable_assemblers", cable_assemblers)):
        if type(count) is not int or not 0 <= count <= 200:
            raise ValueError(f"Invalid machine count: {name}")
    ore = _rate(iron_ore_per_second, "iron ore supply", allow_zero=True)
    copper_ore = _rate(copper_ore_per_second, "copper ore supply", allow_zero=True)
    iron_transport = _rate(iron_transport_capacity, "iron transport", allow_zero=True)
    copper_transport = _rate(copper_transport_capacity, "copper transport", allow_zero=True)
    power = _rate(power_fraction, "power", allow_zero=True)
    if power > 1:
        raise ValueError("Power fraction must not exceed 1")

    # Two output targets share a single iron plate supply and one copper supply.
    gear_target, circuit_target = 5.0, 3.0
    target_iron = 2 * gear_target + circuit_target          # 13 plates/s
    target_copper = 3 * circuit_target / 2                 # 4.5 plates/s
    target_cable = 3 * circuit_target                      # 9 cables/s
    target_capacities: dict[str, float] = {
        "iron_ore_supply": ore / target_iron,
        "copper_ore_supply": copper_ore / target_copper,
        "iron_furnaces": (iron_furnaces * 2 / 3.2) / target_iron,
        "copper_furnaces": (copper_furnaces * 2 / 3.2) / target_copper,
        "iron_transport": iron_transport / target_iron,
        "copper_transport": copper_transport / target_copper,
        "gear_assemblers": (gear_assemblers * .75 / .5) / gear_target,
        "circuit_assemblers": (circuit_assemblers * .75 / .5) / circuit_target,
        "cable_assemblers": (cable_assemblers * .75 / .5 * 2) / target_cable,
        "power_fraction": power,
    }
    bottleneck = min(target_capacities.items(), key=lambda item: item[1])[0]
    fraction = min(1.0, target_capacities[bottleneck])
    products = {
        "iron-plate": target_iron * fraction,
        "iron-gear-wheel": gear_target * fraction,
        "electronic-circuit": circuit_target * fraction,
        "copper-plate": target_copper * fraction,
        "copper-cable": target_cable * fraction,
        "water": 20.0,  # independent bounded fluid fixture, not an installed offshore pump
    }
    consumed = {
        "iron-plate": products["iron-gear-wheel"] * 2 + products["electronic-circuit"],
        "copper-plate": products["copper-cable"] / 2,
        "copper-cable": products["electronic-circuit"] * 3,
    }
    # Fail loudly if math ever creates more of an intermediate than it uses.
    for key, amount in consumed.items():
        if amount - products[key] > 1e-9:
            raise AssertionError("Fixture violates material balance")
    if products["iron-plate"] - ore > 1e-9 or products["copper-plate"] - copper_ore > 1e-9:
        raise AssertionError("Fixture creates ore")
    return {"products_per_second": products, "consumed_per_second": consumed,
            "available_ore_per_second": {"iron-ore": ore, "copper-ore": copper_ore},
            "utilization_fraction": fraction, "limiting_factor": (
                bottleneck if fraction < 1 else "none")}


def make_constrained_trace() -> dict:
    """10-minute game-tick-aligned flow trace from steady-state constrained steps.

    Minutes 5-7 deliberately reduce iron ore to 40% of required flow while
    power satisfaction drops to 55%; no stored surplus is assumed.
    """
    kind = {
        "iron-plate": "item", "iron-gear-wheel": "item",
        "electronic-circuit": "item", "copper-plate": "item",
        "copper-cable": "item", "water": "fluid",
    }
    ideal = constrained_second()["products_per_second"]
    targets = [
        {"kind": kind[name], "name": name,
         "target_per_minute": amount * 60,
         "predicted_per_minute": amount * 60}
        for name, amount in ideal.items()
    ]
    produced = {key: 0.0 for key in ideal}
    consumed = {"iron-plate": 0.0, "copper-plate": 0.0, "copper-cable": 0.0}
    samples = []
    for second in range(601):
        if second > 0:
            outage = 300 <= second - 1 < 420
            result = constrained_second(
                iron_ore_per_second=5.2 if outage else 13.0,
                power_fraction=.55 if outage else 1.0,
            )
            for key, amount in result["products_per_second"].items():
                produced[key] += amount
            for key, amount in result["consumed_per_second"].items():
                consumed[key] += amount
        else:
            outage = False

        def rows(values: dict) -> list:
            return [{"kind": kind[name], "name": name, "total": round(value, 8)}
                    for name, value in values.items()]

        samples.append({
            "tick": second * TICKS_PER_SECOND,
            "produced": rows(produced),
            "consumed": rows(consumed),
            "power_satisfaction": .55 if 300 <= second < 420 else 1.0,
        })
    return {
        "schema": 1,
        "evidence": "synthetic_fixture",
        "profile": {"game_version": "2.1.23", "force": "player", "surface": "nauvis",
                    "content": ["base"], "tick_rate": TICKS_PER_SECOND},
        "targets": targets,
        "samples": samples,
    }
