"""Assert tested mod staging contains exactly the current source files."""
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
STAGED = ROOT / ".local" / "mod-test-mods" / "2.1.23" / "autoengineer-input_2.1.23"


class ModStageConsistency(unittest.TestCase):
    def test_staged_mod_matches_source(self):
        if not STAGED.exists():
            self.skipTest("No local 2.1.23 staging directory; live mod test not configured")
        self.assertTrue(SOURCE.is_dir(), "Missing versioned mod source")
        source = {p.relative_to(SOURCE): p for p in SOURCE.rglob("*") if p.is_file() and not p.name.endswith(".bak")}
        staged = {p.relative_to(STAGED): p for p in STAGED.rglob("*") if p.is_file() and not p.name.endswith(".bak")}
        self.assertEqual(set(source), set(staged), "Staged mod differs in file list")
        for rel in sorted(source):
            with self.subTest(file=str(rel)):
                self.assertEqual(
                    hashlib.sha256(source[rel].read_bytes()).digest(),
                    hashlib.sha256(staged[rel].read_bytes()).digest(),
                    f"Stale staged mod file: {rel}",
                )


if __name__ == "__main__":
    unittest.main()

