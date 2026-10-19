"""Host-side closed dispatch table; approval is a one-use capability."""

import asyncio
import json
import math
from types import MappingProxyType

from mode_policy import ModePolicy
from verified_operations import validate_operation

ALLOWED = {
    "autoengineer_operation_preview": {"kind", "name", "count"},
    "autoengineer_operation": {"kind", "name", "count", "safetyOwner", "targetX", "targetY"},
    "autoengineer_view": {"catalogPage", "catalogPageSize"},
    "autoengineer_policy": set(),
    "get_player_position": set(),
    "scan_resources": {"radius"},
    "get_nearby_entities": {"radius"},
    "walk_to_position": {"targetX", "targetY", "safetyOwner", "tolerance", "timeoutSeconds"},
    "autoengineer_status": {"owner"},
    "autoengineer_arm": {"owner"},
    "autoengineer_renew": {"owner"},
    "autoengineer_stop": {"owner"},
}


class DispatchBoundary:
    def __init__(self, session, control=None, policy=None, journal=None):
        self.policy = policy if policy is not None else ModePolicy()
        self.session = session
        self.control = control
        self._permit = None
        self._permit_tool = None
        self.journal = journal

    def propose(self, tool, arguments, observation):
        if self.journal:
            return self.journal.propose(tool, arguments, observation)

    def checkpoint(self, verified, observation):
        if self.journal:
            self.journal.checkpoint(verified, observation)

    def cancel_proposal(self):
        self._permit = None
        self._permit_tool = None
        if self.journal:
            self.journal.cancel_proposal()

    async def list_tools(self):
        return await self.session.list_tools()

    async def verify(self):
        listed = await asyncio.wait_for(self.list_tools(), 5)
        if {t.name for t in listed.tools} != set(ALLOWED):
            raise RuntimeError("Restricted backend tool set required")
        response = await asyncio.wait_for(self.call_tool("autoengineer_policy"), 5)
        data = None
        for item in response.content:
            if item.type == "text":
                data = json.loads(item.text)
        if response.is_error or data != {
            "version": 8,
            "max_walk": 5,
            "restricted": True,
            "mode": self.policy.mode,
        }:
            raise RuntimeError("Restricted backend policy mismatch")

    def approve(self, arguments, answer, tool="walk_to_position"):
        self.policy.authorize(tool)
        if answer != "y" or (self.control and self.control.stop.is_set()):
            raise PermissionError("Fresh human approval required")
        if self.journal:
            self.journal.approve(tool, arguments)
        self._permit = MappingProxyType(dict(arguments))
        self._permit_tool = tool

    async def call_tool(self, name, arguments=None):
        args = dict(arguments or {})
        if name not in ALLOWED or set(args) - ALLOWED[name]:
            raise PermissionError("Tool or argument denied by dispatch boundary")
        if name == "autoengineer_view":
            page = args.get("catalogPage", 1)
            page_size = args.get("catalogPageSize", 16)
            if type(page) is not int or not 1 <= page <= 10000:
                raise ValueError("Invalid catalog page")
            if type(page_size) is not int or not 1 <= page_size <= 32:
                raise ValueError("Invalid catalog page size")
        self.policy.authorize(name)
        if name in {"walk_to_position", "autoengineer_operation"}:
            permit, self._permit = self._permit, None
            permit_tool, self._permit_tool = self._permit_tool, None
            if (
                permit_tool != name
                or permit is None
                or dict(permit) != args
                or (self.control and self.control.stop.is_set())
            ):
                raise PermissionError("Missing, stale or consumed approval")
        if name in {"autoengineer_operation_preview", "autoengineer_operation"}:
            validate_operation({k: args.get(k) for k in ("kind", "name", "count")})
            if name == "autoengineer_operation" and any(
                type(args.get(k)) not in (int, float) or not math.isfinite(args[k])
                for k in ("targetX", "targetY")
            ):
                raise ValueError("Invalid operation target")
        if name == "walk_to_position":
            for key in ("targetX", "targetY", "tolerance", "timeoutSeconds"):
                if type(args.get(key)) not in (float, int) or not math.isfinite(args[key]):
                    raise ValueError("Invalid movement parameter")
            if not 0 < args["tolerance"] <= 0.75 or not 0 < args["timeoutSeconds"] <= 20:
                raise ValueError("Movement bounds rejected")
        writes = name in {"walk_to_position", "autoengineer_operation"}
        if writes and self.journal:
            self.journal.dispatch(name, args)
        result = await self.session.call_tool(name, arguments=args)
        if writes and self.journal:
            if result.is_error:
                raise RuntimeError("Gameplay response failed; action outcome is uncertain")
            self.journal.observed({"response_received": True})
        return result
