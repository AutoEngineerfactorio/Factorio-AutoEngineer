"""Small JSONL audit records; arbitrary text, credentials and paths are excluded."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import uuid

FIELDS = {"cycle", "approved", "moved", "remaining", "progress", "elapsed", "count"}
EVENTS = {"session_start", "policy_verified", "proposal", "approval", "dispatch",
          "movement_arrived", "movement_failed", "movement_stalled", "movement_repeated",
          "route_recovery", "stop_requested", "stop_confirmed", "stop_unconfirmed", "session_end"}


class EventLog:
    def __init__(self, directory=None):
        directory = Path(directory or Path(__file__).resolve().parents[1] / ".local/events")
        directory.mkdir(parents=True, exist_ok=True)
        self.session = uuid.uuid4().hex
        self.path = directory / (self.session + ".jsonl")
        self.lock = threading.Lock()

    def emit(self, event, **fields):
        if event not in EVENTS:
            raise ValueError("Unknown event type")
        record = {"schema": 1, "time": datetime.now(timezone.utc).isoformat(), "session": self.session, "event": event}
        for key, value in fields.items():
            if key == "status" and value in {"arrived", "no_path", "stuck", "timeout", "other"}:
                record[key] = value
            if key in FIELDS and type(value) in (int, float, bool) and math.isfinite(value):
                record[key] = value
        with self.lock, self.path.open('a', encoding='utf-8') as output:
            output.write(json.dumps(record, separators=(',', ':'), allow_nan=False) + '\n')


_logger = None
def emit(event, **fields):
    global _logger
    try:
        if _logger is None:
            _logger = EventLog()
        _logger.emit(event, **fields)
    except OSError:
        # Audit storage failure must never bypass emergency stopping.
        return
