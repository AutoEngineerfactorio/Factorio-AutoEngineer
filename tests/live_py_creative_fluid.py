"""Continuous creative fluid supply for disposable full-Pyanodons blueprint stress.

Uses Factorio 2.1 LuaEntity.insert_fluid/extract_fluid, not deleted .fluidbox.
This standalone wrapper NEVER edits the concurrently locked original harness.
Feed and output extraction happen ONLY on the isolated 'ae-py-blueprint-stress'
surface owned by an auto-generated disposable save. A separate local RCON
connection avoids racing status sampling on the main harness connection.
"""
from __future__ import annotations

import argparse
import configparser
import json
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tests"))

import live_blueprint_direct  # noqa: E402
import live_long_stress  # noqa: E402
from launcher_services import Rcon  # noqa: E402

BLUEPRINT = ROOT / ".local/blueprint-stress/py-oxygen-nitrogen-source.txt"
ROOT_RUNS = ROOT / ".local/live-long-stress"

# Creative-only operation: each fluid product is removed from its machine
# and each fluid ingredient is supplied to its input at a bounded volume.
# Recipe fluid names come from live Factorio prototypes, not guesses.
# All writes target a named disposable stress-test surface.
FLUID_LUA = (
    "local s=game.surfaces['ae-py-blueprint-stress'];"
    "if not s then rcon.print('AE_FLUID_ERR:NO_SURFACE');return end;"
    "local added=0;local drained=0;local working=0;"
    "local failed=0;local recipes=0;local fluid_inputs={};local fluid_outputs={};"
    "for _,name in pairs({'distilator','vacuum-pump-mk01'}) do "
    "for _,e in pairs(s.find_entities_filtered{name=name}) do "
    "if e.valid then "
    "local rec=e.get_recipe();"
    "if rec then recipes=recipes+1;"
    "for _,product in pairs(rec.products) do "
    "if product.type=='fluid' then "
    "fluid_outputs[product.name]=true;"
    "local ok,amount=pcall(function() return e.extract_fluid{"
    "name=product.name,amount=25000} end);"
    "if ok then drained=drained+(amount or 0) else failed=failed+1 end end end;"
    "for _,ingredient in pairs(rec.ingredients) do "
    "if ingredient.type=='fluid' then "
    "fluid_inputs[ingredient.name]=true;"
    "local ok,amount=pcall(function() return e.insert_fluid{"
    "name=ingredient.name,amount=600} end);"
    "if ok then added=added+(amount or 0) else failed=failed+1 end end end "
    "end;"
    "if e.status==defines.entity_status.working then working=working+1 end "
    "end end end;"
    "local ins={};local outs={};"
    "for name,_ in pairs(fluid_inputs) do ins[#ins+1]=name end;"
    "for name,_ in pairs(fluid_outputs) do outs[#outs+1]=name end;"
    "table.sort(ins);table.sort(outs);"
    "rcon.print('AE_FLUID_DATA:'..helpers.table_to_json({"
    "added=added,drained=drained,working=working,recipes=recipes,"
    "errors=failed,inputs=ins,outputs=outs}))"
)


