import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from verified_operations import validate_operation, run_operation, inventory
from mode_policy import ModePolicy, SEMI
from dispatch_boundary import DispatchBoundary
from session_safety import ConsoleControl, StopRequested
from offline_loop import OfflineLoop


def result(data):return NS(is_error=False,content=[NS(type='text',text=json.dumps(data))])
def view(plate=2,gear=0,ore=0):return dict(status='ok',x=0,y=0,tick=1,surface='nauvis',inventory_available=True,truncated=False,inventory=[dict(name=name,quality='normal',count=count) for name,count in [('iron-plate',plate),('iron-gear-wheel',gear),('iron-ore',ore)]])


class BoundsTests(unittest.TestCase):
    def test_only_small_starter_operations_allowed(self):
        for kind,name,count in [('craft','uranium-rounds-magazine',1),('mine','uranium-ore',1),('mine','coal',True),('craft','iron-gear-wheel',4),('drop','coal',1)]:
            with self.assertRaises(ValueError):validate_operation(dict(kind=kind,name=name,count=count))
        with self.assertRaises(ValueError):validate_operation(dict(kind='mine',name='coal',count=1,lua='bad'))

    def test_partial_or_invalid_inventory_not_verified(self):
        with self.assertRaises(ValueError):inventory(dict(view(),truncated=True),'iron-ore')
        invalid=view();invalid['inventory'][0]['count']=True
        with self.assertRaises(ValueError):inventory(invalid,'iron-plate')


class OperationTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):self._asyncioRunner=asyncio.Runner(loop_factory=OfflineLoop)

    async def scenario(self,kind='craft',answer='y',stopped=False,changed=False,missing=False,wrong=False):
        operation=dict(kind=kind,name='iron-gear-wheel' if kind=='craft' else 'iron-ore',count=1)
        control=ConsoleControl()
        async def approve():
            if stopped:control.stop.set()
            return answer
        control.approve=approve;calls=[];previews=0;views=0
        async def call(name,arguments=None):
            nonlocal previews,views
            calls.append(name)
            if name=='autoengineer_operation_preview':
                previews+=1
                return result(dict(status='missing_materials' if missing else 'ready',x=1 if changed and previews==2 else 0,y=0,product_before=0,input_before=2,targetX=0,targetY=1))
            if name=='autoengineer_view':
                views+=1
                return result(view() if views==1 else view(plate=0 if kind=='craft' else 2,gear=0 if wrong else int(kind=='craft'),ore=int(kind=='mine')))
            return result(dict(status='verified',resource_before=10,resource_after=9))
        boundary=DispatchBoundary(NS(call_tool=call),control,ModePolicy(SEMI))
        with redirect_stdout(io.StringIO()) as output:
            await run_operation(boundary,control,'a'*32,operation)
        return calls,output.getvalue()

    async def test_craft_requires_consumption_and_product_gain(self):
        calls,output=await self.scenario();self.assertEqual(calls.count('autoengineer_operation'),1);self.assertIn('Verified operation: True',output)

    async def test_mining_requires_depletion_and_inventory_gain(self):
        _,output=await self.scenario(kind='mine');self.assertIn('Verified operation: True',output)

    async def test_reject_never_dispatches(self):
        calls,_=await self.scenario(answer='n');self.assertNotIn('autoengineer_operation',calls)

    async def test_stop_after_approval_never_dispatches(self):
        with self.assertRaises(StopRequested):await self.scenario(stopped=True)

    async def test_changed_position_cancels(self):
        calls,_=await self.scenario(changed=True);self.assertNotIn('autoengineer_operation',calls)

    async def test_missing_materials_stops_before_approval(self):
        calls,_=await self.scenario(missing=True);self.assertEqual(calls,['autoengineer_operation_preview'])

    async def test_reported_success_without_inventory_change_fails(self):
        with self.assertRaises(RuntimeError):await self.scenario(wrong=True)

    async def test_permit_is_bound_to_tool_and_single_use(self):
        raw=NS(call_tool=AsyncMock(return_value=result({})));boundary=DispatchBoundary(raw, policy=ModePolicy(SEMI))
        args=dict(kind='mine',name='coal',count=1,safetyOwner='a'*32,targetX=0,targetY=1)
        with self.assertRaises(PermissionError):await boundary.call_tool('autoengineer_operation',args)
        boundary.approve(args,'y')
        with self.assertRaises(PermissionError):await boundary.call_tool('autoengineer_operation',args)
        boundary.approve(args,'y',tool='autoengineer_operation');await boundary.call_tool('autoengineer_operation',args)
        with self.assertRaises(PermissionError):await boundary.call_tool('autoengineer_operation',args)
        self.assertEqual(raw.call_tool.await_count,1)
