"""Tests for safe Factorio 2.1.23 icon path resolution."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_icons import (
    ICON_PACKAGES,
    all_icon_candidates,
    enabled_mod_names,
    factorio_data_root,
    factorio_mods_root,
    icon_candidates,
    icon_frame_geometry,
    is_safe_prototype_name,
    mod_icon_candidates,
    quality_icon_candidates,
)


class SafeNameTests(unittest.TestCase):
    def test_safe_names_are_accepted(self):
        for name in ("iron-plate", "electronic-circuit", "nuclear_fuel", "copper2"):
            self.assertTrue(is_safe_prototype_name(name), name)

    def test_traversal_and_non_ascii_names_are_rejected(self):
        for name in ("../secret", "..\\secret", "a/b", "a:b", "ä", "", None, 5, "a b"):
            self.assertFalse(is_safe_prototype_name(name), repr(name))

    def test_candidates_are_empty_for_unsafe_names(self):
        for name in ("../secret", "a/b", "", None, "C:evil"):
            self.assertEqual(icon_candidates(Path("data"), name), ())

    def test_quality_icon_candidates_only_for_known_tiers(self):
        self.assertTrue(quality_icon_candidates(Path("data"), "epic"))
        self.assertEqual(quality_icon_candidates(Path("data"), "normal"), ())
        self.assertEqual(quality_icon_candidates(Path("data"), "bogus"), ())
        self.assertEqual(quality_icon_candidates(Path("data"), None), ())


class CandidateTests(unittest.TestCase):
    def test_candidates_cover_vanilla_and_space_age_packages(self):
        paths = list(icon_candidates(Path("data"), "iron-plate"))
        self.assertTrue(paths)
        self.assertEqual(paths[0], Path("data/base/graphics/icons/iron-plate.png"))
        joined = " ".join(str(p) for p in paths)
        for package in ("base", "space-age", "quality"):
            self.assertIn(package, joined)

    def test_every_candidate_stays_inside_the_icon_directory(self):
        for path in icon_candidates(Path("data"), "iron-plate"):
            # <root>/<package>/graphics/icons/<name>.png
            self.assertEqual(path.parent.name, "icons")
            self.assertEqual(path.parent.parent.name, "graphics")
            self.assertIn(path.parent.parent.parent.name, ICON_PACKAGES)
            self.assertEqual(path.suffix, ".png")
            self.assertEqual(path.name, "iron-plate.png")


class DataRootTests(unittest.TestCase):
    def test_default_points_at_the_isolated_installation(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            root = factorio_data_root()
        self.assertIn("Factorio-Isolated-2.1.23", str(root))
        self.assertEqual(root.name, "data")

    def test_override_is_respected(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"AUTOENGINEER_FACTORIO_DATA": r"D:\custom\data"}):
            self.assertEqual(factorio_data_root(), Path(r"D:\custom\data"))


class ModIconTests(unittest.TestCase):
    def test_missing_mod_list_yields_no_mods(self):
        self.assertEqual(enabled_mod_names(Path("does-not-exist")), ())

    def test_mod_list_names_are_read(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod-list.json").write_text(json.dumps({
                "mods": [
                    {"name": "my-mod", "enabled": True},
                    {"name": "off-mod", "enabled": False},
                    {"name": "../evil", "enabled": True},
                ]
            }), encoding="utf-8")
            self.assertEqual(enabled_mod_names(root), ("my-mod",))

    def test_mod_candidates_stay_inside_the_mods_folder(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod-list.json").write_text(json.dumps({
                "mods": [{"name": "my-mod", "enabled": True}]
            }), encoding="utf-8")
            paths = list(mod_icon_candidates(root, "my-item"))
            self.assertEqual(len(paths), 1)
            self.assertEqual(
                paths[0], root / "my-mod" / "graphics" / "icons" / "my-item.png"
            )

    def test_versioned_mod_directory_is_resolved(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod-list.json").write_text(json.dumps({
                "mods": [{"name": "PerfectlyGenericObject", "enabled": True}]
            }), encoding="utf-8")
            (root / "PerfectlyGenericObject_1.210.0").mkdir()
            paths = mod_icon_candidates(root, "perfectly-generic-object")
            self.assertIn(root / "PerfectlyGenericObject_1.210.0" / "graphics" / "icons" / "perfectly-generic-object.png", paths)

    def test_mod_candidates_reject_unsafe_names(self):
        for name in ("../secret", "a/b", "", None):
            self.assertEqual(mod_icon_candidates(Path("mods"), name), ())

    def test_all_candidates_put_vanilla_before_mods(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod-list.json").write_text(json.dumps({
                "mods": [{"name": "my-mod", "enabled": True}]
            }), encoding="utf-8")
            paths = list(all_icon_candidates(Path("data"), root, "thing"))
            # data/<package>/graphics/icons/<name>.png
            self.assertEqual(paths[0].parts[-4], "base")
            # <mods>/<mod>/graphics/icons/<name>.png
            self.assertEqual(paths[-1].parts[-4], "my-mod")

    def test_mods_root_defaults_to_the_isolated_installation(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {}, clear=True):
            root = factorio_mods_root()
        self.assertIn("Factorio-Isolated-2.1.23", str(root))
        self.assertEqual(root.name, "mods")

    def test_mods_root_override_is_respected(self):
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"AUTOENGINEER_FACTORIO_MODS": r"D:\custom\mods"}):
            self.assertEqual(factorio_mods_root(), Path(r"D:\custom\mods"))


class AtlasGeometryTests(unittest.TestCase):
    def test_mipmap_strip_reports_frame_size_and_count(self):
        # Factorio stores icons as a 64 + 32 + 16 + 8 horizontal mipmap strip.
        self.assertEqual(icon_frame_geometry(120, 64), (64, 4))

    def test_square_icon_is_a_single_frame(self):
        self.assertEqual(icon_frame_geometry(64, 64), (64, 1))

    def test_invalid_sizes_are_rejected(self):
        self.assertEqual(icon_frame_geometry(0, 64), (0, 0))
        self.assertEqual(icon_frame_geometry(64, -1), (0, 0))


if __name__ == "__main__":
    unittest.main()