class FeedWatch:
    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.samples: list[dict] = []
        self.errors: list[str] = []
        self.stalled = False
        self._low = 0

    def start(self, original_rcon: Rcon) -> None:
        if self.thread is not None:
            raise RuntimeError("Fluid feed watcher already running")
        endpoint = original_rcon.sock.getpeername()
        if endpoint[0] != "127.0.0.1":
            raise RuntimeError("Refusing non-loopback RCON connection")
        port = endpoint[1]
        candidates = sorted(ROOT_RUNS.glob("py-*"), key=lambda p: p.name)
        if not candidates:
            raise RuntimeError("Disposable test run directory not found")
        config = configparser.ConfigParser()
        config.read(candidates[-1] / "host.private.ini")
        target = config.get("other", "local-rcon-socket")
        if target != f"127.0.0.1:{port}":
            raise RuntimeError("RCON endpoint is not owned by latest disposable save")
        password = config.get("other", "local-rcon-password")

        def worker() -> None:
            conn = None
            try:
                conn = Rcon(port, password)
                # Console gate was already verified by creative_place.
                while not self.stop.is_set():
                    response = conn.command("/c " + FLUID_LUA)
                    match = re.search(r"AE_FLUID_DATA:(\{.*\})", response)
                    if not match:
                        raise RuntimeError("Creative fluid command not confirmed: " + response[:140])
                    value = json.loads(match.group(1))
                    value["at"] = round(time.monotonic(), 2)
                    self.samples.append(value)
                    if value.get("errors"):
                        raise RuntimeError("Factorio rejected fluid API commands: "
                                           + str(value["errors"]))
                    if value.get("recipes", 0) < 60:
                        raise RuntimeError("Too few live production recipes")
                    if value.get("working", 0) < 50:
                        self._low += 1
                    else:
                        self._low = 0
                    if self._low >= 3:
                        self.stalled = True
                        raise RuntimeError("Factory had under 50 working machines for "
                                           "three successive creative-fluid samples")
                    if self.stop.wait(self.interval):
                        break
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                self.errors.append(type(exc).__name__ + ": " + str(exc)[:180])
                self.stalled = True
            finally:
                if conn is not None:
                    conn.close()

        self.thread = threading.Thread(target=worker, daemon=True,
                                       name="creative-fluid-disposable-only")
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=8)


def run(replicas: int, seconds: int, diagnose: bool = False) -> int:
    if not BLUEPRINT.is_file():
        raise FileNotFoundError("Previously reviewed blueprint exchange file missing")
    watcher = FeedWatch()
    place_original = live_blueprint_direct.creative_place
    guarded_original = live_long_stress.guarded_urlopen
    stop_original = live_long_stress.stop_owned

    def supplied_place(rcon, path, copies):
        details = place_original(rcon, path, copies)
        watcher.start(rcon)
        return details

    @contextmanager
    def abort_if_stalled(request, *, timeout=125):
        if watcher.stalled:
            raise RuntimeError("Creative fluid factory stalled: "
                               + "; ".join(watcher.errors[-2:]))
        with guarded_original(request, timeout=timeout) as response:
            yield response

    def stop_after_feed(proc):
        # Keep the game alive until its final feed/observation call has ended.
        watcher.close()
        stop_original(proc)

    live_blueprint_direct.creative_place = supplied_place
    live_long_stress.guarded_urlopen = abort_if_stalled
    live_long_stress.stop_owned = stop_after_feed
    try:
        result = live_long_stress.run(
            "py", seconds, blueprint_file=BLUEPRINT,
            replicas=replicas, diagnose_only=diagnose)
    finally:
        watcher.close()
        live_blueprint_direct.creative_place = place_original
        live_long_stress.guarded_urlopen = guarded_original
        live_long_stress.stop_owned = stop_original
        candidates = sorted(ROOT_RUNS.glob("py-*"), key=lambda p: p.name)
        if candidates:
            output = candidates[-1] / "creative-fluid.json"
            report = {
                "mode": "creative-fluid-current-api",
                "samples": watcher.samples,
                "errors": watcher.errors,
                "stalled": watcher.stalled,
                "last": watcher.samples[-1] if watcher.samples else None,
            }
            output.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"[fluid] Samples={len(watcher.samples)} "
                  f"stalled={watcher.stalled} errors={watcher.errors[-2:]} "
                  f"evidence={output}", flush=True)
    if watcher.stalled:
        return 1
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicas", type=int, default=1, choices=(1, 2, 3, 4))
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--diagnose-only", action="store_true")
    parsed = parser.parse_args()
    raise SystemExit(run(parsed.replicas, parsed.seconds, parsed.diagnose_only))
