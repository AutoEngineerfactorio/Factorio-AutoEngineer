"""Live UPS admission gate for optional local AI inference.

Uses only registered, read-only Factorio status via launcher RCON; no game
writes or raw Lua. A new inference is refused unless four real tick samples
over >=12 seconds establish stable near-60 UPS. Only one HTTP model request
may be in flight per agent process. Unknown/disconnected is fail-closed.
This does not preempt a previously admitted model request; live acceptance
must measure its impact separately.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request
from contextlib import contextmanager
from typing import Callable, Iterator

from performance_governor import WorkBudget, guard_from_settings


class InferenceDeferred(RuntimeError):
    """AI planning is paused; gameplay observation remains available."""


class UPSAdmission:
    def __init__(self, sample_tick: Callable[[], int], *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 interval: float = 4.2):
        if interval < 4:
            raise ValueError("Use at least four seconds between live tick samples")
        self.sample_tick = sample_tick
        self.clock = clock
        self.sleep = sleep
        self.interval = interval

    def admit(self) -> WorkBudget:
        # The guard uses the configured UPS thresholds, so the Settings
        # really change when the optional work is paused.
        guard = guard_from_settings()
        budget = guard.budget()
        for index in range(4):
            try:
                tick = self.sample_tick()
                if type(tick) is not int or tick < 0:
                    raise ValueError("Missing verified game tick")
                budget = guard.observe(tick, self.clock())
            except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
                raise InferenceDeferred("Game observation unavailable; AI paused") from exc
            # Factorio/TimeTools may deliberately run at nonstandard speed:
            # that cannot be accepted as proof of near-60 UPS headroom.
            if budget.estimated_ups is not None and budget.estimated_ups > 61.5:
                raise InferenceDeferred("Nonstandard tick rate; AI paused")
            if budget.state in ("critical", "degraded"):
                raise InferenceDeferred("Game behind target; AI paused")
            if budget.ai_allowed:
                return budget
            if index < 3:
                self.sleep(self.interval)
        raise InferenceDeferred("Insufficient healthy UPS observations; AI paused")


def live_status_tick() -> int:
    """One localhost-only authenticated registered status read; fail closed."""
    from autoengineer_config import get_settings
    from launcher_services import Rcon

    secret = os.environ.get("FACTORIO_RCON_PASSWORD", "")
    if not secret:
        raise InferenceDeferred("No authenticated game observation; AI paused")
    settings = get_settings()
    if settings["rcon_host"] not in ("127.0.0.1", "localhost", "::1"):
        raise InferenceDeferred("RCON must be loopback")
    connection = Rcon(settings["rcon_port"], secret)
    try:
        status = connection.health()
        if status.get("players") != 1 or status.get("character") is not True:
            raise InferenceDeferred("Game/player status unavailable; AI paused")
        tick = status.get("tick")
        if type(tick) is not int or tick < 0:
            raise InferenceDeferred("Invalid game tick; AI paused")
        return tick
    finally:
        connection.close()


_model_lock = threading.Lock()

#: The semaphores that bound the concurrent model requests, one per
#: configured limit. The lock above stays the admission gate: every
#: request is admitted against the live game state, and only then does it
#: take a slot for its HTTP dispatch.
_model_slots: dict[int, threading.Semaphore] = {}


def inference_concurrency() -> int:
    """Return how many model requests may run at the same time.

    The limit comes from the settings. A missing or unusable value falls
    back to one, so the model is never flooded by default.
    """
    try:
        from runtime_settings import model_runtime

        limit = model_runtime().max_parallel_requests
    except Exception:
        return 1
    if type(limit) is not int or limit < 1:
        return 1
    return min(limit, 8)


def _model_semaphore() -> threading.Semaphore:
    """Return the semaphore for the configured concurrency.

    The semaphore is created once per limit and reused, so the limit is
    stable while the application runs. The limit is clamped here as well,
    so a wrong value can never produce a semaphore that blocks every
    request.
    """
    limit = inference_concurrency()
    if type(limit) is not int or limit < 1:
        limit = 1
    limit = min(limit, 8)
    with _model_lock:
        semaphore = _model_slots.get(limit)
        if semaphore is None:
            semaphore = threading.Semaphore(limit)
            _model_slots[limit] = semaphore
        return semaphore


@contextmanager
def guarded_urlopen(request: urllib.request.Request, *, timeout: float = 120
                    ) -> Iterator:
    """Protect all attached local-AI completion paths before HTTP dispatch.

    Does not modify game state, start extra processes or acquire the AI
    control lease. Existing callers can use it as a urlopen context manager.

    The request is admitted against the live game state first, and only
    then does it take one of the configured concurrency slots, so a burst
    of requests cannot overrun the model.
    """
    with _model_lock:
        UPSAdmission(live_status_tick).admit()
    with _model_semaphore():
        with urllib.request.urlopen(request, timeout=timeout) as response:
            yield response
