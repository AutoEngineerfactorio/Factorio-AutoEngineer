"""Independent offline R06 DAG benchmark for the corrected per-craft contract.

Each synthetic recipe declares an explicit ``output_quantity_per_craft``. The
solver fails closed when that value is missing, so the benchmark states it
rather than relying on an implicit yield.

Output quantity per craft is the number of main output units one craft
produces. It is distinct from ``base_speed`` (items per second) and from
``energy_per_craft_kj`` (energy per craft, not power in kW).

No source mutations, game launches, API calls, or dependency installations.
Peak RSS is sampled by the parent using psutil; records include both RSS and
the sampled baseline.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
SAVE = Path(__file__).with_name("r06_independent_benchmark_result.json")
SIZES = (1000, 5000, 10000)
CASES = ("chain", "fanout")

# Explicit output quantity per craft for every synthetic recipe. A value of 1
# means one main output unit per craft; it is not an items-per-second rate.
OUTPUT_QUANTITY_PER_CRAFT = 1.0


def child_case(kind: str, n: int):
    sys.path.insert(0, str(ROOT))
    from agent.production_solver import ProductionSolver, create_recipe

    t0 = time.perf_counter()
    solver = ProductionSolver()
    if kind == "chain":
        for i in range(n):
            need = f"n{i+1:05}" if i + 1 < n else "ore"
            solver.add_recipe(create_recipe(
                f"n{i:05}", 1.0, 0.0,
                inputs=[{"prototype_id": need, "count": 1}],
                output_quantity_per_craft=OUTPUT_QUANTITY_PER_CRAFT,
            ))
        target = "n00000"
        supply = {"ore": 1.0}
        expected = 1.0
        recipes_expected = n
    elif kind == "fanout":
        for i in range(n):
            solver.add_recipe(create_recipe(
                f"piece{i:05}", 1.0, 0.0,
                inputs=[{"prototype_id": "ore", "count": 1}],
                output_quantity_per_craft=OUTPUT_QUANTITY_PER_CRAFT,
            ))
        solver.add_recipe(create_recipe(
            "final", 1.0, 0.0,
            inputs=[{"prototype_id": f"piece{i:05}", "count": 1}
                    for i in range(n)],
            output_quantity_per_craft=OUTPUT_QUANTITY_PER_CRAFT,
        ))
        target = "final"
        supply = {"ore": float(n)}
        expected = float(n)
        recipes_expected = n + 1
    else:
        raise ValueError(kind)
    build_seconds = time.perf_counter() - t0
    t1 = time.perf_counter()
    result = solver.compute_multi_recipe_material_flow(target, 1.0, supply, 0.0)
    solve_seconds = time.perf_counter() - t1
    report = {
        "scenario": kind, "nodes": n, "status": result["status"],
        "output_quantity_per_craft": OUTPUT_QUANTITY_PER_CRAFT,
        "expected_external_ore": expected,
        "actual_external_ore": result.get("net_material_requirements", {}).get("ore"),
        "expected_selected_count": recipes_expected,
        "actual_selected_count": len(result.get("selected_recipes", {})),
        "has_cycle": result.get("has_cycle"), "energy_limiting": result.get("energy_limiting"),
        "build_seconds": round(build_seconds, 5),
        "solve_seconds": round(solve_seconds, 5),
    }
    report["pass"] = (
        result["status"] == "computed"
        and report["actual_external_ore"] == expected
        and report["actual_selected_count"] == recipes_expected
        and not report["has_cycle"]
        and not report["energy_limiting"]
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    return int(not report["pass"])


def parent():
    results = []
    for kind in CASES:
        for n in SIZES:
            args = [sys.executable, "-B", __file__, "--child", kind, str(n)]
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, cwd=ROOT)
            start = time.monotonic()
            baseline_rss = 0
            peak_rss = 0
            hit_timeout = False
            while proc.poll() is None:
                try:
                    rss = psutil.Process(proc.pid).memory_info().rss
                    peak_rss = max(peak_rss, rss)
                    if not baseline_rss:
                        baseline_rss = rss
                except psutil.Error:
                    pass
                if time.monotonic() - start >= 90:
                    proc.kill()
                    hit_timeout = True
                    break
                time.sleep(0.02)
            stdout, stderr = proc.communicate(timeout=7)
            try:
                data = json.loads(stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                data = {"scenario": kind, "nodes": n, "pass": False,
                        "exception": stderr[-800:]}
            data.update({
                "exit_code": proc.returncode,
                "timed_out_90_seconds": hit_timeout,
                "peak_process_rss_mib": round(peak_rss / (1024**2), 2),
                "initial_sampled_rss_mib": round(baseline_rss / (1024**2), 2),
                "peak_delta_rss_mib": round(max(0, peak_rss - baseline_rss) / (1024**2), 2),
                "wall_seconds_including_startup": round(time.monotonic()-start, 3),
            })
            data["pass"] = bool(data.get("pass") and proc.returncode == 0 and not hit_timeout)
            results.append(data)
            print("INDEPENDENT_BENCHMARK " + json.dumps(data, sort_keys=True), flush=True)
            SAVE.write_text(json.dumps({
                "method": "parent sampled peak child RSS (psutil)",
                "contract": "explicit output_quantity_per_craft per synthetic recipe",
                "evidence_kind": "SYNTHETIC",
                "versions": {"python": sys.version.split()[0]},
                "runs": results}, indent=2)+"\n", encoding="utf8")
    print("ALL_BENCHMARKS_PASS=" + str(all(x["pass"] for x in results)), flush=True)
    return 0 if all(x["pass"] for x in results) else 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        raise SystemExit(child_case(sys.argv[2], int(sys.argv[3])))
    raise SystemExit(parent())
