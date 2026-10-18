import asyncio
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

AGENT = str(Path(__file__).resolve().parents[1] / "agent")
sys.path.insert(0, AGENT)
from dispatch_boundary import DispatchBoundary
from job_journal import JobJournal, RecoveryRequired
from mode_policy import ModePolicy

ARGS = dict(targetX=4, targetY=0, tolerance=0.75, timeoutSeconds=20, safetyOwner="owner")


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "jobs.sqlite3"

    def journal(self, world="world", surface="nauvis"):
        j = JobJournal(self.path, world, surface)
        self.addCleanup(j.close)
        return j

    def stopped(self, surface="nauvis"):
        return dict(
            surface=surface,
            observed_monotonic=time.monotonic(),
            control=dict(input_adapter=True, lease_active=False, walking=False),
        )

    def test_exact_approval_and_dependency_graph(self):
        j = self.journal()
        j.start({"objective": "iron"}, "model")
        a = j.propose("walk_to_position", ARGS, {"x": 0, "y": 0})
        j.approve("walk_to_position", ARGS)
        with self.assertRaises(RuntimeError):
            j.dispatch("walk_to_position", dict(ARGS, targetX=3))
        j.dispatch("walk_to_position", ARGS)
        j.observed({"received": True})
        j.checkpoint(True, {"x": 4, "y": 0})
        b = j.propose("walk_to_position", dict(ARGS, targetX=8), {"x": 4, "y": 0})
        self.assertEqual(
            j.db.execute("SELECT dependency FROM actions WHERE id=?", (b,)).fetchone()[0], a
        )
        with self.assertRaises(RuntimeError):
            j.transition(a, "executing", {})

    def test_process_crash_at_each_side_effect_boundary(self):
        for phase in ("approval_pending", "approved", "executing", "observed", "verified"):
            with self.subTest(phase=phase):
                path = Path(self.temp.name) / (phase + ".sqlite3")
                code = """import sys,os
sys.path.insert(0,sys.argv[1])
from job_journal import JobJournal
j=JobJournal(sys.argv[2],'world','nauvis');j.start({'objective':'iron'},'old-model')
args={'count':1};j.propose('autoengineer_operation',args,{});phase=sys.argv[3]
if phase!='approval_pending':j.approve('autoengineer_operation',args)
if phase in ('executing','observed','verified'):j.dispatch('autoengineer_operation',args)
if phase in ('observed','verified'):j.observed({'received':True})
if phase=='verified':j.checkpoint(True,{'gained':1})
os._exit(0)
"""
                subprocess.run(
                    [sys.executable, "-c", code, AGENT, str(path), phase], check=True, timeout=15
                )
                j = JobJournal(path, "world", "nauvis")
                try:
                    if phase in ("executing", "observed"):
                        with self.assertRaises(RecoveryRequired):
                            j.start({"objective": "new"}, "different-model-and-backend")
                        self.assertEqual(len(j.unresolved()), 1)
                        self.assertEqual(j.review(self.stopped()), 1)
                        self.assertEqual(
                            j.db.execute("SELECT state,reviewed FROM actions").fetchone(),
                            ("uncertain", 1),
                        )
                        j.start({"objective": "new"}, "different-model-and-backend")
                    else:
                        j.start({"objective": "new"}, "different-model-and-backend")
                        self.assertEqual(j.unresolved(), [])
                    self.assertEqual(j.db.execute("SELECT count(*) FROM actions").fetchone()[0], 1)
                finally:
                    j.close()

    def test_review_rejects_stale_wrong_surface_and_active_game(self):
        j = self.journal()
        j.start({}, "model")
        j.propose("walk_to_position", ARGS, {})
        j.approve("walk_to_position", ARGS)
        j.dispatch("walk_to_position", ARGS)
        j.close()
        j = self.journal()
        j.recover()
        for observation in (
            self.stopped("vulcanus"),
            dict(self.stopped(), observed_monotonic=0),
            dict(
                self.stopped(), control=dict(input_adapter=True, lease_active=True, walking=False)
            ),
        ):
            with self.assertRaises((RuntimeError, ValueError)):
                j.review(observation)
        self.assertEqual(len(j.unresolved()), 1)

    def test_scope_lock_and_surface_isolation(self):
        a = self.journal()
        a.start({}, "model")
        b = self.journal()
        with self.assertRaises(RuntimeError):
            b.start({}, "model")
        c = self.journal(surface="vulcanus")
        c.start({}, "model")
        self.assertEqual(c.unresolved(), [])

    def test_corrupt_and_future_schema_fail_closed(self):
        self.path.write_bytes(b"not sqlite")
        import sqlite3

        with self.assertRaises(sqlite3.DatabaseError):
            self.journal()
        future = self.path.with_name("future.sqlite3")
        connection = sqlite3.connect(future)
        try:
            connection.execute("PRAGMA user_version=99")
        finally:
            connection.close()
        with self.assertRaises(RuntimeError):
            JobJournal(future, "world", "nauvis")


class JournalDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_executing_is_committed_before_call_and_not_replayed(self):
        with tempfile.TemporaryDirectory() as temp:
            j = JobJournal(Path(temp) / "jobs.sqlite3", "world", "nauvis")
            j.start({}, "model")
            raw = NS(call_tool=AsyncMock())

            async def call(*args, **kwargs):
                self.assertEqual(
                    j.db.execute("SELECT state FROM actions").fetchone()[0], "executing"
                )
                raise ConnectionError("lost after possible write")

            raw.call_tool.side_effect = call
            boundary = DispatchBoundary(raw, policy=ModePolicy("semi"), journal=j)
            boundary.propose("walk_to_position", ARGS, {})
            boundary.approve(ARGS, "y")
            with self.assertRaises(ConnectionError):
                await boundary.call_tool("walk_to_position", ARGS)
            j.close()
            j = JobJournal(Path(temp) / "jobs.sqlite3", "world", "nauvis")
            try:
                with self.assertRaises(RecoveryRequired):
                    j.start({}, "changed-model")
                self.assertEqual(raw.call_tool.await_count, 1)
            finally:
                j.close()

    async def test_takeover_drops_approved_write_before_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            j = JobJournal(Path(temp) / "jobs.sqlite3", "world", "nauvis")
            j.start({}, "model")
            control = NS(stop=asyncio.Event())
            raw = NS(call_tool=AsyncMock())
            b = DispatchBoundary(raw, control, ModePolicy("semi"), j)
            b.propose("walk_to_position", ARGS, {})
            b.approve(ARGS, "y")
            control.stop.set()
            with self.assertRaises(PermissionError):
                await b.call_tool("walk_to_position", ARGS)
            raw.call_tool.assert_not_called()
            j.close()
