"""Tests for the exact Factorio 2.1.23 API signature lookup helper.

These tests enforce the project's exact-signature rule: an API name that is
not in the 2.1.23 archive must be reported as unknown, never guessed.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

import factorio_api_2123 as api  # noqa: E402


class Factorio2123ApiLookup(unittest.TestCase):
    def test_archive_declares_supported_version(self):
        self.assertEqual(api.runtime_api()["application_version"], "2.1.23")
        self.assertEqual(api.prototype_api()["application_version"], "2.1.23")

    def test_find_known_class(self):
        entry = api.find_class("LuaGameScript")
        self.assertEqual(entry["name"], "LuaGameScript")

    def test_find_known_method_signature(self):
        method = api.find_method("LuaGameScript", "take_screenshot")
        self.assertEqual(method["name"], "take_screenshot")
        names = {p["name"] for p in method["parameters"]}
        # The 2.1.23 archive records take_screenshot with flat named
        # parameters, not a single nested `param` struct.
        self.assertIn("hide_health_bars", names)
        self.assertIn("path", names)

    def test_method_signature_is_human_readable(self):
        signature = api.method_signature("LuaGameScript", "take_screenshot")
        self.assertTrue(signature.startswith("LuaGameScript.take_screenshot("))
        # Optional parameters are marked with a trailing '?'.
        self.assertIn("path?", signature)
        # Parameters are ordered by the archive's documented `order` field.
        self.assertLess(
            signature.index("player?"), signature.index("hide_health_bars?")
        )

    def test_find_known_event_and_fields(self):
        self.assertIn("player_index", api.event_fields("on_player_respawned"))

    def test_unknown_class_fails_closed(self):
        with self.assertRaises(api.UnknownApiError) as ctx:
            api.find_class("LuaThisDoesNotExist")
        self.assertIn("UNVERIFIED", str(ctx.exception))

    def test_unknown_method_fails_closed(self):
        with self.assertRaises(api.UnknownApiError):
            api.find_method("LuaGameScript", "definitely_not_a_method")

    def test_unknown_event_fails_closed(self):
        with self.assertRaises(api.UnknownApiError):
            api.find_event("on_not_a_real_event")

    def test_has_api_is_false_for_unknown(self):
        self.assertTrue(api.has_api("LuaSurface"))
        self.assertFalse(api.has_api("LuaNotARealClass"))

    def test_2_0_only_event_is_reported_unknown(self):
        """A 2.0-era event must not resolve against the 2.1.23 archive.

        This guards against an archived 2.0.77/2.1.22 signature leaking in as
        if it were current.
        """
        self.assertFalse(api.has_api("on_player_start_select_area"))
        with self.assertRaises(api.UnknownApiError):
            api.find_event("on_player_start_select_area")

    def test_2_1_23_only_api_is_present(self):
        """A signature added in 2.1.23 must resolve from the 2.1.23 archive."""
        game = api.find_class("LuaGameScript")
        capture = next(
            m for m in game["methods"] if m["name"] == "take_screenshot"
        )
        names = {p["name"] for p in capture["parameters"]}
        self.assertIn("hide_health_bars", names)

    def test_a_runtime_attribute_resolves(self):
        """A runtime class member must resolve.

        The 2.1.23 archive keeps a runtime class's readable members under
        ``attributes`` and a prototype class's under ``properties``. A
        lookup that only searched ``properties`` reported every runtime
        attribute as missing, which made a documented member look
        unverified.
        """
        prop = api.find_property("LuaEntityPrototype", "module_inventory_size")
        self.assertEqual(prop["name"], "module_inventory_size")
        self.assertEqual(prop["read_type"], "uint32")

    def test_a_prototype_property_still_resolves(self):
        """A data-stage prototype property must keep resolving.

        The prototype (data stage) document keeps its classes under
        ``prototypes`` and their members under ``properties``, so the
        prototype-stage lookup must not be broken by the runtime fix.
        """
        prop = api.find_property("EntityPrototype", "build_grid_size",
                                 stage="prototype")
        self.assertEqual(prop["name"], "build_grid_size")

    def test_the_data_stage_crafting_speed_resolves(self):
        """The data stage declares the machine crafting speed.

        The data-stage ``CraftingMachinePrototype`` declares the base
        ``crafting_speed`` and the ``module_slots`` count. These are the
        documented meaning of the values the runtime method
        ``get_crafting_speed`` and the attribute ``module_inventory_size``
        report at normal quality.
        """
        speed = api.find_property("CraftingMachinePrototype", "crafting_speed",
                                  stage="prototype")
        self.assertEqual(speed["name"], "crafting_speed")
        self.assertEqual(speed["type"], "double")
        self.assertFalse(speed["optional"])
        slots = api.find_property("CraftingMachinePrototype", "module_slots",
                                  stage="prototype")
        self.assertEqual(slots["name"], "module_slots")
        self.assertTrue(slots["optional"])
        # The slot count defaults to zero, so a machine without modules
        # legitimately has no slots.
        self.assertEqual(slots["default"]["value"], 0)

    def test_a_prototype_stage_class_resolves(self):
        """A data-stage class must resolve from the prototype document."""
        entry = api.find_class("EntityPrototype", stage="prototype")
        self.assertEqual(entry["name"], "EntityPrototype")

    def test_the_declared_machine_accessors_resolve(self):
        """The accessors the machine collection uses must all resolve."""
        for name in ("module_inventory_size",
                     "crafting_speed_quality_multiplier",
                     "quality_affects_module_slots",
                     "module_slots_quality_bonus"):
            with self.subTest(name=name):
                found = api.find_property("LuaEntityPrototype", name)
                self.assertEqual(found["name"], name)
        self.assertEqual(
            api.method_signature("LuaEntityPrototype", "get_crafting_speed"),
            "LuaEntityPrototype.get_crafting_speed(quality?)")
        self.assertEqual(
            api.method_signature("LuaEntityPrototype", "get_inventory_size"),
            "LuaEntityPrototype.get_inventory_size(index, quality?)")

    def test_an_absent_runtime_attribute_fails_closed(self):
        """A member the archive does not declare must still be unknown.

        The fix must not turn the lookup into a permissive one: the plain
        ``crafting_speed`` and ``module_slots`` names are not declared by
        2.1.23 and must stay unverified.
        """
        for name in ("crafting_speed", "module_slots", "fluid_boxes"):
            with self.subTest(name=name):
                with self.assertRaises(api.UnknownApiError):
                    api.find_property("LuaEntityPrototype", name)


if __name__ == "__main__":
    unittest.main()
