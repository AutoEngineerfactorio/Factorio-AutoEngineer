import asyncio
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import supervised_agent as agent
from mode_policy import ModePolicy, SEMI
from session_safety import ConsoleControl, StopRequested
from offline_loop import OfflineLoop


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=OfflineLoop)

    async def test_stop_after_approval_prevents_dispatch(self):
        control = ConsoleControl()
        async def approve():
            control.stop.set()
            return "y"
        control.approve = approve
        session = SimpleNamespace(call_tool=AsyncMock())
        async def read(*args, **kwargs):
            return {"x": 0, "y": 0}
        decision = {"action": "walk", "x": 1, "y": 0}
        with patch.object(agent, "read_tool", side_effect=read), patch.object(agent, "daemon_call", AsyncMock(return_value=decision)), redirect_stdout(io.StringIO()):
            with self.assertRaises(StopRequested):
                await agent.run_cycles(session, control, "a" * 32, policy=ModePolicy(SEMI))
        session.call_tool.assert_not_called()

    async def test_approved_dispatch_carries_session_owner(self):
        control = ConsoleControl()
        control.approve = AsyncMock(return_value="y")
        response = SimpleNamespace(is_error=False, content=[SimpleNamespace(type="text", text='{"status":"arrived"}')])
        session = SimpleNamespace(call_tool=AsyncMock(return_value=response))
        reads = [{"x": 0, "y": 0}, {}, {}, {"x": 0, "y": 0}, {"x": 1, "y": 0}]
        decision = {"action": "walk", "x": 1, "y": 0}
        with patch.object(agent, "MAX_ACTIONS", 1), patch.object(agent, "read_tool", AsyncMock(side_effect=reads)), patch.object(agent, "daemon_call", AsyncMock(return_value=decision)), redirect_stdout(io.StringIO()):
            await agent.run_cycles(session, control, "a" * 32, policy=ModePolicy(SEMI))
        self.assertEqual(session.call_tool.call_args.kwargs["arguments"]["safetyOwner"], "a" * 32)
        self.assertEqual(session.call_tool.call_args.args[0], "walk_to_position")

    async def test_rejected_approval_never_dispatches(self):
        control = ConsoleControl()
        control.approve = AsyncMock(return_value="n")
        session = SimpleNamespace(call_tool=AsyncMock())
        decision = {"action": "walk", "x": 1, "y": 0}
        with patch.object(agent, "MAX_ACTIONS", 1), patch.object(agent, "read_tool", AsyncMock(return_value={"x": 0, "y": 0})), patch.object(agent, "daemon_call", AsyncMock(return_value=decision)), redirect_stdout(io.StringIO()):
            await agent.run_cycles(session, control, "a" * 32, policy=ModePolicy(SEMI))
        session.call_tool.assert_not_called()
