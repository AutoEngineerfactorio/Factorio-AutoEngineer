"""Regression tests for the accurate in-game nature map layer (R08).

These cover the behaviours the R08 request names explicitly: tree rendering,
rock rendering, cliff rendering, prototype map colour extraction, observed
geometry, coordinate accuracy, visibility boundaries, modded natural entities,
large forests and preservation of the resource-patch layer.

Every colour asserted here is a **verified Factorio 2.1.23** value taken from
the pinned offline 2.1.23 prototype API archive or from the verified 2.1.23
installation's data stage. No colour is invented.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))

import dashboard_map_layers
import dashboard_nature_layers as nature


class PrototypeMapColorTests(unittest.TestCase):
    """Extraction of the prototype map colour the game itself uses."""

    def test_float_color_components_scale_to_bytes(self):
        self.assertEqual(nature.parse_map_color({"r": 1.0, "g": 0.0, "b": 0.0}), "#ff0000")

    def test_zero_to_one_components_are_fractions(self):
        self.assertEqual(nature.parse_map_color({"r": 0.0, "g": 0.5, "b": 1.0}), "#0080ff")

    def test_zero_to_255_components_are_absolute(self):
        # Factorio's Color type documents that a component above 1 means the
        # whole colour is given in 0..255 units.
        self.assertEqual(nature.parse_map_color({"r": 129, "g": 105, "b": 78}), "#81694e")

    def test_short_array_form_is_accepted(self):
        self.assertEqual(nature.parse_map_color([129, 105, 78]), "#81694e")
        self.assertEqual(nature.parse_map_color([129, 105, 78, 1.0]), "#81694e")

    def test_alpha_is_accepted_and_ignored_for_the_opaque_map_colour(self):
        self.assertEqual(nature.parse_map_color({"r": 0.19, "g": 0.39, "b": 0.19, "a": 0.40}),
                         "#306330")

    def test_invalid_colors_are_rejected_not_guessed(self):
        for bad in (None, {}, {"r": 1}, "red", [1, 2], {"r": "a", "g": 0, "b": 0},
                    {"r": True, "g": 0, "b": 0}, {"r": float("nan"), "g": 0, "b": 0},
                    {"r": 0, "g": 0, "b": 300}):
            self.assertIsNone(nature.parse_map_color(bad), bad)

    def test_verified_vanilla_prototype_colors(self):
        # data/base/prototypes/decorative/decoratives.lua -> big-rock
        self.assertEqual(nature.verified_prototype_map_color("big-rock"), "#81694e")
        # data/base/prototypes/entity/entity-util.lua -> scaled_cliff default
        self.assertEqual(nature.verified_prototype_map_color("cliff"), "#907757")

    def test_unknown_prototype_has_no_verified_color(self):
        self.assertIsNone(nature.verified_prototype_map_color("some-mod-tree"))
        self.assertIsNone(nature.verified_prototype_map_color(None))

    def test_observed_color_wins_over_the_verified_table(self):
        entity = {"name": "big-rock", "map_color": {"r": 0.0, "g": 1.0, "b": 0.0}}
        self.assertEqual(nature.nature_color(entity), "#00ff00")

    def test_the_runtime_white_default_is_never_painted(self):
        # LIVE READ-ONLY evidence from the running 2.1.23 game: every
        # prototype reports map_color {255,255,255}, including copper-ore
        # whose real chart colour is #cd6337. White is the runtime's "no
        # chart colour" marker and must never become a drawn colour.
        entity = {"name": "tree-08", "prototype_type": "tree",
                  "map_color": {"r": 255, "g": 255, "b": 255}}
        self.assertNotEqual(nature.nature_color(entity), "#ffffff")

    def test_a_tree_uses_its_verified_tint_palette_entry(self):
        # Factorio tints a tree sprite with the palette entry selected by the
        # entity's graphics variation. The in-game map draws that tint shaded
        # by the game's own map shading factor.
        entity = {"name": "tree-01", "prototype_type": "tree",
                  "graphics_variation": 6}
        self.assertEqual(nature.nature_color(entity),
                         nature.shade_color("#47e04a", nature.MAP_SHADING_FACTOR))

    def test_the_tree_colour_is_darker_than_the_bright_world_sprite(self):
        # The in-game map draws a tree darker than the world sprite. A tree
        # colour must never be the unshaded sprite tint.
        entity = {"name": "tree-08", "prototype_type": "tree",
                  "graphics_variation": 0}
        colour = nature.nature_color(entity)
        palette = nature.tree_tint_palette("tree-08")
        if palette is None:
            self.fail("tree-08 must have a verified tint palette")
        self.assertNotEqual(colour, palette[0])
        self.assertEqual(colour, nature.shade_color(palette[0],
                                                     nature.MAP_SHADING_FACTOR))

    def test_shade_color_uses_the_game_map_shading_factor(self):
        self.assertEqual(nature.shade_color("#ffffff", 1.0), "#ffffff")
        self.assertEqual(nature.shade_color("#ffffff", 0.0), "#000000")
        self.assertEqual(nature.shade_color("#ff8000", 0.5), "#804000")
        self.assertIsNone(nature.shade_color("not-a-colour", 0.5))
        self.assertIsNone(nature.shade_color("#12345", 0.5))

    def test_the_tree_colour_index_wraps_the_palette_like_the_game(self):
        # LIVE READ-ONLY evidence: tree-08 has seven palette entries but
        # placed trees were observed with graphics variations up to 10, so the
        # colour index wraps around the palette.
        palette = nature.tree_tint_palette("tree-08")
        if palette is None:
            self.fail("tree-08 must have a verified tint palette")
        self.assertEqual(len(palette), 7)
        for variation in range(0, 20):
            entity = {"name": "tree-08", "prototype_type": "tree",
                      "graphics_variation": variation}
            self.assertEqual(nature.nature_color(entity),
                             nature.shade_color(palette[variation % len(palette)],
                                                nature.MAP_SHADING_FACTOR))

    def test_a_tree_without_a_known_variation_gets_no_invented_colour(self):
        entity = {"name": "tree-01", "prototype_type": "tree"}
        self.assertIsNone(nature.nature_color(entity))

    def test_a_negative_variation_gets_no_invented_colour(self):
        entity = {"name": "tree-01", "prototype_type": "tree",
                  "graphics_variation": -1}
        self.assertIsNone(nature.nature_color(entity))

    def test_a_dead_tree_without_a_palette_gets_no_invented_colour(self):
        entity = {"name": "dead-tree-desert", "prototype_type": "tree",
                  "graphics_variation": 3}
        self.assertIsNone(nature.nature_color(entity))

    def test_every_verified_tree_palette_entry_is_a_hex_colour(self):
        for name, palette in nature.VERIFIED_TREE_TINT_PALETTES.items():
            self.assertTrue(name.startswith("tree-"), name)
            self.assertGreater(len(palette), 0, name)
            for colour in palette:
                self.assertRegex(colour, r"^#[0-9a-f]{6}$", f"{name}: {colour}")

    def test_friendly_map_color_wins_over_the_generic_map_color(self):
        # The 2.1.23 runtime API documents map_color as the colour used "if a
        # friendly or enemy color isn't defined", so the force-specific colour
        # is the one the game charts with.
        entity = {
            "name": "some-tree",
            "friendly_map_color": {"r": 1.0, "g": 0.0, "b": 0.0},
            "map_color": {"r": 0.0, "g": 0.0, "b": 1.0},
        }
        self.assertEqual(nature.nature_color(entity), "#ff0000")

    def test_enemy_map_color_wins_over_the_generic_map_color(self):
        entity = {
            "name": "some-tree",
            "enemy_map_color": {"r": 0.0, "g": 1.0, "b": 0.0},
            "map_color": {"r": 0.0, "g": 0.0, "b": 1.0},
        }
        self.assertEqual(nature.nature_color(entity), "#00ff00")

    def test_verified_table_is_the_fallback_when_nothing_was_observed(self):
        entity = {"name": "big-rock"}
        self.assertEqual(nature.nature_color(entity), "#81694e")

    def test_no_color_is_invented_for_an_unknown_natural_prototype(self):
        # An unknown prototype with no observed colour must report "no
        # authoritative colour" instead of guessing one.
        entity = {"name": "some-mod-rock", "prototype_type": "simple-entity"}
        self.assertIsNone(nature.nature_color(entity))


class NatureClassificationTests(unittest.TestCase):
    """Trees, rocks and cliffs are distinguished by observed prototype data."""

    def shape_of(self, entity):
        """Return the classified shape, failing the test if there is none."""
        shape = nature.nature_shape(entity)
        if shape is None:
            self.fail(f"expected a natural shape for {entity!r}")
        return shape

    def test_tree_prototype_is_a_tree(self):
        shape = self.shape_of(
            {"x": 10, "y": 20, "name": "tree-01", "prototype_type": "tree"}
        )
        self.assertEqual(shape.kind, "tree")

    def test_tree_entity_type_is_a_tree(self):
        shape = self.shape_of(
            {"x": 10, "y": 20, "name": "mod-tree", "entity_type": "tree"}
        )
        self.assertEqual(shape.kind, "tree")

    def test_simple_entity_prototype_is_a_rock(self):
        shape = self.shape_of(
            {"x": 1, "y": 2, "name": "big-rock", "prototype_type": "simple-entity"}
        )
        self.assertEqual(shape.kind, "rock")

    def test_cliff_prototype_is_a_cliff(self):
        shape = self.shape_of(
            {"x": 1, "y": 2, "name": "cliff", "prototype_type": "cliff"}
        )
        self.assertEqual(shape.kind, "cliff")

    def test_a_resource_is_never_a_natural_object(self):
        # A stone ore deposit has prototype type "resource" and must never be
        # classified as a mineable rock.
        shape = nature.nature_shape(
            {"x": 1, "y": 2, "name": "stone-ore", "prototype_type": "resource"}
        )
        self.assertIsNone(shape)

    def test_a_building_is_never_a_natural_object(self):
        shape = nature.nature_shape(
            {"x": 1, "y": 2, "name": "stone-furnace", "prototype_type": "furnace"}
        )
        self.assertIsNone(shape)

    def test_an_unclassifiable_entity_is_not_drawn(self):
        self.assertIsNone(nature.nature_shape({"x": 1, "y": 2, "name": "mystery"}))

    def test_a_non_numeric_position_is_rejected(self):
        self.assertIsNone(nature.nature_shape(
            {"x": "10", "y": 2, "name": "tree-01", "prototype_type": "tree"}))
        self.assertIsNone(nature.nature_shape(
            {"x": None, "y": 2, "name": "tree-01", "prototype_type": "tree"}))
        self.assertIsNone(nature.nature_shape(
            {"x": float("inf"), "y": 2, "name": "tree-01", "prototype_type": "tree"}))
        self.assertIsNone(nature.nature_shape(
            {"x": True, "y": 2, "name": "tree-01", "prototype_type": "tree"}))


class ObservedGeometryTests(unittest.TestCase):
    """Only the observer's own geometry is used; nothing is inferred."""

    def shape_of(self, entity):
        """Return the classified shape, failing the test if there is none."""
        shape = nature.nature_shape(entity)
        if shape is None:
            self.fail(f"expected a natural shape for {entity!r}")
        return shape

    def test_width_and_height_are_the_observed_footprint(self):
        shape = self.shape_of({
            "x": 0, "y": 0, "name": "big-rock", "prototype_type": "simple-entity",
            "width": 2.0, "height": 2.0,
        })
        self.assertEqual(shape.tiles, (2.0, 2.0))

    def test_bounds_are_the_observed_footprint(self):
        shape = self.shape_of({
            "x": 5, "y": 5, "name": "cliff", "prototype_type": "cliff",
            "bounds": {"left_top": {"x": 4.0, "y": 4.0}, "right_bottom": {"x": 6.0, "y": 6.0}},
        })
        self.assertEqual(shape.tiles, (2.0, 2.0))

    def test_no_observed_geometry_means_no_footprint(self):
        shape = self.shape_of(
            {"x": 0, "y": 0, "name": "tree-01", "prototype_type": "tree"}
        )
        self.assertIsNone(shape.tiles)

    def test_incomplete_geometry_is_ignored_rather_than_guessed(self):
        shape = self.shape_of({
            "x": 0, "y": 0, "name": "tree-01", "prototype_type": "tree", "width": 3.0,
        })
        self.assertIsNone(shape.tiles)

    def test_inverted_bounds_are_rejected(self):
        shape = self.shape_of({
            "x": 0, "y": 0, "name": "cliff", "prototype_type": "cliff",
            "bounds": {"left_top": {"x": 6.0, "y": 6.0}, "right_bottom": {"x": 4.0, "y": 4.0}},
        })
        self.assertIsNone(shape.tiles)

    def test_tree_symbol_is_the_game_marker_size_without_geometry(self):
        shape = self.shape_of(
            {"x": 0, "y": 0, "name": "tree-01", "prototype_type": "tree"}
        )
        self.assertEqual(nature.tree_shape(shape), nature.TREE_MARKER_TILES)

    def test_rock_symbol_grows_with_an_observed_footprint(self):
        shape = self.shape_of({
            "x": 0, "y": 0, "name": "big-rock", "prototype_type": "simple-entity",
            "width": 2.0, "height": 2.0,
        })
        self.assertGreater(nature.rock_shape(shape), nature.ROCK_MARKER_TILES)

    def test_cliff_symbol_uses_its_own_marker_size(self):
        shape = self.shape_of(
            {"x": 0, "y": 0, "name": "cliff", "prototype_type": "cliff"}
        )
        self.assertEqual(nature.cliff_shape(shape), nature.CLIFF_MARKER_TILES)

    def test_trees_and_rocks_have_different_marker_sizes(self):
        self.assertNotEqual(nature.TREE_MARKER_TILES, nature.ROCK_MARKER_TILES)


