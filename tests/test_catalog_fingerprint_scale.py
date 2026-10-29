"""Run the real mod fingerprint against large synthetic recipe catalogs."""
import unittest
from pathlib import Path
from typing import Any, cast

from test_r06_recipe_accounting import MOCK_FORCE

try:
    from lupa import LuaRuntime
except ImportError:
    raise unittest.SkipTest("lupa unavailable")

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "factorio-mod/autoengineer-input_2.1.23/observation_capabilities.lua"


def catalog(count, *, invalid_amount=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    code = (f"RECIPE_COUNT={count}; BAD_INDEX_1=-1; BAD_INDEX_2=-1;\n" + (MOCK_FORCE.replace("amount = amount", "amount = math.huge") if invalid_amount else MOCK_FORCE)
            + "\npackage.loaded.observation={observed_player=function() return p,c end};\n"
            + SOURCE.read_text(encoding="utf-8")
            + "\nreturn package.loaded.observation.capabilities(1,32,true)")
    return cast(Any, lua.execute(code))


class FingerprintScaleTests(unittest.TestCase):
    def test_small_catalog_is_fingerprinted(self):
        caps, status = catalog(10)
        self.assertIsNotNone(caps["source_fingerprint"])
        self.assertTrue(status["fingerprint_complete"])

    def test_ten_thousand_recipes_have_a_bounded_fingerprint(self):
        caps, status = catalog(10000)
        self.assertIsNotNone(caps["source_fingerprint"])
        self.assertTrue(status["fingerprint_complete"])
        self.assertFalse(caps["truncated"])
        self.assertGreater(status["fingerprint_nodes"], 100000)
        self.assertLessEqual(status["fingerprint_nodes"], 4000000)
        self.assertLessEqual(status["fingerprint_bytes"], 32000000)

    def test_invalid_numbers_cannot_acquire_a_complete_fingerprint(self):
        caps, status = catalog(10, invalid_amount=True)
        self.assertIsNone(caps["source_fingerprint"])
        self.assertFalse(status["fingerprint_complete"])
        self.assertTrue(caps["truncated"])
