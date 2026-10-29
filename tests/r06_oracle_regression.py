"""Independent offline exact oracle for randomly generated valid DAGs.

Every synthetic recipe declares an explicit ``output_quantity_per_craft``. The
solver fails closed without it, so the oracle states the yield instead of
relying on an implicit value.

Output quantity per craft is the number of main output units one craft
produces. It is distinct from ``base_speed`` (items per second) and from
``energy_per_craft_kj`` (energy per craft, not power in kW).

Never edits repository sources, game data, or tests.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
sys.path.insert(0, str(ROOT))
from agent.production_solver import ProductionSolver, create_recipe

OUTPUT_QUANTITY_PER_CRAFT = 1.0

passed = 0
for seed in range(60):
    rng = random.Random(seed + 20261024)
    n = rng.randint(4, 28)
    target_qty = rng.randint(1, 4)
    inputs = {}
    bps = {}
    solver = ProductionSolver()
    for i in range(n):
        name = f"n{i:03d}"
        choices = [f"n{j:03d}" for j in range(i+1, n)]
        if choices and rng.random() < 0.85:
            chosen = rng.sample(choices, min(len(choices), rng.randint(1, 3)))
            inputs[name] = {item: rng.randint(1, 2) for item in chosen}
        else:
            inputs[name] = {"ore": rng.randint(1, 3)}
        if i == n-1:
            inputs[name] = {"ore": rng.randint(1, 3)}
        bps[name] = {"ore": rng.choice([0.0, 0.25, 0.5, 0.75]),
                     "scrap": rng.choice([0, 0.5, 1.0])}
        recipe = create_recipe(
            name, 1, 0,
            inputs=[{"prototype_id": k, "count": v} for k,v in inputs[name].items()],
            byproducts=[{"prototype_id": k, "count": v} for k,v in bps[name].items()],
            output_quantity_per_craft=OUTPUT_QUANTITY_PER_CRAFT,
        )
        solver.add_recipe(recipe)

    demand = defaultdict(float, {"n000": float(target_qty)})
    byproducts = defaultdict(float)
    gross_ore = 0.0
    for i in range(n):
        name=f"n{i:03d}"
        count=demand[name]
        for item,qty in inputs[name].items():
            if item=="ore":
                gross_ore+=count*qty
            else:
                demand[item]+=count*qty
        for item,qty in bps[name].items():
            byproducts[item]+=count*qty
    net_ore=max(0.0, gross_ore-byproducts["ore"])
    supplies = {"ore":net_ore} if net_ore else {}
    result=solver.compute_multi_recipe_material_flow(
        "n000",target_qty,supplies,0)
    if result.get("status")!="computed":
        raise AssertionError((seed,"status",result.get("status"),result.get("unresolved")))
    expected_selected={k:v for k,v in demand.items() if v>0}
    if result["selected_recipes"] != expected_selected:
        raise AssertionError((seed,"selected",result["selected_recipes"],expected_selected))
    expected_net = {"ore":net_ore} if net_ore else {}
    if result["net_material_requirements"]!=expected_net:
        raise AssertionError((seed,"net",result["net_material_requirements"],expected_net))
    actual_bp={x["prototype_id"]:x["count"] for x in result["total_byproducts"]}
    if actual_bp!=dict(byproducts):
        raise AssertionError((seed,"byproducts",actual_bp,dict(byproducts)))
    if net_ore:
        short=solver.compute_multi_recipe_material_flow(
            "n000",target_qty,{"ore":max(0.0,net_ore-0.5)},0)
        if short["status"]!="shortage" or "ore" not in short["shortages"]:
            raise AssertionError((seed,"shortage",short.get("status"),short.get("shortages")))
        absent=solver.compute_multi_recipe_material_flow("n000",target_qty,{},0)
        if absent["status"]!="unresolved":
            raise AssertionError((seed,"missing supply",absent["status"]))
    passed+=1
print(json.dumps({"independent_random_DAG_seeds":passed,
                  "oracle":"forward exact demand with separate byproduct accounting",
                  "cases":"selected recipe counts, net external material, byproducts, shortages, missing supplies",
                  "contract":"explicit output_quantity_per_craft per synthetic recipe",
                  "output_quantity_per_craft":OUTPUT_QUANTITY_PER_CRAFT,
                  "evidence_kind":"SYNTHETIC",
                  "status":"PASS"}),flush=True)
