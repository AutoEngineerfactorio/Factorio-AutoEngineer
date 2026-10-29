"""Fog-of-war state model tests for the read-only dashboard map.

Factorio 2.1.23 has exactly three map-tile visibility states. These tests
pin the shared model that the backend's terrain palette and the dashboard's
renderer both rely on, so a change in one cannot silently disagree with the
other.

The state model:

* ``unexplored`` - the chunk was never charted. Nothing is revealed; the
  tile is black.
* ``charted``    - the chunk was charted but is not currently visible. The
  terrain is drawn darkened by Factorio's map shading factor, and no live
  entity is reported for it.
* ``visible``    - the chunk is charted and currently visible. The terrain
  is drawn at full brightness and the live entities in it are reported.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from dashboard_map_layers import (  # noqa: E402
    FOG_BLACK,
    FOG_CHARTED,
    FOG_SHADING_FACTOR,
    FOG_UNEXPLORED,
    FOG_VISIBLE,
    fog_state,
    shade_fog_color,
)

TOOLS_SOURCE = ROOT / "backend-safety" / "AutoEngineerTools.cs"
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
MOD = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
#: The observation runs inside the mod now. The terrain raster and the
#: entity observation are two separate modules.
MOD_TERRAIN = MOD / "observation_terrain.lua"
MOD_MAP = MOD / "observation_map.lua"


class FogStateTests(unittest.TestCase):
    def test_unexplored_when_neither_charted_nor_visible(self):
        self.assertEqual(fog_state(False, False), FOG_UNEXPLORED)

    def test_charted_when_charted_but_not_visible(self):
        self.assertEqual(fog_state(True, False), FOG_CHARTED)

    def test_visible_when_currently_visible(self):
        self.assertEqual(fog_state(True, True), FOG_VISIBLE)

    def test_visible_wins_because_visibility_implies_charting(self):
        # Factorio's is_chunk_visible already implies "charted and visible",
        # so a visible chunk is visible whatever the charted flag says.
        self.assertEqual(fog_state(False, True), FOG_VISIBLE)

    def test_the_three_states_are_distinct(self):
        self.assertEqual(len({FOG_UNEXPLORED, FOG_CHARTED, FOG_VISIBLE}), 3)

    def test_unexplored_tiles_are_black(self):
        self.assertEqual(FOG_BLACK, "#000000")


class FogShadingTests(unittest.TestCase):
    def test_charted_terrain_is_darkened_to_the_games_factor(self):
        # 0xFF * 0.6667 == 170 == 0xAA
        self.assertEqual(shade_fog_color("#ffffff"), "#aaaaaa")

    def test_shading_uses_the_verified_factor(self):
        self.assertAlmostEqual(FOG_SHADING_FACTOR, 0.6667, places=4)

    def test_black_stays_black(self):
        self.assertEqual(shade_fog_color("#000000"), "#000000")

    def test_a_darkened_colour_is_darker_than_the_original(self):
        shaded = shade_fog_color("#6a8694")
        self.assertIsNotNone(shaded)
        assert shaded is not None
        self.assertLess(int(shaded[1:3], 16), 0x6A)
        self.assertLess(int(shaded[3:5], 16), 0x86)
        self.assertLess(int(shaded[5:7], 16), 0x94)

    def test_unusable_colours_are_not_guessed(self):
        for bad in ("", "#12345", "ffffff", "#gggggg", None, 123, "#1234567"):
            self.assertIsNone(shade_fog_color(bad))


class ObserverRendererAgreementTests(unittest.TestCase):
    """The observer's terrain palette and the renderer must agree.

    The observation runs inside the ``autoengineer-input`` mod, so these
    assertions pin the mod's Lua rather than the backend's C#. The
    behaviour they protect is unchanged: the same shading factor, the same
    black unexplored tile, the same two chunk predicates and the same
    visibility gate on live entities.
    """

    def setUp(self):
        self.terrain = MOD_TERRAIN.read_text(encoding="utf-8")
        self.entities = MOD_MAP.read_text(encoding="utf-8")

    def test_the_observer_uses_the_same_shading_factor(self):
        # The observer shades a charted-but-not-visible tile by this factor
        # while it builds the terrain palette.
        self.assertIn(str(FOG_SHADING_FACTOR), self.terrain)

    def test_the_observer_keeps_unexplored_tiles_black(self):
        # An uncharted tile stays on palette index 0, which is black.
        self.assertIn('palette = { "#000000" }', self.terrain)

    def test_the_observer_queries_both_charted_and_visible_predicates(self):
        self.assertIn("is_chunk_visible", self.terrain)
        self.assertIn("is_chunk_charted", self.terrain)

    def test_the_observer_gates_entities_on_current_visibility(self):
        # A live entity is only reported for a chunk that is currently
        # visible; a charted-but-hidden chunk reports no live entity.
        self.assertIn("is_visible(entity.position.x, entity.position.y)", self.entities)

    def test_the_backend_no_longer_sends_a_lua_console_command(self):
        # The normal read path must not carry any Lua at all. The gameplay
        # writing tools still use the upstream services; they are audited
        # separately and are not part of the read path.
        source = TOOLS_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("ExecuteLuaAsync", source)
        self.assertNotIn("ExecuteLuaAsync", TOOLS_SOURCE.read_text(encoding="utf-8"))
        composer = (ROOT / "backend-safety" / "Tools" / "ViewComposer.cs").read_text(
            encoding="utf-8")
        self.assertNotIn("ExecuteLuaAsync", composer)
        transport = (ROOT / "backend-safety" / "Tools" / "ModObservation.cs").read_text(
            encoding="utf-8")
        self.assertNotIn("ExecuteLuaAsync", transport)


if __name__ == "__main__":
    unittest.main()
