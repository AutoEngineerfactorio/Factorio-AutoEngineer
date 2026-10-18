import asyncio
from contextlib import redirect_stdout
import io
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from navigation_objective import Objective
from movement_proposals import movement_choices, resolve_choice
from session_safety import ConsoleControl
from offline_loop import OfflineLoop
import supervised_agent as agent


class ObjectiveTests(unittest.TestCase):
    def test_distant_objective_generates_only_short_offers(self):
        state = {'position': {'x': 0, 'y': 0}, 'objective': {'x': 100, 'y': 100}}
        choices = movement_choices(state)
        self.assertLess(choices[0]['objective_remaining'], math.hypot(100, 100))
        for choice in choices:
            decision = resolve_choice({'choice': choice['choice']}, choices)
            self.assertIsNotNone(agent.validate(decision, state['position']))
        with self.assertRaises(PermissionError):
            agent.validate({'action': 'walk', 'x': 100, 'y': 100}, state['position'])

    def test_resource_target_is_observed_nearest_and_does_not_switch(self):
        objective = Objective('iron-ore')
        state = {'position': {'x': 0, 'y': 0}, 'resources': {'resources': [
            {'name': 'iron-ore', 'center_x': 10, 'center_y': 0},
            {'name': 'iron-ore', 'center_x': 20, 'center_y': 0}]}}
        self.assertEqual(objective.observe(state), {'x': 10, 'y': 0})
        state['resources'] = {}
        self.assertEqual(objective.observe(state), {'x': 10, 'y': 0})

    def test_invalid_or_unobserved_objectives(self):
        for value in ['', 'nan,0', 'inf,0', '0,0,0', '1000001,0', 'ore;execute', '[]']:
            with self.assertRaises(ValueError): Objective(value)
        self.assertIsNone(Objective('iron-ore').observe({'position': {'x': 0, 'y': 0}}))

    def test_failed_target_still_excluded_for_objective(self):
        state = {'position': {'x': 0, 'y': 0}, 'objective': {'x': 100, 'y': 0}}
        choices = movement_choices(state, [{'decision': {'x': 4, 'y': 0}, 'outcome': 'no_path'}])
        self.assertFalse(any(c['x'] == 4 and c['y'] == 0 for c in choices))


class ObjectiveSessionTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=OfflineLoop)

    async def test_reached_and_unobserved_stop_before_model_or_approval(self):
        for objective in [Objective('0,0'), Objective('iron-ore')]:
            control = ConsoleControl(); control.approve = AsyncMock()
            session = SimpleNamespace(call_tool=AsyncMock())
            with patch.object(agent, 'load_objective', return_value=objective), patch.object(agent, 'load_memory', return_value=None), patch.object(agent, 'read_tool', AsyncMock(return_value={'x': 0, 'y': 0})), patch.object(agent, 'daemon_call', AsyncMock()) as planner, redirect_stdout(io.StringIO()):
                await agent.run_cycles(session, control, 'a'*32)
            planner.assert_not_called(); control.approve.assert_not_called(); session.call_tool.assert_not_called()

    async def test_objective_arrival_ends_session_after_one_approved_step(self):
        control = ConsoleControl(); control.approve = AsyncMock(return_value='y')
        response = SimpleNamespace(is_error=False, content=[SimpleNamespace(type='text', text='{"status":"arrived"}')])
        session = SimpleNamespace(call_tool=AsyncMock(return_value=response))
        reads = [{'x': 0, 'y': 0}, {}, {}, {'x': 0, 'y': 0}, {'x': 4, 'y': 0}]
        with patch.object(agent, 'load_objective', return_value=Objective('4,0')), patch.object(agent, 'load_memory', return_value=None), patch.object(agent, 'read_tool', AsyncMock(side_effect=reads)), patch.object(agent, 'daemon_call', AsyncMock(return_value={'action': 'walk', 'x': 4, 'y': 0})), redirect_stdout(io.StringIO()) as output:
            await agent.run_cycles(session, control, 'a'*32)
        self.assertEqual(control.approve.await_count, 1)
        self.assertEqual(session.call_tool.await_count, 1)
        self.assertIn('Objective reached', output.getvalue())


class DashboardObjectiveTests(unittest.TestCase):
    def test_invalid_goal_does_not_start_child(self):
        from autoengineer_dashboard import Dashboard
        view = Dashboard.__new__(Dashboard)
        view.closing = False
        view.proc = None
        view.objective = Mock()
        view.objective.get.return_value = 'nan,0'
        with patch('autoengineer_dashboard.subprocess.Popen') as launch, patch('autoengineer_dashboard.messagebox.showerror') as error:
            view.start()
        launch.assert_not_called()
        error.assert_called_once()
