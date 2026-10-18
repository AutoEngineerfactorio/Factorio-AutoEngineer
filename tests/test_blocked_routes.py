import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import supervised_agent as agent
from mode_policy import ModePolicy, SEMI
from movement_proposals import movement_choices
from session_safety import ConsoleControl, StopRequested
from offline_loop import OfflineLoop


class ChoiceRecoveryTests(unittest.TestCase):
    def test_failed_and_near_duplicate_targets_are_not_offered_again(self):
        state = {"position": {"x": 0, "y": 0}, "resources": {"resources": [
            {"name": "coal", "center_x": 1, "center_y": -45}]}}
        failed = {"action": "walk", "x": .0889, "y": -3.999}
        for outcome in ['no_path', 'stuck', 'timeout', 'path_rejected']:
            choices = movement_choices(state, [{"decision": failed, "outcome": outcome}])
            self.assertTrue(choices)
            self.assertTrue(all(c['y'] >= 0 for c in choices))

    def test_no_choices_stops_without_calling_model(self):
        state = {"position": {"x": 0, "y": 0}}
        history = [{"decision": c, "outcome": "no_path"} for c in movement_choices(state)]
        with patch.object(agent.urllib.request, 'urlopen') as request:
            self.assertEqual(agent.ask_ai(state, history)['action'], 'stop')
        request.assert_not_called()


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=OfflineLoop)

    async def run_scenario(self, status='no_path', moving=False, stop=False, second_approval='n'):
        control = ConsoleControl()
        control.approve = AsyncMock(side_effect=['y', second_approval])
        session = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
            is_error=False, content=[SimpleNamespace(type='text', text=json.dumps({'status': status}))])))
        calls = 0
        async def read(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 6:
                if stop: control.stop.set()
                return {'x': 1 if moving else 0, 'y': 0}
            return {'x': 0, 'y': 0}
        planner = AsyncMock(return_value={'action': 'walk', 'x': 4, 'y': 0})
        with patch.object(agent, 'MAX_ACTIONS', 2), patch.object(agent, 'read_tool', side_effect=read), patch.object(agent, 'daemon_call', planner), redirect_stdout(io.StringIO()):
            if stop:
                with self.assertRaises(StopRequested): await agent.run_cycles(session, control, 'a'*32, policy=ModePolicy(SEMI))
            else:
                await agent.run_cycles(session, control, 'a'*32, policy=ModePolicy(SEMI))
        return session, control, planner

    async def test_known_route_failures_offer_fresh_approval_without_auto_dispatch(self):
        for status in ['no_path', 'stuck', 'timeout', 'path_rejected']:
            session, control, planner = await self.run_scenario(status)
            self.assertEqual(control.approve.await_count, 2)
            self.assertEqual(session.call_tool.await_count, 1)
            self.assertEqual(planner.await_count, 2)

    async def test_continued_motion_prevents_retry(self):
        session, control, planner = await self.run_scenario(moving=True)
        self.assertEqual(planner.await_count, 1)

    async def test_unknown_result_prevents_retry(self):
        session, control, planner = await self.run_scenario(status='unexpected')
        self.assertEqual(planner.await_count, 1)

    async def test_stop_during_recovery_prevents_next_proposal(self):
        session, control, planner = await self.run_scenario(stop=True)
        self.assertEqual(planner.await_count, 1)
        self.assertEqual(session.call_tool.await_count, 1)
