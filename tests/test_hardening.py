import asyncio
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'agent'))
from dispatch_boundary import DispatchBoundary, ALLOWED
from agent_events import EventLog
from movement_watchdog import monitored_walk, MovementStalled
from offline_loop import OfflineLoop
import autoengineer_config as config

def response(data):
    return NS(is_error=False, content=[NS(type='text', text=json.dumps(data))])

class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner=asyncio.Runner(loop_factory=OfflineLoop)

    async def test_unlisted_tools_and_extra_arguments_never_reach_transport(self):
        raw=NS(call_tool=AsyncMock())
        boundary=DispatchBoundary(raw)
        for name,args in [('execute_lua',{'code':'bad'}),('scan_resources',{'radius':50,'centerX':0})]:
            with self.assertRaises(PermissionError): await boundary.call_tool(name,arguments=args)
        raw.call_tool.assert_not_called()

    async def test_approval_is_single_use_and_bound_to_exact_arguments(self):
        raw=NS(call_tool=AsyncMock(return_value=response({})))
        boundary=DispatchBoundary(raw)
        args={'targetX':1,'targetY':0,'safetyOwner':'a'*32,'tolerance':.75,'timeoutSeconds':20}
        with self.assertRaises(PermissionError): await boundary.call_tool('walk_to_position',arguments=args)
        boundary.approve(args,'y')
        with self.assertRaises(PermissionError): await boundary.call_tool('walk_to_position',arguments=args|{'targetX':2})
        with self.assertRaises(PermissionError): await boundary.call_tool('walk_to_position',arguments=args)
        boundary.approve(args,'y')
        await boundary.call_tool('walk_to_position',arguments=args)
        with self.assertRaises(PermissionError): await boundary.call_tool('walk_to_position',arguments=args)
        self.assertEqual(raw.call_tool.await_count,1)

    async def test_cancel_after_approval_revokes_dispatch(self):
        stop=asyncio.Event()
        raw=NS(call_tool=AsyncMock())
        boundary=DispatchBoundary(raw,NS(stop=stop))
        args={'targetX':1,'targetY':0,'safetyOwner':'a'*32,'tolerance':.75,'timeoutSeconds':20}
        boundary.approve(args,'y');stop.set()
        with self.assertRaises(PermissionError): await boundary.call_tool('walk_to_position',arguments=args)
        raw.call_tool.assert_not_called()

    async def test_broad_backend_refused(self):
        raw=NS(list_tools=AsyncMock(return_value=NS(tools=[NS(name=k) for k in ALLOWED]+[NS(name='execute_lua')])))
        with self.assertRaises(RuntimeError): await DispatchBoundary(raw).verify()

    async def test_policy_mismatch_refused(self):
        raw=NS(list_tools=AsyncMock(return_value=NS(tools=[NS(name=k) for k in ALLOWED])),call_tool=AsyncMock(return_value=response({'version':1})))
        with self.assertRaises(RuntimeError): await DispatchBoundary(raw).verify()

    async def test_old_backend_without_route_checks_refused(self):
        raw=NS(list_tools=AsyncMock(return_value=NS(tools=[NS(name=k) for k in ALLOWED])),call_tool=AsyncMock(return_value=response({'version':2,'max_walk':5,'restricted':True})))
        with self.assertRaises(RuntimeError): await DispatchBoundary(raw).verify()

    async def test_stationary_live_call_is_cancelled_by_watchdog(self):
        cancelled=asyncio.Event()
        async def call(name,arguments):
            if name=='autoengineer_status': return response({'status':'active','x':0,'y':0})
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        with self.assertRaises(MovementStalled):
            await monitored_walk(NS(call_tool=call),{'safetyOwner':'a'*32},interval=.005,stall_seconds=.015)
        await asyncio.sleep(0)
        self.assertTrue(cancelled.is_set())

    async def test_lost_or_invalid_status_ends_walk(self):
        for data in [{'status':'inactive'},{'status':'active','x':float('nan'),'y':0}]:
            async def call(name,arguments):
                if name=='autoengineer_status': return response(data)
                await asyncio.Event().wait()
            with self.assertRaises(RuntimeError):
                await monitored_walk(NS(call_tool=call),{'safetyOwner':'a'*32},interval=.005)

    async def test_repeated_approved_destination_is_not_dispatched_twice(self):
        import supervised_agent as agent
        from session_safety import ConsoleControl
        control=ConsoleControl();control.approve=AsyncMock(return_value='y')
        raw=NS(call_tool=AsyncMock(return_value=response({'status':'no_path'})))
        decision={'action':'walk','x':4,'y':0}
        with patch.object(agent,'MAX_ACTIONS',2),patch.object(agent,'read_tool',AsyncMock(return_value={'x':0,'y':0})),patch.object(agent,'daemon_call',AsyncMock(return_value=decision)),patch.object(agent,'emit') as events:
            import io
            from contextlib import redirect_stdout
            with redirect_stdout(io.StringIO()): await agent.run_cycles(raw,control,'a'*32)
        self.assertEqual(raw.call_tool.await_count,1)
        self.assertIn('movement_repeated',[c.args[0] for c in events.call_args_list])

class IsolationTests(unittest.TestCase):
    def test_nonlocal_endpoints_rejected(self):
        for field,value in [('rcon_host','192.0.2.2'),('llm_api_url','https://example.com/v1')]:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'config.local.json').write_text(json.dumps({field:value}))
                with patch.object(config,'PROJECT_ROOT',root),patch.dict(os.environ,{},clear=True):
                    with self.assertRaises(ValueError): config.get_settings()

    def test_backend_does_not_inherit_parent_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'server.dll').write_bytes(b'')
            (root/'config.local.json').write_text('{"mcp_server_dll":"server.dll"}')
            environment={'FACTORIO_RCON_PASSWORD':'test-only','AWS_SECRET_ACCESS_KEY':'never-forward','OPENAI_API_KEY':'never-forward','AUTOENGINEER_CONFIG':'config.local.json','PATH':'test-path'}
            with patch.object(config,'PROJECT_ROOT',root),patch.dict(os.environ,environment,clear=True),patch.object(config.shutil,'which',return_value='dotnet'):
                params=config.mcp_parameters()
            self.assertNotIn('AWS_SECRET_ACCESS_KEY',params.env)
            self.assertNotIn('OPENAI_API_KEY',params.env)
            self.assertNotIn('AUTOENGINEER_CONFIG',params.env)
            self.assertEqual(Path(params.cwd),root/'.local/backend')

    def test_events_exclude_arbitrary_data_and_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            logger=EventLog(directory)
            logger.emit('approval',approved=False,password='secret',reason='private text',moved=math.nan)
            item=json.loads(logger.path.read_text())
            self.assertFalse(item['approved'])
            self.assertNotIn('secret',logger.path.read_text())
            self.assertNotIn('reason',item)
            self.assertNotIn('moved',item)

    def test_logging_storage_error_does_not_interrupt_safety(self):
        import agent_events
        with patch.object(agent_events,'_logger',NS(emit=lambda *a,**k: (_ for _ in ()).throw(OSError()))):
            agent_events.emit('stop_requested')
