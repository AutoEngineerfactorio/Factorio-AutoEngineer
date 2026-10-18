"""Private durable action checkpoints. Interrupted writes are never auto-replayed."""

import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

from app_runtime import data_root


class RecoveryRequired(RuntimeError):
    pass


def compact(value):
    text = json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)
    if len(text) > 65536:
        raise ValueError("Job evidence exceeds bound")
    return text


def configuration_identity(settings):
    """Identify model endpoint and exact backend without retaining credentials."""
    identity = {key: settings[key] for key in ("llm_model", "llm_api_url")}
    identity["backend_sha256"] = hashlib.sha256(
        Path(settings["mcp_server_dll"]).read_bytes()
    ).hexdigest()
    identity["launcher_runtime"] = os.environ.get("AUTOENGINEER_RUNTIME_FINGERPRINT")
    return hashlib.sha256(compact(identity).encode()).hexdigest()


def journal_path():
    return data_root() / ".local" / "jobs.sqlite3"


class JobJournal:
    def __init__(self, path, world, surface):
        if any(not isinstance(v, str) or not 1 <= len(v) <= 512 for v in (world, surface)):
            raise ValueError("A world and surface are required for durable gameplay jobs")
        self.surface = surface
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.scope = hashlib.sha256(compact([world, surface]).encode()).hexdigest()
        self.lock = None
        self.closed = False
        self.job = None
        self.action = None
        self.db = sqlite3.connect(self.path, timeout=2)
        try:
            self._initialize_schema()
        except (sqlite3.Error, RuntimeError):
            self.db.close()
            raise

    def _initialize_schema(self):
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise RuntimeError("Unsupported job journal schema")
        self.db.execute("PRAGMA user_version=1")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,scope TEXT NOT NULL,goal TEXT NOT NULL,identity TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,job TEXT NOT NULL REFERENCES jobs(id),dependency TEXT REFERENCES actions(id),tool TEXT NOT NULL,arguments TEXT NOT NULL,state TEXT NOT NULL,evidence TEXT NOT NULL,reviewed INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS transitions(seq INTEGER PRIMARY KEY,action TEXT NOT NULL REFERENCES actions(id),state TEXT NOT NULL,at REAL NOT NULL,evidence TEXT NOT NULL);
        """)

    def hold(self):
        """Acquire a nonblocking process lock without reading a locked byte."""
        if self.lock:
            return
        handle = None
        try:
            handle = self.path.with_name("job-" + self.scope + ".lock").open("a+b")
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if handle:
                handle.close()
            raise RuntimeError("Another gameplay job owns this world and surface") from None
        self.lock = handle

    def recover(self):
        """Reclassify interrupted work only after taking exclusive scope ownership."""
        if self.job is not None:
            raise RuntimeError("Cannot recover while this job is active")
        self.hold()
        rows = self.db.execute(
            "SELECT a.id,a.state FROM actions a JOIN jobs j ON a.job=j.id WHERE j.scope=? AND a.state IN ('proposed','validated','approval_pending','approved','executing','observed')",
            (self.scope,),
        ).fetchall()
        for action, state in rows:
            self.transition(
                action,
                "uncertain" if state in ("executing", "observed") else "cancelled",
                {"reason": "interrupted_process"},
            )
        self.db.execute(
            "UPDATE jobs SET state='interrupted' WHERE scope=? AND state='active'", (self.scope,)
        )
        self.db.commit()

    def unresolved(self):
        return [
            dict(id=a, tool=t, arguments=json.loads(args), job=j)
            for a, t, args, j in self.db.execute(
                "SELECT a.id,a.tool,a.arguments,a.job FROM actions a JOIN jobs j ON a.job=j.id WHERE j.scope=? AND a.state='uncertain' AND a.reviewed=0 ORDER BY j.created LIMIT 32",
                (self.scope,),
            )
        ]

    def start(self, goal: dict, identity: str) -> str:
        """Start a new job; require human review of any uncertain prior side effect."""
        self.recover()
        if self.unresolved():
            raise RecoveryRequired(
                "Interrupted action outcome requires fresh observation and human review; nothing was retried"
            )
        self.job = uuid.uuid4().hex
        self.db.execute(
            "INSERT INTO jobs VALUES(?,?,?,?,?,?)",
            (self.job, self.scope, compact(goal), compact(identity), "active", time.time()),
        )
        self.db.commit()
        return self.job

    def transition(self, action, state, evidence):
        allowed = {
            "proposed": {"proposed", "validated", "cancelled"},
            "validated": {"approval_pending", "cancelled"},
            "approval_pending": {"approved", "cancelled"},
            "approved": {"executing", "cancelled"},
            "executing": {"observed", "uncertain"},
            "observed": {"verified", "failed", "uncertain"},
        }
        row = self.db.execute("SELECT state FROM actions WHERE id=?", (action,)).fetchone()
        if row is None or state not in allowed.get(row[0], set()):
            raise RuntimeError("Invalid durable action transition")
        text = compact(evidence)
        with self.db:
            self.db.execute(
                "UPDATE actions SET state=?,evidence=? WHERE id=?", (state, text, action)
            )
            self.db.execute(
                "INSERT INTO transitions(action,state,at,evidence) VALUES(?,?,?,?)",
                (action, state, time.time(), text),
            )

    def propose(self, tool, args, observation):
        if self.job is None:
            raise RuntimeError("No active durable job")
        if self.action:
            previous = self.db.execute(
                "SELECT state FROM actions WHERE id=?", (self.action,)
            ).fetchone()[0]
            if previous in ("proposed", "validated", "approval_pending", "approved"):
                self.cancel_proposal()
            elif previous not in ("verified", "failed", "cancelled"):
                raise RecoveryRequired("Prior action must be resolved before proposing another")
        action = uuid.uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO actions VALUES(?,?,?,?,?,?,?,0)",
                (
                    action,
                    self.job,
                    self.action,
                    tool,
                    compact(args),
                    "proposed",
                    compact(observation),
                ),
            )
        self.action = action
        for state in ("proposed", "validated", "approval_pending"):
            self.transition(action, state, observation)
        return action

    def approve(self, tool, args):
        if self.action is None:
            raise RuntimeError("No durable proposal for this approval")
        row = self.db.execute(
            "SELECT tool,state FROM actions WHERE id=?", (self.action,)
        ).fetchone()
        if row != (tool, "approval_pending"):
            raise RuntimeError("Stale durable approval")
        with self.db:
            self.db.execute(
                "UPDATE actions SET arguments=? WHERE id=?", (compact(args), self.action)
            )
        self.transition(self.action, "approved", {})

    def dispatch(self, tool: str, args: dict) -> None:
        """Commit executing before the caller is permitted to send the write."""
        if self.action is None:
            raise RuntimeError("No durable approval")
        row = self.db.execute(
            "SELECT tool,arguments,state FROM actions WHERE id=?", (self.action,)
        ).fetchone()
        if row != (tool, compact(args), "approved"):
            raise RuntimeError("Durable action does not match approval")
        self.transition(self.action, "executing", {})  # FULL commit before side effect.

    def observed(self, evidence):
        self.transition(self.action, "observed", evidence)

    def checkpoint(self, verified: bool, evidence: dict) -> None:
        """Record independent outcome verification, separately from MCP receipt."""
        if type(verified) is not bool:
            raise ValueError("Verification must be a boolean")
        if self.action:
            self.transition(self.action, "verified" if verified else "failed", evidence)

    def cancel_proposal(self):
        if self.action:
            state = self.db.execute(
                "SELECT state FROM actions WHERE id=?", (self.action,)
            ).fetchone()[0]
            if state in ("proposed", "validated", "approval_pending", "approved"):
                self.transition(self.action, "cancelled", {})

    def review(self, observation: dict) -> int:
        """Acknowledge uncertainty without verifying or replaying the old action."""
        self.recover()
        control = observation.get("control", {})
        if not isinstance(control, dict) or any(
            type(control.get(key)) is not bool
            for key in ("input_adapter", "lease_active", "walking")
        ):
            raise ValueError("Invalid recovery control observation")
        stamp = observation.get("observed_monotonic")
        if (
            observation.get("surface") != self.surface
            or type(stamp) not in (int, float)
            or not 0 <= time.monotonic() - stamp <= 3
            or not control.get("input_adapter")
        ):
            raise RuntimeError("Fresh observation on the same surface is required")
        if control.get("lease_active", True) or control.get("walking", True):
            raise RuntimeError("Game must be freshly observed stopped before review")
        pending = self.unresolved()
        with self.db:
            for row in pending:
                self.db.execute("UPDATE actions SET reviewed=1 WHERE id=?", (row["id"],))
                self.db.execute(
                    "INSERT INTO transitions(action,state,at,evidence) VALUES(?,?,?,?)",
                    (row["id"], "reviewed_uncertain", time.time(), compact(observation)),
                )
        return len(pending)  # Preserve uncertainty; review is not outcome verification.

    def close(self):
        """Leave unfinished writes uncertain, then release the process lock."""
        if self.closed:
            return
        try:
            if self.job:
                rows = self.db.execute(
                    "SELECT id,state FROM actions WHERE job=?", (self.job,)
                ).fetchall()
                for action, state in rows:
                    if state in ("executing", "observed"):
                        self.transition(
                            action, "uncertain", {"reason": "session_ended_before_checkpoint"}
                        )
                    elif state in ("proposed", "validated", "approval_pending", "approved"):
                        self.transition(action, "cancelled", {})
                uncertain = self.db.execute(
                    "SELECT 1 FROM actions WHERE job=? AND state='uncertain' AND reviewed=0",
                    (self.job,),
                ).fetchone()
                with self.db:
                    self.db.execute(
                        "UPDATE jobs SET state=? WHERE id=?",
                        ("interrupted" if uncertain else "checkpointed", self.job),
                    )
        finally:
            self.db.close()
            self.closed = True
            if self.lock:
                self.lock.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
                self.lock.close()
                self.lock = None
