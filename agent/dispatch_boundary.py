"""Host-side closed dispatch table; approval is a one-use capability."""

import asyncio
import json
import math
from types import MappingProxyType

from dashboard_chunk_grid import validate_chunk_request
from mode_policy import ModePolicy
from verified_operations import validate_operation

ALLOWED = {
    "autoengineer_operation_preview": {"kind", "name", "count"},
    "autoengineer_operation": {"kind", "name", "count", "safetyOwner", "targetX", "targetY"},
    "autoengineer_view": {"catalogPage", "catalogPageSize", "mapChunkX", "mapChunkY",
                           "catalogOnly", "noCatalog"},
    "autoengineer_telemetry": set(),
    "autoengineer_inventory": {"machinePage", "machinePageSize",
                               "logisticsPage", "logisticsPageSize"},
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
            # Optional read-only map chunk selection. Both coordinates must be
            # given together and each must be a bounded integer chunk index.
            # The backend only ever reads the world; it never charts, generates
            # or selects anything.
            chunk_x = args.get("mapChunkX")
            chunk_y = args.get("mapChunkY")
            if (chunk_x is None) != (chunk_y is None):
                raise ValueError("Map chunk coordinates must be given together")
            if chunk_x is not None:
                validate_chunk_request((chunk_x, chunk_y))
            catalog_only = args.get("catalogOnly", False)
            if type(catalog_only) is not bool:
                raise ValueError("Invalid catalog-only flag")
            no_catalog = args.get("noCatalog", False)
            if type(no_catalog) is not bool:
                raise ValueError("Invalid no-catalog flag")
            if catalog_only and no_catalog:
                # A catalog read that also suppressed the catalog would
                # report an empty catalog, which is indistinguishable from
                # a catalog that genuinely has no recipes.
                raise ValueError("A catalog read cannot also suppress the catalog")
            if not catalog_only and not no_catalog:
                # The frequent view read does not need the recipe catalog.
                # The catalog adapter enumerates every recipe, recomputes
                # the technology fingerprint and enumerates every machine
                # prototype; at the observed live Pyanodons scale that is
                # 10,146 recipes to emit one page of 32, measured offline
                # at 165.5 ms of Lua per call, against 19.2 ms for the fast
                # path.
                #
                # A request that names a catalog page wants the catalog, so
                # only a request that names **no** catalog argument at all
                # is switched to the fast path.
                if not ({"catalogPage", "catalogPageSize"} & set(args)):
                    args["noCatalog"] = True
        if name == "autoengineer_inventory":
            # The inventory and logistics pages are bounded on both sides.
            # A page outside the range is refused here, before the request
            # ever reaches the game, so a bad page can never turn into an
            # unbounded scan.
            for key, maximum in (("machinePage", 10000),
                                 ("logisticsPage", 10000)):
                page = args.get(key, 1)
                if type(page) is not int or not 1 <= page <= maximum:
                    raise ValueError(f"Invalid {key}")
            for key, maximum in (("machinePageSize", 64),
                                 ("logisticsPageSize", 64)):
                size = args.get(key, 16)
                if type(size) is not int or not 1 <= size <= maximum:
                    raise ValueError(f"Invalid {key}")
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
