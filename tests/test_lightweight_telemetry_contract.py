"""The telemetry tool must stay read-only, map-free, recipe-free and Lua-free.

The backend no longer embeds the telemetry Lua. The observation runs inside
the ``autoengineer-input`` mod and is reached over the registered
``autoengineer-observe`` mod command, so the backend must not send a Lua
console command on this path at all.

These assertions describe the **new** contract and are deliberately stricter
than the previous one: they additionally require that the backend emits no
``/c``, ``/sc`` or ``/silent-command`` string for the telemetry tool.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend-safety" / "AutoEngineerTools.cs"
MOD_OBSERVATION = ROOT / "backend-safety" / "Tools" / "ModObservation.cs"

# Console prefixes that would make an observation achievement-affecting.
LUA_CONSOLE_PREFIXES = ("/c ", "/sc ", "/silent-command", "rcon.print(")


def telemetry_block(source: str) -> str:
    """Return the source of the ``autoengineer_telemetry`` tool."""
    start = source.index('[McpServerTool(Name = "autoengineer_telemetry")')
    end = source.index('[McpServerTool(Name = "autoengineer_view")', start)
    return source[start:end]


class LightweightTelemetryContractTests(unittest.TestCase):
    def test_backend_has_separate_read_only_tool(self):
        source = SOURCE.read_text(encoding="utf-8")
        block = telemetry_block(source)
        # The backend routes the request over the mod command.
        self.assertIn('ModObservation.BuildCommand("telemetry")', block)
        self.assertIn("rcon.ExecuteAsync(command", block)
        self.assertIn('["autoengineer_telemetry"] = []', source)

    def test_backend_telemetry_sends_no_lua_console_command(self):
        """The backend must not emit any achievement-affecting console string."""
        source = SOURCE.read_text(encoding="utf-8")
        block = telemetry_block(source)
        for prefix in LUA_CONSOLE_PREFIXES:
            self.assertNotIn(prefix, block)
        self.assertNotIn("ExecuteLuaAsync", block)

    def test_transport_uses_a_fixed_allowlisted_mod_command(self):
        transport = MOD_OBSERVATION.read_text(encoding="utf-8")
        self.assertIn('internal const string Command = "/autoengineer-observe"', transport)
        self.assertIn("AllowedOperations", transport)
        for operation in ("status", "telemetry", "map", "recipes", "research", "machines"):
            self.assertIn(f'"{operation}"', transport)
        # An unknown operation is rejected before any command is built.
        self.assertIn("Unknown observation operation", transport)

    def test_transport_rejects_a_response_without_the_protocol_version(self):
        transport = MOD_OBSERVATION.read_text(encoding="utf-8")
        self.assertIn('TryGetProperty("protocol"', transport)
        self.assertIn("ProtocolVersion", transport)
        self.assertIn("returned no response", transport)

    def test_catalog_only_branch_does_not_request_terrain_or_entities(self):
        """The catalog read must not read terrain or entities.

        The catalog page is composed by the backend from the mod's
        ``recipes`` and ``research`` observations. It never asks for the
        terrain raster, the entities or the overlays.
        """
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index('private Task<string> CatalogOnly(')
        end = source.index('private Task<string> ViewCore(', start)
        block = source[start:end]
        self.assertIn('ComposeCatalog(', block)
        for observation in ('"terrain"', '"map"', '"overlay"'):
            self.assertNotIn(observation, block)
        self.assertNotIn('ExecuteLuaAsync', block)
        self.assertIn('"catalogOnly"', source)

    def test_the_view_tool_sends_no_lua_console_command(self):
        """The whole view tool must not carry any Lua console command."""
        source = SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("ExecuteLuaAsync", source)
        for prefix in LUA_CONSOLE_PREFIXES:
            self.assertNotIn(prefix, source)

    def test_the_composer_asks_the_mod_for_the_small_pieces(self):
        """The composer must request the mod's bounded observations."""
        composer = (ROOT / "backend-safety" / "Tools" / "ViewComposer.cs").read_text(
            encoding="utf-8")
        for observation in ('"status"', '"inventory"', '"terrain"', '"map"',
                            '"overlay"', '"recipes"', '"research"'):
            self.assertIn(observation, composer)
        self.assertNotIn("ExecuteLuaAsync", composer)

    def test_telemetry_failure_has_safe_diagnostic_not_unhandled_mcp_error(self):
        source = SOURCE.read_text(encoding="utf-8")
        block = telemetry_block(source)
        self.assertIn('catch (Exception ex)', block)
        self.assertIn('telemetry_transport_failed', block)
        self.assertIn('ex.GetType().Name', block)
        self.assertNotIn('ex.Message', block)


if __name__ == "__main__":
    unittest.main()
