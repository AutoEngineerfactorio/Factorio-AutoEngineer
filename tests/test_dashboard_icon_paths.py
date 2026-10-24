"""Verify safe icon paths in the isolated Factorio 2.1.23 installation."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_icons import ICON_PACKAGES
from dashboard_view import factorio_data_root, icon_candidates


class DashboardIconPaths(unittest.TestCase):
    def test_default_uses_isolated_factorio(self):
        with patch.dict(os.environ, {}, clear=True):
            root = factorio_data_root()
        self.assertIn("Factorio-Isolated-2.1.23", str(root))
        self.assertEqual(root.name, "data")

    def test_override_is_respected(self):
        with patch.dict(os.environ, {"AUTOENGINEER_FACTORIO_DATA": r"D:\custom\data"}):
            self.assertEqual(factorio_data_root(), Path(r"D:\custom\data"))

    def test_valid_icons_choose_packaged_paths(self):
        paths = icon_candidates(Path("data"), "iron-plate")
        path_list = list(paths)
        self.assertEqual(len(path_list), len(ICON_PACKAGES))
        self.assertEqual(path_list[0], Path("data/base/graphics/icons/iron-plate.png"))
        # Space Age, quality and the other shipped packages are searched too.
        self.assertIn("space-age", " ".join(str(p) for p in path_list))
        self.assertIn("quality", " ".join(str(p) for p in path_list))

    def test_traversal_and_non_ascii_names_do_not_access_files(self):
        for name in ("../secret", r"..\secret", "a/b", "a:b", "ä", "", None):
            with self.subTest(name=name):
                self.assertEqual(icon_candidates(Path("data"), name), ())


if __name__ == "__main__":
    unittest.main()
