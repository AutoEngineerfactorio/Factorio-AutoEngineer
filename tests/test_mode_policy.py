import asyncio
from dataclasses import FrozenInstanceError
import io
import json
import os
from pathlib import Path
import queue
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from mode_policy import ModePolicy, load_mode, HELPER, SEMI, FULL, GAME_WRITES, READ_TOOLS
from dispatch_boundary import DispatchBoundary, ALLOWED
from autoengineer_dashboard import Dashboard
from session_safety import ConsoleControl
from offline_loop import OfflineLoop


class PolicyTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner=asyncio.Runner(loop_factory=OfflineLoop)

    async def test_every_exposed_tool_requires_explicit_classification(self):
        self.assertEqual(set(ALLOWED),set(READ_TOOLS)|set(GAME_WRITES)|{'autoengineer_stop'})
        with self.assertRaises(PermissionError):ModePolicy().authorize('future_unclassified_tool')

    async def test_helper_blocks_all_writes_before_transport_and_approval(self):
        raw=NS(call_tool=AsyncMock());b=DispatchBoundary(raw)
        for tool in GAME_WRITES:
            with self.assertRaises(PermissionError):await b.call_tool(tool,{})
        with self.assertRaises(PermissionError):b.approve({},'y')
        raw.call_tool.assert_not_called()

    async def test_helper_keeps_reads_and_owner_checked_stop(self):
        raw=NS(call_tool=AsyncMock());b=DispatchBoundary(raw)
        for tool,args in [('autoengineer_view',{}),('autoengineer_stop',{'owner':'a'*32})]:
            await b.call_tool(tool,args)
        self.assertEqual(raw.call_tool.await_count,2)

    async def test_semi_still_requires_approval_and_stop_revokes_it(self):
        c=ConsoleControl();raw=NS(call_tool=AsyncMock());b=DispatchBoundary(raw,c,ModePolicy(SEMI))
        args=dict(targetX=1,targetY=0,tolerance=.75,timeoutSeconds=20,safetyOwner='a'*32)
        with self.assertRaises(PermissionError):await b.call_tool('walk_to_position',args)
        b.approve(args,'y');c.stop.set()
        with self.assertRaises(PermissionError):await b.call_tool('walk_to_position',args)
        raw.call_tool.assert_not_called()

    async def test_full_unknown_and_mutation_fail_closed(self):
        with self.assertRaises(PermissionError):ModePolicy(FULL)
        with self.assertRaises(ValueError):ModePolicy('future-mode')
        policy=ModePolicy()
        with self.assertRaises(FrozenInstanceError):policy.mode=SEMI
        with patch.dict(os.environ,{},clear=True):self.assertEqual(load_mode().mode,HELPER)

    async def test_helper_and_full_entrypoints_never_launch_gameplay(self):
        import supervised_agent as agent
        with patch.dict(os.environ,{'AUTOENGINEER_MODE':'helper'}),patch.object(agent,'mcp_parameters') as launch,patch('builtins.print'):
            await agent.main()
            launch.assert_not_called()
        with patch.dict(os.environ,{'AUTOENGINEER_MODE':'full'}),patch.object(agent,'mcp_parameters') as launch:
            with self.assertRaises(PermissionError):await agent.main()
            launch.assert_not_called()

    async def test_backend_policy_must_match_session_mode(self):
        raw=NS(list_tools=AsyncMock(return_value=NS(tools=[NS(name=k) for k in ALLOWED])),
            call_tool=AsyncMock(return_value=NS(is_error=False,content=[NS(type='text',text=json.dumps(dict(version=7,max_walk=5,restricted=True,mode='helper')))])))
        await DispatchBoundary(raw).verify()
        with self.assertRaises(RuntimeError):await DispatchBoundary(raw,policy=ModePolicy(SEMI)).verify()


    async def test_old_backend_is_rejected(self):
        raw=NS(list_tools=AsyncMock(return_value=NS(tools=[NS(name=k) for k in ALLOWED])),
            call_tool=AsyncMock(return_value=NS(is_error=False,content=[NS(type='text',text=json.dumps(dict(version=6,max_walk=5,restricted=True,mode='helper')))])))
        with self.assertRaises(RuntimeError):await DispatchBoundary(raw).verify()


class DashboardModeTests(unittest.TestCase):
    def view(self):
        v=Dashboard.__new__(Dashboard);v.current_mode=SEMI;v.mode=Mock();v.mode.get.return_value='AI Helper'
        v.mode_note=Mock();v.proc=NS(poll=lambda:None,stdin=io.StringIO());v.observer=object()
        v.stop_requested=False;v.stop_confirmed=False;v.waiting_for_approval=True;v.closing=False
        v.status=Mock();v.approve_button=Mock();v.reject_button=Mock();v.sync_mode_controls=Mock()
        return v

    def test_switch_to_helper_stops_child_and_drops_late_approval(self):
        v=self.view();observer=v.observer
        with patch('autoengineer_dashboard.threading.Thread'):v.change_mode()
        self.assertEqual(v.current_mode,HELPER);self.assertEqual(v.proc.stdin.getvalue(),'q\n')
        v.answer('y');self.assertEqual(v.proc.stdin.getvalue(),'q\n');self.assertIs(v.observer,observer)

    def test_full_choice_is_locked_and_does_not_switch(self):
        v=self.view();v.mode.get.return_value='Fully Autonomous (locked)'
        with patch('autoengineer_dashboard.messagebox.showinfo'):v.change_mode()
        self.assertEqual(v.current_mode,SEMI);self.assertEqual(v.proc.stdin.getvalue(),'')

    def test_helper_cannot_start_child_even_when_called_directly(self):
        v=self.view();v.current_mode=HELPER;v.proc=None
        with patch('autoengineer_dashboard.subprocess.Popen') as launch:v.start()
        launch.assert_not_called()

    def test_cannot_reenable_semi_until_old_child_stops(self):
        v=self.view();v.current_mode=HELPER;v.mode.get.return_value='Semi-Autonomous'
        with patch('autoengineer_dashboard.messagebox.showinfo'):v.change_mode()
        self.assertEqual(v.current_mode,HELPER)

    def test_more_permissive_switch_requires_confirmation(self):
        v=self.view();v.current_mode=HELPER;v.proc=None;v.mode.get.return_value='Semi-Autonomous'
        with patch('autoengineer_dashboard.messagebox.askyesno',return_value=False):v.change_mode()
        self.assertEqual(v.current_mode,HELPER)
