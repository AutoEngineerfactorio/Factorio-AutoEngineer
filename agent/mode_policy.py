"""Immutable session permissions. Full Autonomy has no executable path yet."""

import os
from dataclasses import dataclass

HELPER = "helper"
SEMI = "semi"
FULL = "full"
LABELS = {"AI Helper": HELPER, "Semi-Autonomous": SEMI, "Fully Autonomous (locked)": FULL}
READ_TOOLS = frozenset(
    {
        "autoengineer_operation_preview",
        "autoengineer_view",
        "autoengineer_telemetry",
        "autoengineer_inventory",
        "autoengineer_policy",
        "get_player_position",
        "scan_resources",
        "get_nearby_entities",
        "autoengineer_status",
    }
)
GAME_WRITES = frozenset(
    {"walk_to_position", "autoengineer_operation", "autoengineer_arm", "autoengineer_renew"}
)


@dataclass(frozen=True)
class ModePolicy:
    mode: str = HELPER

    def __post_init__(self):
        if self.mode == FULL:
            raise PermissionError("Fully Autonomous is locked pending acceptance tests")
        if self.mode not in (HELPER, SEMI):
            raise ValueError("Unknown operating mode")

    def authorize(self, tool):
        # Owner-checked emergency cleanup remains available in every mode.
        if self.mode != SEMI and tool not in READ_TOOLS | {"autoengineer_stop"}:
            raise PermissionError("AI Helper cannot execute gameplay or arm a lease")


def load_mode():
    return ModePolicy(os.environ.get("AUTOENGINEER_MODE", HELPER))
