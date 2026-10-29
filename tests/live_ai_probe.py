"""Disposable graphical-host + one local llama.cpp performance probe.

Only read-only /autoengineer-observe status requests and one bounded model
HTTP call. No autonomous gameplay, save changes, or second game process.
The caller owns its copied-save Factorio host; this module owns and stops
only the model process it creates. Secrets stay in local environment/config.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

import psutil  # noqa: E402
from performance_governor import owned_process_creationflags  # noqa: E402
from ups_inference import InferenceDeferred, guarded_urlopen, live_status_tick  # noqa: E402


def port_available() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/health", timeout=3) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def rates(samples: list[tuple[float, int]]) -> list[float]:
    measured = []
    for i, (moment, tick) in enumerate(samples):
        if i == 0:
            continue
        elapsed = moment - samples[i - 1][0]
        diff = tick - samples[i - 1][1]
        if elapsed > 0.4 and diff >= 0:
            measured.append(diff / elapsed)
    return measured


def run(port: int, password: str, work: Path) -> dict:
    result: dict = {"status": "unavailable", "reason": "",
                    "model_response": False, "tokens": 0,
                    "baseline_ups": None, "inference_ups_min": None,
                    "inference_ups_average": None, "model_peak_rss_mb": None,
                    "model_pid": None, "inference_seconds": None,
                    "samples": 0}
    profile_path = ROOT / ".local/launcher-profiles/2.1.23/launcher.local.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    exe = Path(profile["llama_exe"])
    model = Path(profile["model_file"])
    if not exe.is_file() or not model.is_file():
        result["reason"] = "Configured local inference runtime/model is missing"
        return result

    model_port = port_available()
    url = f"http://127.0.0.1:{model_port}"
    config = work / "ai-runtime.private.json"
    config.write_text(json.dumps({
        "rcon_host": "127.0.0.1", "rcon_port": port,
        "llm_api_url": url + "/v1", "llm_model": "autoengineer-local",
    }), encoding="utf-8")
    before_config = os.environ.get("AUTOENGINEER_CONFIG")
    before_secret = os.environ.get("FACTORIO_RCON_PASSWORD")
    os.environ["AUTOENGINEER_CONFIG"] = str(config)
    os.environ["FACTORIO_RCON_PASSWORD"] = password
    proc: subprocess.Popen | None = None
    sample_stop = threading.Event()
    readings: list[tuple[float, int]] = []
    sample_thread: threading.Thread | None = None
    try:
        # Match launcher policy: new inference BELOW_NORMAL, Factorio never
        # reprioritized. Limit CPU and memory pressure with 4 threads, one
        # slot and a 2k context. Existing model processes are never adopted.
        flags = owned_process_creationflags(
            "llama", windows=os.name == "nt",
            no_window=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            below_normal=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        args = [
            str(exe), "--model", str(model), "--host", "127.0.0.1",
            "--port", str(model_port), "--ctx-size", "2048", "--parallel", "1",
            "--threads", "4", "--n-gpu-layers", "99", "--alias", "autoengineer-local",
        ]
        with (work / "llama-private.log").open("wb") as log:
            proc = subprocess.Popen(args, cwd=str(exe.parent),
                                    stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=flags)
        result["model_pid"] = proc.pid
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("Local model process exited before readiness")
            if health(url):
                break
            time.sleep(1)
        else:
            raise TimeoutError("Local model did not become ready")

        # Establish idle baseline while the GPU-resident model is loaded.
        at0, t0 = time.monotonic(), live_status_tick()
        time.sleep(5)
        baseline = (live_status_tick() - t0) / (time.monotonic() - at0)
        result["baseline_ups"] = round(baseline, 2)
        result["status"] = "testing"

        process = psutil.Process(proc.pid)
        max_rss = [process.memory_info().rss]

        def sampler() -> None:
            while not sample_stop.is_set():
                try:
                    readings.append((time.monotonic(), live_status_tick()))
                    max_rss[0] = max(max_rss[0], process.memory_info().rss)
                except (OSError, RuntimeError, ValueError):
                    pass
                sample_stop.wait(1)

        sample_thread = threading.Thread(target=sampler, daemon=True)
        sample_thread.start()
        request = urllib.request.Request(
            url + "/v1/chat/completions",
            data=json.dumps({
                "model": "autoengineer-local", "temperature": 0.1,
                "max_tokens": 48, "stream": False,
                "messages": [{"role": "user",
                              "content": "Reply with a short acknowledgement of this read-only Factorio AI Helper test."}],
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        started = time.monotonic()
        with guarded_urlopen(request, timeout=120) as response:
            message = json.load(response)
        result["inference_seconds"] = round(time.monotonic() - started, 2)
        result["model_response"] = bool(message.get("choices"))
        result["tokens"] = int((message.get("usage") or {}).get("completion_tokens") or 0)
        result["status"] = "pass" if result["model_response"] else "failed"
        if not result["model_response"]:
            result["reason"] = "No model completion choices returned"
    except InferenceDeferred as exc:
        result["status"] = "deferred"
        result["reason"] = str(exc)
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as exc:
        result["status"] = "failed"
        result["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    finally:
        sample_stop.set()
        if sample_thread is not None:
            sample_thread.join(timeout=5)
        ups_rates = rates(readings)
        result["samples"] = len(readings)
        if ups_rates:
            result["inference_ups_min"] = round(min(ups_rates), 2)
            result["inference_ups_average"] = round(sum(ups_rates) / len(ups_rates), 2)
        if proc is not None:
            try:
                result["model_peak_rss_mb"] = round(max_rss[0] / 1048576, 1)
            except (NameError, IndexError):
                pass
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
        if before_config is None:
            os.environ.pop("AUTOENGINEER_CONFIG", None)
        else:
            os.environ["AUTOENGINEER_CONFIG"] = before_config
        if before_secret is None:
            os.environ.pop("FACTORIO_RCON_PASSWORD", None)
        else:
            os.environ["FACTORIO_RCON_PASSWORD"] = before_secret
    return result