class NatureShapesCollectionTests(unittest.TestCase):
    """The layer collects only observed nature entities."""

    def test_only_nature_kind_entities_are_collected(self):
        entities = [
            {"kind": "nature", "x": 1, "y": 1, "name": "tree-01", "prototype_type": "tree"},
            {"kind": "resource", "x": 2, "y": 2, "name": "iron-ore", "prototype_type": "resource"},
            {"kind": "building", "x": 3, "y": 3, "name": "furnace", "prototype_type": "furnace"},
        ]
        shapes = nature.nature_shapes(entities)
        self.assertEqual(len(shapes), 1)
        self.assertEqual(shapes[0].kind, "tree")

    def test_entities_outside_the_observed_window_are_dropped(self):
        entities = [
            {"kind": "nature", "x": 10, "y": 10, "name": "tree-01", "prototype_type": "tree"},
            {"kind": "nature", "x": 500, "y": 10, "name": "tree-01", "prototype_type": "tree"},
        ]
        window = {"x": 0, "y": 0, "width": 256, "height": 256}
        shapes = nature.nature_shapes(entities, window)
        self.assertEqual(len(shapes), 1)
        self.assertEqual(shapes[0].x, 10)

    def test_coordinates_are_preserved_exactly(self):
        entities = [
            {"kind": "nature", "x": 12.25, "y": -7.5, "name": "tree-01",
             "prototype_type": "tree"},
        ]
        shapes = nature.nature_shapes(entities)
        self.assertEqual(shapes[0].x, 12.25)
        self.assertEqual(shapes[0].y, -7.5)

    def test_a_non_list_input_yields_no_shapes(self):
        self.assertEqual(nature.nature_shapes(None), [])
        self.assertEqual(nature.nature_shapes({}), [])

    def test_a_large_forest_is_handled_in_one_pass(self):
        # 5000 observed trees must all be classified, with no truncation and
        # no fabrication.
        entities = [
            {"kind": "nature", "x": float(i % 250), "y": float(i // 250),
             "name": "tree-01", "prototype_type": "tree"}
            for i in range(5000)
        ]
        shapes = nature.nature_shapes(entities)
        self.assertEqual(len(shapes), 5000)
        self.assertTrue(all(s.kind == "tree" for s in shapes))

    def test_a_modded_natural_entity_is_classified_from_observed_data(self):
        # A mod tree reports the vanilla prototype type "tree" and its own
        # prototype name; the layer must handle it without a hard-coded list.
        entities = [
            {"kind": "nature", "x": 3, "y": 4, "name": "alien-tree",
             "prototype_type": "tree", "map_color": {"r": 0.5, "g": 0.0, "b": 0.5}},
        ]
        shapes = nature.nature_shapes(entities)
        self.assertEqual(len(shapes), 1)
        self.assertEqual(shapes[0].kind, "tree")
        self.assertEqual(shapes[0].color, "#800080")


class NatureFingerprintTests(unittest.TestCase):
    """The observation fingerprint drives the nature-layer cache."""

    def test_identical_observations_share_a_fingerprint(self):
        entities = [
            {"kind": "nature", "x": 1, "y": 2, "name": "tree-01", "prototype_type": "tree"},
        ]
        other = [
            {"kind": "nature", "x": 1, "y": 2, "name": "tree-01", "prototype_type": "tree"},
        ]
        self.assertEqual(nature.nature_fingerprint(entities),
                         nature.nature_fingerprint(other))

    def test_a_moved_tree_changes_the_fingerprint(self):
        before = [
            {"kind": "nature", "x": 1, "y": 2, "name": "tree-01", "prototype_type": "tree"},
        ]
        after = [
            {"kind": "nature", "x": 9, "y": 2, "name": "tree-01", "prototype_type": "tree"},
        ]
        self.assertNotEqual(nature.nature_fingerprint(before),
                            nature.nature_fingerprint(after))

    def test_a_changed_colour_changes_the_fingerprint(self):
        before = [
            {"kind": "nature", "x": 1, "y": 2, "name": "tree-01",
             "prototype_type": "tree", "map_color": {"r": 1.0}},
        ]
        after = [
            {"kind": "nature", "x": 1, "y": 2, "name": "tree-01",
             "prototype_type": "tree", "map_color": {"r": 0.0}},
        ]
        self.assertNotEqual(nature.nature_fingerprint(before),
                            nature.nature_fingerprint(after))

    def test_non_nature_entities_do_not_affect_the_fingerprint(self):
        nature_only = [
            {"kind": "nature", "x": 1, "y": 2, "name": "tree-01", "prototype_type": "tree"},
        ]
        with_building = nature_only + [
            {"kind": "building", "x": 3, "y": 4, "name": "furnace"},
        ]
        self.assertEqual(nature.nature_fingerprint(nature_only),
                         nature.nature_fingerprint(with_building))

    def test_a_non_list_input_yields_an_empty_fingerprint(self):
        self.assertEqual(nature.nature_fingerprint(None), ())
        self.assertEqual(nature.nature_fingerprint({}), ())

    def test_a_large_forest_fingerprint_is_cheap_and_stable(self):
        entities = [
            {"kind": "nature", "x": float(i), "y": 0.0, "name": "tree-01",
             "prototype_type": "tree"}
            for i in range(2000)
        ]
        first = nature.nature_fingerprint(entities)
        second = nature.nature_fingerprint(list(entities))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2000)


