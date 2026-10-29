"""Tests for validated save-specific catalog cache."""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from qt_save_catalog_cache import (
    read_active_catalog,
    read_active_pages,
    read_or_build_compiled,
    read_save_catalog,
)


class SaveCatalogTests(unittest.TestCase):
    def test_only_matching_complete_catalog(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            save = root / "12-345"
            save.mkdir()
            metadata = {"save_id": save.name, "total_pages": 2,
                        "game_version": "2.1.23", "mod_signature": "base=2.1.23"}
            (save / "complete.json").write_text(json.dumps(metadata))
            for n in (1, 2):
                page = {"status": "ok", "catalog_status":
                        {"page": n, "total_pages": 2, "status": "ok"},
                        "capabilities": {"recipes": [{"name": f"recipe{n}"}],
                                          "research": [], "machines": []}}
                (save / f"page-{n}.json").write_text(json.dumps(page))
            marker = {"save_id": save.name, "mod_signature": "base=2.1.23"}
            (root / "current.json").write_text(json.dumps(marker))
            found = read_active_catalog(root, game_version="2.1.23")
            self.assertIsNotNone(found)
            self.assertEqual(len(found[1]["capabilities"]["recipes"]), 2)
            self.assertIsNone(read_active_catalog(root, game_version="2.1.24"))
            self.assertIsNone(read_save_catalog(save, expected_save_id="other"))
            (save / "page-2.json").unlink()
            self.assertIsNone(read_active_catalog(root, game_version="2.1.23"))

    def test_generation_scopes_pages_and_incomplete_is_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save = root / "120-345"
            first = save / "g1"
            second = save / "g2"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            marker = {
                "save_id": save.name, "generation": 2,
                "mod_signature": "base=2.1.23", "game_version": "2.1.23"}
            (root / "current.json").write_text(json.dumps(marker))
            page = {
                "status": "ok",
                "catalog_status": {"status": "ok", "page": 1,
                                   "total_pages": 3},
                "capabilities": {"recipes": [{"name": "current-recipe"}],
                                 "machines": [], "research": []}}
            (first / "page-1.json").write_text(json.dumps({
                **page, "capabilities": {"recipes": [{"name": "old-recipe"}]}}))
            (second / "page-1.json").write_text(json.dumps(page))
            result = read_active_pages(root, game_version="2.1.23")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result[1], "g2")
            self.assertEqual(result[2], 3)
            self.assertEqual(result[3][0]["capabilities"]["recipes"][0]["name"],
                             "current-recipe")
            self.assertEqual(len(result[3]), 1)
            self.assertEqual(
                read_active_pages(root, after_page=1, game_version="2.1.23")[3],
                [])
            import os

            old = time.time() - 100
            os.utime(root / "current.json", (old, old))
            self.assertIsNone(read_active_pages(root))
            self.assertIsNotNone(read_active_pages(root, allow_stale=True))

    def test_completed_catalog_compiles_once_per_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "exports"
            target = root / "100-20" / "g2"
            target.mkdir(parents=True)
            cache = Path(directory) / "desktop-cache"
            meta = {"save_id": "100-20", "generation": 2, "total_pages": 2,
                    "game_version": "2.1.23", "mod_signature": "base=2.1.23"}
            (target / "complete.json").write_text(json.dumps(meta))
            for n in (1, 2):
                payload = {
                    "status": "ok",
                    "catalog_status": {"status": "ok", "page": n,
                                       "total_pages": 2},
                    "capabilities": {"recipes": [{"name": f"recipe-{n}"}],
                                     "machines": [{"name": "furnace"}],
                                     "research": ["first-tech"]}}
                (target / f"page-{n}.json").write_text(json.dumps(payload))
            args = dict(save_id="100-20", generation="g2",
                        game_version="2.1.23", mod_signature="base=2.1.23")
            first = read_or_build_compiled(root, cache, **args)
            self.assertIsNotNone(first)
            assert first is not None
            self.assertEqual(len(first["capabilities"]["recipes"]), 2)
            self.assertEqual(len(first["capabilities"]["machines"]), 1)
            self.assertEqual(len(first["capabilities"]["research"]), 1)
            compressed = cache / "100-20" / "g2.json.gz"
            self.assertTrue(compressed.is_file())
            second = read_or_build_compiled(root, cache, **args)
            self.assertEqual(second["capabilities"]["recipes"],
                             first["capabilities"]["recipes"])
            self.assertIsNone(read_or_build_compiled(
                root, cache, **{**args, "mod_signature": "different"}))

    def test_rejects_stale_marker(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "current.json"
            path.write_text('{"save_id":"1-2","mod_signature":"base=2.1.23"}')
            import os
            old = time.time() - 100
            os.utime(path, (old, old))
            self.assertIsNone(read_active_catalog(Path(name)))


if __name__ == "__main__":
    unittest.main()
