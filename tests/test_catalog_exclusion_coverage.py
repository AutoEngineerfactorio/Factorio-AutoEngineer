"""Accounted exclusions must not masquerade as missing catalog pages."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"agent"))
from read_only_planning import accounted_recipe_count, validate_exclusions


class CatalogExclusionCoverageTests(unittest.TestCase):
    def test_explicit_empty_lua_table_is_empty(self):
        self.assertEqual(validate_exclusions({"excluded": {}}),[])

    def test_malformed_exclusions_still_fail(self):
        for entries in ({"name":"x"},"unknown",[{}]):
            with self.subTest(entries=entries),self.assertRaises(ValueError):
                validate_exclusions({"excluded":entries})

    def test_supported_and_excluded_recipes_are_counted_separately(self):
        self.assertEqual(accounted_recipe_count({"recipes":[{"name":"a"}],
            "excluded":[{"name":"b","reason":"unsupported_shape"}]}),2)

    def test_same_recipe_cannot_be_supported_and_excluded(self):
        with self.assertRaisesRegex(ValueError,"overlapping"):
            accounted_recipe_count({"recipes":[{"name":"a"}],
                "excluded":[{"name":"a","reason":"unsupported_shape"}]})

    def test_complete_page_can_explicitly_exclude_an_unsupported_recipe(self):
        from dashboard_feed import snapshot
        from test_catalog_assembly import page
        frame=page(1,["a"],total_count=2,total_pages=1)
        frame["capabilities"]["excluded"]=[{"name":"b","reason":"unsupported_shape"}]
        frame["catalog_status"].update(snapshot=True,snapshot_tick=120,observation_tick=125)
        parsed=snapshot(frame)
        self.assertFalse(parsed["capabilities"]["truncated"])
        self.assertEqual(len(parsed["capabilities"]["excluded"]),1)

    def test_unknown_snapshot_metadata_is_rejected(self):
        from dashboard_feed import snapshot
        from test_catalog_assembly import page
        frame=page(1,["a"],total_count=1,total_pages=1)
        frame["catalog_status"]["untrusted_override"]=True
        with self.assertRaises(ValueError):
            snapshot(frame)

    def test_large_snapshot_batch_is_validated_at_its_actual_bound(self):
        from dashboard_feed import snapshot
        from test_catalog_assembly import page
        frame=page(1,[f"r-{n:03d}" for n in range(128)],total_count=128,total_pages=1)
        frame["catalog_status"]["page_size"]=128
        self.assertEqual(len(snapshot(frame)["capabilities"]["recipes"]),128)
        frame["catalog_status"]["page_size"]=129
        with self.assertRaises(ValueError):
            snapshot(frame)
