"""Regression tests for the Qt map scene builder.

These tests import no Qt module: the scene is pure drawing data, and it
must be verifiable offline.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

import qt_map_scene as scene_module  # noqa: E402
from dashboard_chunk_grid import CHUNK_TILES  # noqa: E402


def _entity(kind, x, y, name="thing", **extra):
    """Return one observed entity."""
    entity = {"kind": kind, "x": x, "y": y, "name": name}
    entity.update(extra)
    return entity


class TerrainPrimitiveTests(unittest.TestCase):
    """The terrain tiles come from the observation and nothing else."""

    def test_flat_merged_cache_tiles_are_drawn(self):
        scene = scene_module.build_scene({"tiles": [{"x": 1, "y": 2, "color": "#123456"}]})
        self.assertEqual(len(scene.by_layer("terrain")), 1)
        self.assertEqual(scene.by_layer("terrain")[0].color, "#123456")

    def test_no_terrain_produces_no_primitives(self):
        self.assertEqual(scene_module.terrain_primitives(None), [])
        self.assertEqual(scene_module.terrain_primitives({}), [])

    def test_an_observed_tile_becomes_a_primitive(self):
        terrain = {"tiles": [{"x": 3, "y": 4, "color": "#123456"}]}
        primitives = scene_module.terrain_primitives(terrain)
        self.assertEqual(len(primitives), 1)
        self.assertEqual(primitives[0].kind, "terrain")
        self.assertEqual(primitives[0].color, "#123456")
        self.assertEqual(primitives[0].width, 1.0)

    def test_a_charted_tile_is_shaded(self):
        terrain = {"tiles": [{"x": 0, "y": 0, "color": "#ffffff",
                              "visible": False}]}
        primitive = scene_module.terrain_primitives(terrain)[0]
        self.assertNotEqual(primitive.color, "#ffffff")

    def test_a_visible_tile_keeps_its_colour(self):
        terrain = {"tiles": [{"x": 0, "y": 0, "color": "#ffffff"}]}
        primitive = scene_module.terrain_primitives(terrain)[0]
        self.assertEqual(primitive.color, "#ffffff")

    def test_a_tile_without_a_colour_is_not_drawn(self):
        terrain = {"tiles": [{"x": 0, "y": 0}]}
        self.assertEqual(scene_module.terrain_primitives(terrain), [])

    def test_a_tile_without_a_position_is_not_drawn(self):
        terrain = {"tiles": [{"color": "#123456"}]}
        self.assertEqual(scene_module.terrain_primitives(terrain), [])

    def test_a_malformed_tile_is_ignored(self):
        terrain = {"tiles": ["nonsense", None, 42]}
        self.assertEqual(scene_module.terrain_primitives(terrain), [])


class ResourcePrimitiveTests(unittest.TestCase):
    """A resource field reads as one patch, not as scattered dots."""

    def test_no_entities_produces_no_patches(self):
        self.assertEqual(
            scene_module.resource_primitives([], [{"x": 0, "y": 0}],
                                             CHUNK_TILES), [])

    def test_no_observed_chunks_produces_no_patches(self):
        self.assertEqual(
            scene_module.resource_primitives(
                [_entity("resource", 10, 10, "iron-ore")], [], CHUNK_TILES), [])

    def test_an_observed_ore_becomes_a_patch(self):
        entities = [_entity("resource", 10, 10, "iron-ore",
                            bounds={"left_top": {"x": 9.5, "y": 9.5},
                                    "right_bottom": {"x": 11.5, "y": 11.5}})]
        primitives = scene_module.resource_primitives(
            entities, [{"x": 0, "y": 0}], CHUNK_TILES)
        self.assertTrue(primitives)
        self.assertEqual(primitives[0].kind, "resource")
        self.assertEqual(primitives[0].label, "iron-ore")
        self.assertTrue(primitives[0].width > 0)

    def test_a_patch_outside_the_observed_chunk_is_dropped(self):
        entities = [_entity("resource", 5000, 5000, "iron-ore",
                            bounds={"left_top": {"x": 4999.5, "y": 4999.5},
                                    "right_bottom": {"x": 5001.5, "y": 5001.5}})]
        primitives = scene_module.resource_primitives(
            entities, [{"x": 0, "y": 0}], CHUNK_TILES)
        self.assertEqual(primitives, [])


class NaturePrimitiveTests(unittest.TestCase):
    """A natural object keeps its own shape and its own chart colour."""

    def test_a_tree_with_a_chart_colour_is_drawn(self):
        entities = [_entity("nature", 5, 5, "tree-01",
                            entity_type="tree", map_color=[0.61, 1.0, 0.88])]
        primitives = scene_module.nature_primitives(entities)
        self.assertEqual(len(primitives), 1)
        self.assertEqual(primitives[0].kind, "nature")
        self.assertEqual(primitives[0].color, "#9cffe0")
        self.assertGreater(primitives[0].radius, 0)

    def test_a_natural_object_without_a_chart_colour_is_not_painted(self):
        entities = [_entity("nature", 5, 5, "tree-01", entity_type="tree")]
        self.assertEqual(scene_module.nature_primitives(entities), [])

    def test_the_runtime_white_is_not_a_chart_colour(self):
        entities = [_entity("nature", 5, 5, "copper-ore",
                            entity_type="simple-entity", map_color=[1, 1, 1])]
        self.assertEqual(scene_module.nature_primitives(entities), [])

    def test_a_cliff_keeps_its_own_shape(self):
        entities = [_entity("nature", 5, 5, "cliff",
                            entity_type="cliff", map_color=[144, 119, 87])]
        primitives = scene_module.nature_primitives(entities)
        self.assertEqual(len(primitives), 1)
        self.assertIn("cliff", primitives[0].data)

    def test_a_rock_keeps_its_own_shape(self):
        entities = [_entity("nature", 5, 5, "big-rock",
                            entity_type="simple-entity", map_color=[129, 105, 78])]
        primitives = scene_module.nature_primitives(entities)
        self.assertEqual(len(primitives), 1)
        self.assertIn("rock", primitives[0].data)


class EntityPrimitiveTests(unittest.TestCase):
    """Buildings and enemies keep the observed geometry."""

    def test_a_building_with_a_footprint_is_a_rectangle(self):
        entities = [_entity("building", 10, 10, "assembler-1",
                            width=3.0, height=3.0)]
        primitives = scene_module.entity_primitives(entities, 2.0)
        self.assertEqual(len(primitives), 1)
        self.assertEqual(primitives[0].kind, "building")
        self.assertGreater(primitives[0].width, 0)

    def test_a_building_without_geometry_is_a_symbol(self):
        entities = [_entity("building", 10, 10, "assembler-1")]
        primitives = scene_module.entity_primitives(entities, 2.0)
        self.assertEqual(len(primitives), 1)
        self.assertTrue(primitives[0].is_symbol)

    def test_an_enemy_is_always_a_symbol(self):
        entities = [_entity("enemy", 10, 10, "small-biter",
                            enemy_map_color=[1.0, 0.0, 0.0])]
        primitives = scene_module.entity_primitives(entities, 2.0)
        self.assertEqual(len(primitives), 1)
        self.assertEqual(primitives[0].kind, "enemy")
        self.assertTrue(primitives[0].is_symbol)
        self.assertEqual(primitives[0].color, "#ff0000")

    def test_an_enemy_without_a_chart_colour_uses_the_threat_red(self):
        entities = [_entity("enemy", 10, 10, "small-biter")]
        primitives = scene_module.entity_primitives(entities, 2.0)
        self.assertEqual(len(primitives), 1)
        self.assertTrue(primitives[0].color.startswith("#"))

    def test_a_resource_entity_is_not_drawn_as_a_building(self):
        entities = [_entity("resource", 10, 10, "iron-ore")]
        self.assertEqual(scene_module.entity_primitives(entities, 2.0), [])

    def test_an_entity_without_a_position_is_skipped(self):
        entities = [{"kind": "building", "name": "x"}]
        self.assertEqual(scene_module.entity_primitives(entities, 2.0), [])


class OverlayPrimitiveTests(unittest.TestCase):
    """Only an overlay the observer reported is drawn."""

    def test_no_overlays_produces_no_primitives(self):
        self.assertEqual(scene_module.overlay_primitives(None), [])
        self.assertEqual(scene_module.overlay_primitives({}), [])

    def test_an_unavailable_overlay_is_not_drawn(self):
        overlays = {"available": {"pollution": False},
                    "pollution": [{"x": 0, "y": 0, "value": 50}]}
        self.assertEqual(scene_module.overlay_primitives(overlays), [])

    def test_an_available_pollution_overlay_is_drawn(self):
        overlays = {"available": {"pollution": True},
                    "pollution": [{"x": 0, "y": 0, "value": 50,
                                   "width": 4, "height": 4}]}
        primitives = scene_module.overlay_primitives(overlays)
        self.assertEqual(len(primitives), 1)
        self.assertEqual(primitives[0].kind, "overlay")
        self.assertIn("pollution", primitives[0].data)

    def test_zero_pollution_is_not_drawn(self):
        overlays = {"available": {"pollution": True},
                    "pollution": [{"x": 0, "y": 0, "value": 0}]}
        self.assertEqual(scene_module.overlay_primitives(overlays), [])

    def test_an_electric_overlay_is_drawn(self):
        overlays = {"available": {"electric": True},
                    "electric": [{"x": 5, "y": 5, "radius": 3}]}
        primitives = scene_module.overlay_primitives(overlays)
        self.assertEqual(len(primitives), 1)
        self.assertIn("electric", primitives[0].data)


class SceneAssemblyTests(unittest.TestCase):
    """The scene assembles the observed layers into one ordered list."""

    def test_an_empty_map_produces_an_empty_scene(self):
        scene = scene_module.build_scene(None)
        self.assertEqual(scene.primitives, [])
        self.assertEqual(scene.note, "No observed map")

    def test_the_player_is_drawn_when_observed(self):
        scene = scene_module.build_scene(
            {"entities": [], "origins": []}, player={"x": 5, "y": 6})
        self.assertEqual(scene.player, (5.0, 6.0))
        self.assertEqual(len(scene.by_layer("player")), 1)

    def test_a_player_without_a_position_is_not_drawn(self):
        scene = scene_module.build_scene(
            {"entities": [], "origins": []}, player={"x": "bad"})
        self.assertIsNone(scene.player)

    def test_a_partial_map_is_marked_partial(self):
        scene = scene_module.build_scene(
            {"entities": [], "origins": [], "partial": True})
        self.assertTrue(scene.partial)

    def test_the_layers_default_to_switched_on(self):
        scene = scene_module.build_scene({"entities": [], "origins": []})
        for name in scene_module.LAYERS:
            self.assertTrue(scene.layers[name])

    def test_a_switched_off_layer_hides_its_primitives(self):
        layers = scene_module.default_layers()
        layers["resource"] = False
        scene = scene_module.build_scene(
            {"entities": [], "origins": []}, layers=layers)
        self.assertEqual(scene.by_layer("resource"), [])

    def test_the_entity_budget_is_bounded(self):
        entities = [_entity("enemy", float(i), 0.0) for i in range(100)]
        scene = scene_module.build_scene({"entities": entities, "origins": []})
        self.assertLessEqual(len(scene.primitives), scene_module.MAX_PRIMITIVES)

    def test_the_fingerprint_changes_with_the_content(self):
        first = scene_module.build_scene(
            {"entities": [_entity("enemy", 1, 1)], "origins": []})
        second = scene_module.build_scene(
            {"entities": [_entity("enemy", 2, 2)], "origins": []})
        self.assertNotEqual(first.fingerprint(), second.fingerprint())

    def test_the_fingerprint_is_stable_for_the_same_content(self):
        frame = {"entities": [_entity("enemy", 1, 1)], "origins": []}
        self.assertEqual(
            scene_module.build_scene(frame).fingerprint(),
            scene_module.build_scene(frame).fingerprint())

    def test_the_scene_holds_no_transport(self):
        """The scene must not be able to command the game."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_map_scene.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("rcon", "call_tool", "send_command"):
            self.assertNotIn(forbidden, source.lower())

    def test_the_scene_module_does_not_import_qt(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "agent", "qt_map_scene.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("PySide6", source)
        self.assertNotIn("QtWidgets", source)


if __name__ == "__main__":
    unittest.main()