class ResourceLayerPreservationTests(unittest.TestCase):
    """The nature layer must not disturb the resource-patch layer."""

    def test_resource_patches_are_still_built_from_resource_entities(self):
        entities = [
            {"kind": "resource", "x": 10.5, "y": 10.5, "name": "iron-ore",
             "bounds": {"left_top": {"x": 10.0, "y": 10.0},
                        "right_bottom": {"x": 12.0, "y": 12.0}}},
        ]
        patches = dashboard_map_layers.resource_patch_cells(entities)
        self.assertIn("iron-ore", patches)
        self.assertEqual(len(patches["iron-ore"]), 4)

    def test_nature_entities_never_contribute_to_a_resource_patch(self):
        entities = [
            {"kind": "nature", "x": 10.5, "y": 10.5, "name": "big-rock",
             "prototype_type": "simple-entity", "width": 2.0, "height": 2.0},
        ]
        self.assertEqual(dashboard_map_layers.resource_patch_cells(entities), {})

    def test_resource_patch_color_table_is_unchanged(self):
        self.assertEqual(dashboard_map_layers.resource_patch_color("iron-ore"), "#6a8694")
        self.assertEqual(dashboard_map_layers.resource_patch_color("copper-ore"), "#cd6337")


class ViewWiringTests(unittest.TestCase):
    """The view must use the nature layer and keep the render order."""

    @staticmethod
    def view_source():
        import dashboard_view

        module_path = dashboard_view.__file__
        if module_path is None:
            raise AssertionError("dashboard_view has no source file")
        with open(Path(module_path), encoding="utf-8") as handle:
            return handle.read()

    def test_view_imports_the_nature_layer(self):
        source = self.view_source()
        self.assertIn("dashboard_nature_layers", source)
        self.assertIn("def draw_nature", source)
        self.assertIn("nature_shapes", source)

    def test_nature_layer_is_drawn_after_resource_patches(self):
        source = self.view_source()
        patches = source.index("self.draw_resource_patches(terrain")
        nature = source.index("self.draw_nature(terrain")
        self.assertLess(patches, nature)

    def test_nature_layer_is_drawn_before_the_entity_loop(self):
        source = self.view_source()
        nature = source.index("self.draw_nature(terrain")
        entities = source.index('for e in terrain.get("entities", []):')
        self.assertLess(nature, entities)

    def test_the_generic_nature_circle_is_gone(self):
        source = self.view_source()
        self.assertNotIn('"rock" in name or "boulder" in name', source)

    def test_natural_objects_are_not_drawn_with_a_black_outline(self):
        source = self.view_source()
        for marker in ("def _draw_tree", "def _draw_rock", "def _draw_cliff"):
            self.assertIn(marker, source)
        start = source.index("def _draw_tree")
        end = source.index("def draw(self):")
        block = source[start:end]
        self.assertNotIn('outline="#111416"', block)
        self.assertNotIn('outline="#1a1b17"', block)

    def test_the_nature_layer_caches_its_classified_shapes(self):
        source = self.view_source()
        self.assertIn("def _nature_shape_cache", source)
        self.assertIn("nature_fingerprint", source)


if __name__ == "__main__":
    unittest.main()
