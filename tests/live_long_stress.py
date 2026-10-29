"""Sustained read-only stress: one 2.1.23 GUI-host + one local model per profile.

Run explicitly with --profile vanilla|py --seconds 300. Never uses dev console,
gameplay commands, new authentication, or existing user saves. Uses disposable
copies, private loopback RCON, the registered observation command and the
same UPS admission policy as the AI Helper. Cleans up only owned children.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
import psutil  # noqa: E402
from launcher_services import Rcon  # noqa: E402
from performance_governor import owned_process_creationflags  # noqa: E402
from r06_live_environment import MODDED_SAVE  # noqa: E402
from ups_inference import InferenceDeferred, guarded_urlopen  # noqa: E402

EXE = Path(r"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe")
VANILLA_MODS = EXE.parents[2] / "mods"
PY_MODS = ROOT / ".local/mod-test-mods/2.1.23"
SAVES = ROOT / ".local/launcher-profiles/2.1.23/data/saves"
AUTH = ROOT / ".local/live-pillow-2.1.23/client-profile/data/player-data.json"
SETTINGS = ROOT / ".local/launcher-profiles/2.1.23/server-settings.json"
PROFILE = ROOT / ".local/launcher-profiles/2.1.23/launcher.local.json"
OUTPUT = ROOT / ".local/live-long-stress"

def digest(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as fd:
        for chunk in iter(lambda: fd.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()

def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def tail_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values), "average": round(statistics.mean(values), 2),
        "minimum": round(min(values), 2),
        "p05": round(sorted(values)[max(0, int((len(values) - 1) * .05))], 2),
        "p50": round(statistics.median(values), 2),
        "below_58": sum(v < 58 for v in values),
        "below_59": sum(v < 59 for v in values),
    }

def start(executable: Path, args: list[str], log: Path, *, model=False):
    flags = owned_process_creationflags(
        "llama" if model else "host", windows=os.name == "nt",
        no_window=getattr(subprocess, "CREATE_NO_WINDOW", 0) if model else 0,
        below_normal=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
    with log.open("wb") as output:
        return subprocess.Popen(
            [str(executable), *args], cwd=str(executable.parent),
            stdout=output, stderr=subprocess.STDOUT, creationflags=flags)

def stop_owned(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=18)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=15)

def run(profile_name: str, duration: int, *,
        blueprint_file: Path | None = None, replicas: int = 0,
        diagnose_only: bool = False) -> int:
    if blueprint_file is not None and (profile_name != "py" or not 1 <= replicas <= 4):
        raise ValueError("Reviewed pY blueprint requires modded profile and 1–4 copies")
    if duration < 60 or duration > 1200:
        raise ValueError("Duration must be 60–1200 seconds")
    mods = VANILLA_MODS if profile_name == "vanilla" else PY_MODS
    source_save = (SAVES / "autoengineer-test.zip" if profile_name == "vanilla"
                   else MODDED_SAVE)
    for required in (EXE, source_save, AUTH, mods / "mod-list.json", SETTINGS, PROFILE):
        if not required.exists():
            print("BLOCKED missing prerequisite: " + required.name, flush=True)
            return 2
    mod_list = json.loads((mods / "mod-list.json").read_text(encoding="utf-8-sig"))
    enabled = {item["name"] for item in mod_list["mods"] if item.get("enabled")}
    if ("autoengineer-input" not in enabled or
            (profile_name == "py" and
             ("pyalienlife" not in enabled or "space-age" in enabled)) or
            (profile_name == "vanilla" and "space-age" not in enabled)):
        print("BLOCKED incorrect isolated mod profile", flush=True)
        return 2
    existing = [p.pid for p in psutil.process_iter(["name"]) if
                (p.info.get("name") or "").lower() in ("factorio.exe", "llama-server.exe")]
    if existing:
        print("BLOCKED existing Factorio or llama-server processes; not touching them",
              flush=True)
        return 2
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    work = OUTPUT / (profile_name + "-" + timestamp)
    work.mkdir(parents=True, exist_ok=False)
    data = work / "data"
    (data / "saves").mkdir(parents=True)
    shutil.copy2(AUTH, data / "player-data.json")
    copied = data / "saves" / "stress-disposable.zip"
    shutil.copy2(source_save, copied)
    source_sha = digest(source_save)
    rcon_port, model_port = port(), port()
    while model_port == rcon_port:
        model_port = port()
    password = secrets.token_urlsafe(32)
    ini = work / "host.private.ini"
    ini.write_text(
        "[path]\nread-data=" + str(EXE.parents[2] / "data").replace("\\", "/")
        + "\nwrite-data=" + str(data).replace("\\", "/")
        + "\n[other]\nlocal-rcon-socket=127.0.0.1:" + str(rcon_port)
        + "\nlocal-rcon-password=" + password
        + "\nenable-blueprint-storage-cloud-sync=false\n", encoding="utf-8")
    cfg = json.loads(PROFILE.read_text(encoding="utf-8-sig"))
    llm_exe, model = Path(cfg["llama_exe"]), Path(cfg["model_file"])
    model_url = f"http://127.0.0.1:{model_port}"
    ai_config = work / "ai.private.json"
    ai_config.write_text(json.dumps({
        "rcon_host": "127.0.0.1", "rcon_port": rcon_port,
        "llm_api_url": model_url + "/v1", "llm_model": "autoengineer-local",
    }), encoding="utf-8")
    assert llm_exe.exists() and model.exists()
    report: dict = {
        "profile": profile_name, "seconds_requested": duration,
        "mod_count": len(enabled), "has_pyanodons": "pyalienlife" in enabled,
        "save_sha_unchanged": False, "model_responses": 0,
        "model_tokens": 0, "deferred": 0, "errors": [],
        "ups": {}, "baseline": {}, "game_process_peak_mb": 0.0,
        "model_process_peak_mb": 0.0, "status_samples": 0,
        "telemetry_ok": 0, "telemetry_fail": 0, "ai_calls": 0,
        "model_ready": False,
    }
    host = None
    llm = None
    rcon = None
    sample_stop = threading.Event()
    samples: list[dict] = []
    thread = None
    previous_config = os.environ.get("AUTOENGINEER_CONFIG")
    previous_password = os.environ.get("FACTORIO_RCON_PASSWORD")
    def sample_loop() -> None:
        last_tick, last_at = None, None
        while not sample_stop.is_set():
            try:
                assert rcon is not None and host is not None
                response = json.loads(rcon.command("/autoengineer-observe status"))
                tick = response.get("tick")
                if (response.get("status") == "ok" and type(tick) is int and
                        tick >= 0):
                    now = time.monotonic()
                    game_memory = psutil.Process(host.pid).memory_info().rss / 1048576
                    model_memory = (psutil.Process(llm.pid).memory_info().rss / 1048576
                                    if llm is not None and llm.poll() is None else 0)
                    one = {"t": round(now, 3), "tick": tick,
                           "game_mb": round(game_memory, 1),
                           "model_mb": round(model_memory, 1),
                           "phase": "inference" if llm else "baseline"}
                    if last_tick is not None and last_at is not None and now > last_at:
                        one["ups"] = round((tick - last_tick) / (now - last_at), 3)
                    last_tick, last_at = tick, now
                    samples.append(one)
                    report["game_process_peak_mb"] = max(
                        report["game_process_peak_mb"], one["game_mb"])
                    report["model_process_peak_mb"] = max(
                        report["model_process_peak_mb"], one["model_mb"])
            except (OSError, RuntimeError, ValueError, AssertionError, KeyError):
                report["telemetry_fail"] += 1
            sample_stop.wait(2.0)
    try:
        print(f"[{profile_name}] Starting disposable GUI host with {len(enabled)} mods",
              flush=True)
        host = start(EXE, ["--config", str(ini), "--mod-directory", str(mods),
                           "--host", str(copied), "--server-settings", str(SETTINGS),
                           "--fullscreen=false"], work / "factorio.private.log")
        end = time.monotonic() + (360 if profile_name == "py" else 150)
        while time.monotonic() < end:
            if host.poll() is not None:
                raise RuntimeError("Factorio exited during startup")
            try:
                rcon = Rcon(rcon_port, password)
                health = json.loads(rcon.command("/autoengineer-observe status"))
                if health.get("status") == "ok" and type(health.get("tick")) is int:
                    break
                rcon.close()
                rcon = None
            except (OSError, RuntimeError, ValueError):
                if rcon is not None:
                    rcon.close()
                    rcon = None
            time.sleep(2)
        else:
            raise TimeoutError("Registered graphical-host status never became ready")
        if blueprint_file is not None:
            from live_blueprint_direct import creative_place
            from live_blueprint_stress import measure_activity

            print(f"[{profile_name}] Creative building {replicas} decoded community pY blueprint copies", flush=True)
            report["blueprint"] = creative_place(rcon, blueprint_file, replicas)
            time.sleep(8)
            report["blueprint_activity_before"] = measure_activity(rcon)
            print(f"[{profile_name}] Placed {report['blueprint']['actual_revived']} entities; "
                  f"activity={report['blueprint_activity_before']}", flush=True)
            if diagnose_only:
                from live_blueprint_direct import diagnose_machines

                report["activity_diagnostics"] = diagnose_machines(rcon)
                report["status"] = "diagnostic"
                print(f"[{profile_name}] Factory diagnostics: "
                      f"{report['activity_diagnostics']}", flush=True)
                return 0
            activity = report["blueprint_activity_before"]
            if activity["working_distilators"] + activity["working_pumps"] < 50:
                raise RuntimeError("Blueprint not actively producing; refusing to label layout-only test as a factory stress test")
        thread = threading.Thread(target=sample_loop, daemon=True)
        thread.start()
        time.sleep(22)
        before = [s["ups"] for s in samples if "ups" in s]
        report["baseline"] = tail_stats(before)
        print(f"[{profile_name}] Baseline {report['baseline']} UPS", flush=True)
        llm = start(llm_exe, [
            "--model", str(model), "--host", "127.0.0.1", "--port", str(model_port),
            "--ctx-size", "3072", "--parallel", "1", "--threads", "4",
            "--n-gpu-layers", "99", "--alias", "autoengineer-local",
        ], work / "llama.private.log", model=True)
        end = time.monotonic() + 180
        while time.monotonic() < end:
            if llm.poll() is not None:
                raise RuntimeError("Model server exited before ready")
            try:
                with urllib.request.urlopen(model_url + "/health", timeout=3) as response:
                    if response.status == 200:
                        report["model_ready"] = True
                        break
            except (OSError, ValueError):
                pass
            time.sleep(2)
        if not report["model_ready"]:
            raise TimeoutError("Model server did not become ready")
        os.environ["AUTOENGINEER_CONFIG"] = str(ai_config)
        os.environ["FACTORIO_RCON_PASSWORD"] = password
        end = time.monotonic() + duration
        last_report = time.monotonic()
        while time.monotonic() < end:
            if host.poll() is not None or llm.poll() is not None:
                raise RuntimeError("Owned game or AI server exited under load")
            # One read-only short planning completion; gated on observed UPS.
            request = urllib.request.Request(
                model_url + "/v1/chat/completions", method="POST",
                headers={"Content-Type": "application/json"},
                data=json.dumps({"model": "autoengineer-local", "temperature": 0.1,
                                 "max_tokens": 256, "stream": False,
                                 "messages": [{"role": "system",
                                   "content": "You are a read-only Factorio production planning assistant. Do not execute actions."},
                                  {"role": "user", "content": "Provide a concise checklist for planning a balanced iron production line using observed recipes, power capacity, throughput and byproducts. Do not invent recipe amounts."}]}).encode())
            report["ai_calls"] += 1
            try:
                with guarded_urlopen(request, timeout=125) as response:
                    data_out = json.load(response)
                if data_out.get("choices"):
                    report["model_responses"] += 1
                    report["model_tokens"] += int(
                        (data_out.get("usage") or {}).get("completion_tokens") or 0)
                else:
                    report["errors"].append("Model returned no choices")
            except InferenceDeferred as ex:
                report["deferred"] += 1
                if report["deferred"] <= 3:
                    print(f"[{profile_name}] UPS gate deferred request: {str(ex)}", flush=True)
                time.sleep(5)
            except (OSError, ValueError, TimeoutError) as ex:
                report["errors"].append(type(ex).__name__ + ": " + str(ex)[:150])
                break
            if time.monotonic() - last_report >= 27:
                rr = tail_stats([s["ups"] for s in samples[-35:] if "ups" in s])
                print(f"[{profile_name}] elapsed-load={duration-max(0,int(end-time.monotonic()))}s "
                      f"UPS={rr.get('average')} min={rr.get('minimum')} "
                      f"AI responses={report['model_responses']}", flush=True)
                last_report = time.monotonic()
        report["test_elapsed_load_s"] = duration - max(0, end - time.monotonic())
        report["status"] = "pass" if report["model_responses"] >= 2 and not report["errors"] else "partial"
    except Exception as ex:
        report["status"] = "failed"
        report["errors"].append(type(ex).__name__ + ": " + str(ex)[:220])
        print(f"[{profile_name}] ERROR {type(ex).__name__}: {str(ex)[:150]}", flush=True)
    finally:
        sample_stop.set()
        if thread is not None:
            thread.join(timeout=7)
        if rcon is not None:
            if blueprint_file is not None and host is not None and host.poll() is None:
                try:
                    from live_blueprint_stress import measure_activity

                    report["blueprint_activity_after"] = measure_activity(rcon)
                    activity = report["blueprint_activity_after"]
                    if (activity["working_distilators"] + activity["working_pumps"] < 50
                            and report.get("status") == "pass"):
                        report["status"] = "partial"
                        report["errors"].append("Factory stopped actively producing during stress")
                except (OSError, RuntimeError, ValueError) as exc:
                    report["errors"].append("Post-stress activity: " + str(exc)[:100])
            rcon.close()
        stop_owned(llm)
        stop_owned(host)
        if previous_config is None:
            os.environ.pop("AUTOENGINEER_CONFIG", None)
        else:
            os.environ["AUTOENGINEER_CONFIG"] = previous_config
        if previous_password is None:
            os.environ.pop("FACTORIO_RCON_PASSWORD", None)
        else:
            os.environ["FACTORIO_RCON_PASSWORD"] = previous_password
        report["save_sha_unchanged"] = digest(source_save) == source_sha
        report["status_samples"] = len(samples)
        report["ups"] = tail_stats([s["ups"] for s in samples
                                     if "ups" in s and s["phase"] == "inference"])
        report["all_ups"] = tail_stats([s["ups"] for s in samples if "ups" in s])
        report["source_save_name"] = source_save.name
        (work / "samples.json").write_text(json.dumps(samples), encoding="utf-8")
        (work / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[{profile_name}] DONE {report['status']} {report['ups']} "
              f"responses={report['model_responses']} output={work / 'result.json'}",
              flush=True)
    return 0 if report.get("status") == "pass" and report["save_sha_unchanged"] else 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("vanilla", "py"), required=True)
    parser.add_argument("--seconds", type=int, default=300)
    parser.add_argument("--blueprint-file", type=Path)
    parser.add_argument("--replicas", type=int, default=0)
    parser.add_argument("--diagnose-only", action="store_true")
    args = parser.parse_args()
    raise SystemExit(run(args.profile, args.seconds,
                         blueprint_file=args.blueprint_file,
                         replicas=args.replicas, diagnose_only=args.diagnose_only))
