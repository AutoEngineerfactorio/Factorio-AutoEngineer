"""Deterministic, offline pY-shaped stress fixtures for the existing R06 graph walker.

These are synthetic fixtures, NOT Pyanodons recipe data or gameplay certification.
No Factorio process, save, mod installer, RCON or external service is accessed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
import tracemalloc

# The existing solver supports direct imports from the agent directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from production_solver import MaterialInput, ProductionSolver, Recipe


def build_synthetic_profile(size: int) -> ProductionSolver:
    """Make a wide, shallow graph containing alternate routes, loops and byproducts."""
    if not 1 <= size <= 50000:
        raise ValueError("size must be between 1 and 50000")
    solver = ProductionSolver(profile_version="synthetic-modded-v1")
    root = Recipe(
        prototype_id="benchmark-target",
        base_speed=1.0,
        energy_usage=1.0,
        inputs=[MaterialInput(f"intermediate-{i}", 1) for i in range(size)],
    )
    solver.add_recipe(root)
    for i in range(size):
        inputs = [MaterialInput("raw-feed", 1)]
        if i > 0 and i % 97 == 0:
            inputs.append(MaterialInput(f"intermediate-{i-1}", 1))
        if i % 199 == 0:
            inputs.append(MaterialInput("benchmark-target", 1))
        alternatives = []
        if i % 5 == 0:
            alternatives.append(
                Recipe(
                    prototype_id=f"intermediate-{i}-alternative",
                    base_speed=0.75,
                    energy_usage=1.5,
                    inputs=[MaterialInput("raw-feed", 2)],
                )
            )
        solver.add_recipe(
            Recipe(
                prototype_id=f"intermediate-{i}",
                base_speed=1.0,
                energy_usage=2.0,
                inputs=inputs,
                alternatives=alternatives,
                byproducts=(
                    [{"prototype_id": f"byproduct-{i % 17}", "count": 0.5}]
                    if i % 3 == 0 else []
                ),
            )
        )
    return solver


def run_benchmark(size: int) -> dict[str, object]:
    """Report results without claiming any real mod content or imposing hardware thresholds."""
    tracemalloc.start()
    try:
        construction_start = perf_counter()
        solver = build_synthetic_profile(size)
        construction_ms = (perf_counter() - construction_start) * 1000
        graph_start = perf_counter()
        result = solver.compute_recipe_graph("benchmark-target", {}, float("inf"))
        traversal_ms = (perf_counter() - graph_start) * 1000
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    if not result["found"] or result["truncated"]:
        raise RuntimeError("Synthetic recipe graph incomplete")
    expected_nodes = size + (size + 4) // 5 + 2  # intermediates, alts, root, raw
    if len(result["graph"]) != expected_nodes:
        raise RuntimeError(
            f"Graph node mismatch: {len(result['graph'])} != {expected_nodes}"
        )
    return {
        "dataset": "synthetic-modded-v1",
        "actual_pyanodons_data": False,
        "recipe_count": size,
        "graph_nodes": len(result["graph"]),
        "cycle_count": len(result["cycles"]),
        "truncated": result["truncated"],
        "construction_ms": round(construction_ms, 3),
        "traversal_ms": round(traversal_ms, 3),
        "peak_memory_mib": round(peak_bytes / (1024 ** 2), 3),
        "python": sys.version.split()[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000])
    options = parser.parse_args()
    print(json.dumps([run_benchmark(size) for size in options.sizes], indent=2))


if __name__ == "__main__":
    main()
