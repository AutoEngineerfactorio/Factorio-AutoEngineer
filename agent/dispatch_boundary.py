"""Host-side closed dispatch table; approval is a one-use capability."""
import asyncio
import json
import math
from types import MappingProxyType

ALLOWED = {
    "autoengineer_view": set(), "autoengineer_policy": set(), "get_player_position": set(),
    "scan_resources": {"radius"}, "get_nearby_entities": {"radius"},
    "walk_to_position": {"targetX", "targetY", "safetyOwner", "tolerance", "timeoutSeconds"},
    "autoengineer_status": {"owner"},
    "autoengineer_arm": {"owner"}, "autoengineer_renew": {"owner"}, "autoengineer_stop": {"owner"},
}


class DispatchBoundary:
    def __init__(self, session, control=None):
        self.session = session
        self.control = control
        self._permit = None

    async def list_tools(self):
        return await self.session.list_tools()

    async def verify(self):
        listed = await asyncio.wait_for(self.list_tools(), 5)
        if {t.name for t in listed.tools} != set(ALLOWED):
            raise RuntimeError("Restricted backend tool set required")
        response = await asyncio.wait_for(self.call_tool('autoengineer_policy'), 5)
        data = None
        for item in response.content:
            if item.type == 'text':
                data = json.loads(item.text)
        if response.is_error or data != {"version": 4, "max_walk": 5, "restricted": True}:
            raise RuntimeError("Restricted backend policy mismatch")

    def approve(self, arguments, answer):
        if answer != 'y' or (self.control and self.control.stop.is_set()):
            raise PermissionError("Fresh human approval required")
        self._permit = MappingProxyType(dict(arguments))

    async def call_tool(self, name, arguments=None):
        args = dict(arguments or {})
        if name not in ALLOWED or set(args) - ALLOWED[name]:
            raise PermissionError("Tool or argument denied by dispatch boundary")
        if name == 'walk_to_position':
            permit, self._permit = self._permit, None
            if permit is None or dict(permit) != args or (self.control and self.control.stop.is_set()):
                raise PermissionError("Missing, stale or consumed approval")
            for key in ('targetX', 'targetY', 'tolerance', 'timeoutSeconds'):
                if type(args.get(key)) not in (float, int) or not math.isfinite(args[key]):
                    raise ValueError("Invalid movement parameter")
            if not 0 < args['tolerance'] <= .75 or not 0 < args['timeoutSeconds'] <= 20:
                raise ValueError("Movement bounds rejected")
        return await self.session.call_tool(name, arguments=args)
