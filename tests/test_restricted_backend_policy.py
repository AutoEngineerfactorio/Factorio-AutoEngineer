"""The restricted backend's tool policy must admit the read-only tools.

The helper mode denies gameplay writes and lease activation. Every **read-only**
observation tool must still be admitted there, because a helper that cannot
read the game's production data cannot do its job.

This test exists because the telemetry tool was missing from the helper-mode
allowlist: the request filter threw before the tool body ran and the MCP SDK
reported the generic "An error occurred invoking 'autoengineer_telemetry'."
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
TOOLS = ROOT / "backend-safety" / "AutoEngineerTools.cs"
BOUNDARY = ROOT / "agent" / "dispatch_boundary.py"

#: The tools the AI Helper mode may call. Every entry must be read-only.
HELPER_MODE_TOOLS = (
    "autoengineer_operation_preview",
    "autoengineer_view",
    "autoengineer_telemetry",
    "autoengineer_policy",
    "get_player_position",
    "scan_resources",
    "get_nearby_entities",
    "autoengineer_status",
    "autoengineer_stop",
)

#: The tools that write to the game. They must stay out of helper mode.
HELPER_MODE_DENIED_TOOLS = (
    "autoengineer_operation",
    "walk_to_position",
    "autoengineer_arm",
    "autoengineer_renew",
)


def helper_mode_allowlist(patch_text: str) -> set[str]:
    """Return the tool names the patched helper-mode filter admits.

    The patch stores the patched file as a diff, so the C# source lines carry
    a leading ``+``. The filter is matched on the source text, not the
    diff markers.
    """
    source = "\n".join(
        line[1:] for line in patch_text.splitlines() if line.startswith("+")
    )
    match = re.search(
        r'if \(mode != "semi" && context\.Params\.Name is not\s*\n\s*\(([^)]*)\)',
        source,
    )
    assert match, "the patched helper-mode filter was not found"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


class RestrictedBackendPolicyTests(unittest.TestCase):
    """The restricted tool policy must stay intact and complete."""

    def setUp(self):
        self.patch = PATCH.read_text(encoding="utf-8")
        self.tools = TOOLS.read_text(encoding="utf-8")

    def test_helper_mode_admits_every_read_only_tool(self):
        allowed = helper_mode_allowlist(self.patch)
        for tool in HELPER_MODE_TOOLS:
            self.assertIn(tool, allowed, f"helper mode must admit {tool}")

    def test_helper_mode_still_denies_the_gameplay_writes(self):
        allowed = helper_mode_allowlist(self.patch)
        for tool in HELPER_MODE_DENIED_TOOLS:
            self.assertNotIn(tool, allowed, f"helper mode must deny {tool}")

    def test_the_telemetry_tool_declares_no_arguments(self):
        """The telemetry tool takes no arguments, so it cannot widen a read."""
        self.assertIn('["autoengineer_telemetry"] = []', self.tools)

    def test_the_helper_mode_filter_still_denies_unknown_arguments(self):
        self.assertIn(
            "arguments.Keys.Any(k => !keys.Contains(k))", self.patch)
        self.assertIn(
            "Dispatch denied by AutoEngineer policy", self.patch)

    def test_the_thirteen_external_tools_are_unchanged(self):
        """The external tool boundary must not gain a fourteenth tool.

        R10-B added ``autoengineer_inventory``. The count is pinned so
        that a further tool cannot be added silently: every new external
        tool has to be a deliberate, reviewed change that updates this
        list, the helper-mode filter, the host dispatch boundary and the
        host mode policy together.
        """
        declared = set(re.findall(r'\[McpServerTool\(Name = "([a-z_]+)"', self.tools))
        self.assertEqual(
            declared,
            {
                "autoengineer_policy",
                "autoengineer_telemetry",
                "autoengineer_view",
                "autoengineer_inventory",
                "get_player_position",
                "scan_resources",
                "get_nearby_entities",
                "walk_to_position",
                "autoengineer_operation_preview",
                "autoengineer_operation",
            },
        )
        self.assertIn(
            ".WithTools<AutoEngineerTools>().WithTools<SafetyTools>()", self.patch)

    def test_helper_mode_admits_the_inventory_tool(self):
        """The inventory tool is a read and helper mode must admit it."""
        allowed = helper_mode_allowlist(self.patch)
        self.assertIn("autoengineer_inventory", allowed)

    def test_the_inventory_tool_is_classified_as_a_read_everywhere(self):
        """The inventory tool must be admitted in all three allowlists.

        The R10-A telemetry tool was missing from all three at once, so
        every one of them denied the call. The same trap applies to the
        R10-B inventory tool: the backend's helper-mode filter, the host
        dispatch boundary and the host mode policy each deny it
        independently, so it has to be present in all of them.
        """
        boundary = BOUNDARY.read_text(encoding="utf-8")
        self.assertIn('"autoengineer_inventory"', boundary)
        policy = (ROOT / "agent" / "mode_policy.py").read_text(encoding="utf-8")
        self.assertIn('"autoengineer_inventory"', policy)
        sys.path.insert(0, str(ROOT / "agent"))
        from mode_policy import GAME_WRITES, READ_TOOLS  # noqa: PLC0415

        self.assertIn("autoengineer_inventory", READ_TOOLS)
        self.assertNotIn("autoengineer_inventory", GAME_WRITES)

    def test_the_inventory_tool_declares_only_bounded_page_arguments(self):
        """The inventory tool may only ask for bounded pages."""
        self.assertIn(
            '["autoengineer_inventory"] = ["machinePage", "machinePageSize", '
            '"logisticsPage", "logisticsPageSize"]',
            self.tools,
        )

    def test_the_host_boundary_admits_the_telemetry_tool(self):
        """The host-side dispatch boundary must not reject the tool either."""
        boundary = BOUNDARY.read_text(encoding="utf-8")
        self.assertIn('"autoengineer_telemetry"', boundary)

    def test_the_mode_policy_classifies_the_telemetry_tool_as_a_read(self):
        """The host mode policy must classify the tool as read-only.

        The tool was missing from all three allowlists at once: the backend's
        helper-mode filter, the host dispatch boundary and the host mode
        policy. Each omission alone denies the call, so the tool has to be
        admitted in all of them.
        """
        policy = (ROOT / "agent" / "mode_policy.py").read_text(encoding="utf-8")
        self.assertIn('"autoengineer_telemetry"', policy)
        sys.path.insert(0, str(ROOT / "agent"))
        from mode_policy import GAME_WRITES, READ_TOOLS  # noqa: PLC0415

        self.assertIn("autoengineer_telemetry", READ_TOOLS)
        self.assertNotIn("autoengineer_telemetry", GAME_WRITES)


if __name__ == "__main__":
    unittest.main()
