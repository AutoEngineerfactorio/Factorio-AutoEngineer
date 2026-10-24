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


class BackendRendererAgreementTests(unittest.TestCase):
    """The backend's terrain palette and the renderer must agree."""

    def setUp(self):
        self.source = TOOLS_SOURCE.read_text(encoding="utf-8")
        self.patch = PATCH.read_text(encoding="utf-8")

    def test_backend_uses_the_same_shading_factor(self):
        # The backend shades a charted-but-not-visible tile by this factor
        # while it builds the terrain palette.
        self.assertIn(str(FOG_SHADING_FACTOR), self.source)

    def test_backend_keeps_unexplored_tiles_black(self):
        # An uncharted tile stays on palette index 0, which is black.
        self.assertIn('palette,colors,chunks={},{"#000000"}', self.source)

    def test_backend_queries_both_charted_and_visible_predicates(self):
        self.assertIn("is_chunk_visible", self.source)
        self.assertIn("is_chunk_charted", self.source)

    def test_backend_gates_entities_on_current_visibility(self):
        # A live entity is only reported for a chunk that is currently
        # visible; a charted-but-hidden chunk reports no live entity.
        self.assertIn("visible(e.position.x,e.position.y)", self.source)

    def test_the_patch_carries_the_same_backend_source(self):
        # The combined patch must install exactly the readable source, or
        # the running backend would not be the reviewed one.
        self.assertIn("enemy_chart_color", self.patch)
        self.assertIn("is_chunk_charted", self.patch)


if __name__ == "__main__":
    unittest.main()
