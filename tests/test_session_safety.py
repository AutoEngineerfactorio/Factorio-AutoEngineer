import asyncio
import io
import sys
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from offline_loop import OfflineLoop
from session_safety import ConsoleControl, SafetySession, StopRequested, daemon_call


class FakeSession:
    def __init__(self, *, tools=True, renew="active", stop="stopped", arm="active"):
        self.tools = tools
        self.renew = renew
        self.stop_status = stop
        self.arm = arm
        self.calls = []

    async def list_tools(self):
        names = (
            ["autoengineer_arm", "autoengineer_renew", "autoengineer_stop"] if self.tools else []
        )
        return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in names])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        status = {
            "autoengineer_arm": self.arm,
            "autoengineer_renew": self.renew,
            "autoengineer_stop": self.stop_status,
        }[name]
        if status == "hang":
            await asyncio.Event().wait()
        if status == "error":
            raise ConnectionError("simulated transport loss")
        import json

        value = {"version": 1, "status": status, "walking": False}
        return SimpleNamespace(
            is_error=False, content=[SimpleNamespace(type="text", text=json.dumps(value))]
        )


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=OfflineLoop)

    async def test_unpatched_backend_cannot_start_work(self):
        session, control = FakeSession(tools=False), ConsoleControl()
        called = []

        async def work():
            called.append(True)

        with self.assertRaisesRegex(RuntimeError, "Patched backend"):
            await SafetySession(session, control).run(work)
        self.assertFalse(called)
        self.assertFalse(session.calls)

    async def test_busy_arm_cannot_start_work_or_stop_another_owner(self):
        session, control = FakeSession(arm="busy", stop="not_owner"), ConsoleControl()
        called = []

        async def work():
            called.append(True)

        with redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(RuntimeError):
                await SafetySession(session, control).run(work)
        self.assertFalse(called)
        self.assertIn("SAFETY_STOP_UNCONFIRMED", output.getvalue())

    async def test_stop_interrupts_inflight_work_and_cleans_up(self):
        session, control = FakeSession(), ConsoleControl()
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def work():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with redirect_stdout(io.StringIO()) as output:
            task = asyncio.create_task(SafetySession(session, control).run(work))
            await started.wait()
            control.feed("q\n")
            with self.assertRaises(StopRequested):
                await asyncio.wait_for(task, 1)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(session.calls[-1][0], "autoengineer_stop")
        self.assertIn("SAFETY_STOP_CONFIRMED", output.getvalue())
        self.assertEqual(len({args["owner"] for _, args in session.calls}), 1)

    async def test_heartbeat_loss_cancels_work_and_stops(self):
        session, control = FakeSession(renew="error"), ConsoleControl()
        cancelled = asyncio.Event()

        async def work():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with redirect_stdout(io.StringIO()):
            with self.assertRaises(ConnectionError):
                await SafetySession(session, control, interval=0.001).run(work)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(session.calls[-1][0], "autoengineer_stop")

    async def test_expired_lease_is_not_rearmed(self):
        session, control = FakeSession(renew="expired"), ConsoleControl()

        async def work():
            await asyncio.Event().wait()

        with redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "no longer active"):
                await SafetySession(session, control, interval=0.001).run(work)
        self.assertEqual(sum(name == "autoengineer_arm" for name, _ in session.calls), 1)

    async def test_stop_ack_timeout_is_bounded_and_not_confirmed(self):
        session, control = FakeSession(stop="hang"), ConsoleControl()

        async def work():
            return 5

        with redirect_stdout(io.StringIO()) as output:
            value = await asyncio.wait_for(
                SafetySession(session, control, call_timeout=0.02).run(work), 1
            )
        self.assertEqual(value, 5)
        self.assertIn("SAFETY_STOP_UNCONFIRMED", output.getvalue())
        self.assertNotIn("SAFETY_STOP_CONFIRMED", output.getvalue())

    async def test_normal_completion_still_stops_and_latches(self):
        session, control = FakeSession(), ConsoleControl()

        async def work():
            return "done"

        with redirect_stdout(io.StringIO()):
            self.assertEqual(await SafetySession(session, control).run(work), "done")
        self.assertTrue(control.stop.is_set())
        self.assertEqual(session.calls[-1][0], "autoengineer_stop")

    async def test_stop_rechecks_later_tick_before_confirming(self):
        session, control = FakeSession(stop="unconfirmed"), ConsoleControl()
        original = session.call_tool

        async def call(name, arguments):
            reply = await original(name, arguments)
            if name == "autoengineer_stop":
                session.stop_status = "stopped"
            return reply

        session.call_tool = call

        async def work():
            return None

        with redirect_stdout(io.StringIO()) as output:
            await SafetySession(session, control).run(work)
        self.assertEqual(sum(name == "autoengineer_stop" for name, _ in session.calls), 2)
        self.assertIn("SAFETY_STOP_CONFIRMED", output.getvalue())

    async def test_unconfirmed_state_cannot_retry_forever(self):
        session, control = FakeSession(stop="unconfirmed"), ConsoleControl()

        async def work():
            return None

        with redirect_stdout(io.StringIO()) as output:
            await asyncio.wait_for(
                SafetySession(session, control, call_timeout=0.02).run(work), 0.5
            )
        self.assertIn("SAFETY_STOP_UNCONFIRMED", output.getvalue())

    async def test_exception_still_stops(self):
        session, control = FakeSession(), ConsoleControl()

        async def work():
            raise ValueError("invalid model response")

        with redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                await SafetySession(session, control).run(work)
        self.assertEqual(session.calls[-1][0], "autoengineer_stop")

    async def test_outer_cancellation_still_stops(self):
        session, control = FakeSession(), ConsoleControl()
        started = asyncio.Event()

        async def work():
            started.set()
            await asyncio.Event().wait()

        with redirect_stdout(io.StringIO()):
            task = asyncio.create_task(SafetySession(session, control).run(work))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(session.calls[-1][0], "autoengineer_stop")

    async def test_timed_out_arm_still_attempts_stop(self):
        session, control = FakeSession(arm="hang"), ConsoleControl()

        async def work():
            self.fail("work must not run")

        with redirect_stdout(io.StringIO()):
            with self.assertRaises(TimeoutError):
                await SafetySession(session, control, call_timeout=0.01).run(work)
        self.assertEqual(session.calls[-1][0], "autoengineer_stop")

    async def test_stale_approval_and_eof_cannot_execute(self):
        control = ConsoleControl()
        control.feed("y\n")  # No prompt, so discard it.
        self.assertTrue(control.answers.empty())
        with redirect_stdout(io.StringIO()):
            waiting = asyncio.create_task(control.approve())
            await asyncio.sleep(0)
            self.assertFalse(waiting.done())
            control.feed("")
            control.feed("y\n")
            self.assertTrue(control.stop.is_set())
            self.assertTrue(control.answers.empty())
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting
            with self.assertRaises(StopRequested):
                await control.approve()

    async def test_model_wait_can_be_cancelled_without_worker_pool(self):
        started, release = threading.Event(), threading.Event()

        def model():
            started.set()
            release.wait(1)
            return "discarded"

        task = asyncio.create_task(daemon_call(model))
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        release.set()


if __name__ == "__main__":
    unittest.main()
