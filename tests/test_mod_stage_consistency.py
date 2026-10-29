"""Assert tested mod staging contains exactly the current source files.

Both active 2.1.23 profiles are covered: the Pyanodons staging directory and
the isolated installation's portable mods directory (Vanilla + Space Age).
The sync helper ``tests/sync_mod_stage.py`` writes both, so both are verified
here.
"""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

SOURCE = ROOT / "factorio-mod" / "autoengineer-input_2.1.23"
STAGED = ROOT / ".local" / "mod-test-mods" / "2.1.23" / "autoengineer-input_2.1.23"


def _source_files() -> set[Path]:
    return {
        p.relative_to(SOURCE)
        for p in SOURCE.rglob("*")
        if p.is_file() and not p.name.endswith(".bak")
    }


class ModStageConsistency(unittest.TestCase):
    """The staged mod must be byte-identical to the mod source."""

    def _assert_stage_matches(self, staged: Path, label: str) -> None:
        if not staged.exists():
            self.skipTest(f"No local {label} staging directory; live mod test not configured")
        self.assertTrue(SOURCE.is_dir(), "Missing versioned mod source")
        source = _source_files()
        staged_files = {
            p.relative_to(staged)
            for p in staged.rglob("*")
            if p.is_file() and not p.name.endswith(".bak")
        }
        self.assertEqual(source, staged_files, f"{label} staged mod differs in file list")
        for rel in sorted(source):
            with self.subTest(profile=label, file=str(rel)):
                self.assertEqual(
                    hashlib.sha256((SOURCE / rel).read_bytes()).digest(),
                    hashlib.sha256((staged / rel).read_bytes()).digest(),
                    f"Stale staged mod file: {rel}",
                )

    def test_staged_mod_matches_source(self) -> None:
        self._assert_stage_matches(STAGED, "Pyanodons")

    def test_vanilla_profile_staged_mod_matches_source(self) -> None:
        import sync_mod_stage

        self._assert_stage_matches(sync_mod_stage.VANILLA_PROFILE, "Vanilla")

    def test_sync_removes_only_staged_files_missing_from_source(self) -> None:
        """Regression: the sync must not delete a freshly copied source file.

        The previous implementation removed ``set(files) - staged_files``,
        which is the set of source files missing from the stage. Those files
        had just been copied, so the sync deleted them again and the staged
        mod was missing its newest module.
        """
        import shutil
        import tempfile

        import sync_mod_stage

        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "staged"
            target.mkdir()
            (target / "obsolete.lua").write_text("old", encoding="utf-8")

            original_targets = sync_mod_stage.STAGE_TARGETS
            original_argv = sys.argv
            try:
                sync_mod_stage.STAGE_TARGETS = (target,)
                sys.argv = ["sync_mod_stage.py"]
                self.assertEqual(sync_mod_stage.main(), 0)
            finally:
                sync_mod_stage.STAGE_TARGETS = original_targets
                sys.argv = original_argv

            staged_files = {p.name for p in target.iterdir() if p.is_file()}
            source_files = {p.name for p in sync_mod_stage.source_files()}
            self.assertEqual(
                staged_files,
                source_files,
                "Staged file set must equal the source file set after a sync",
            )
            self.assertNotIn(
                "obsolete.lua", staged_files,
                "A staged file that no longer exists in the source must be removed",
            )
            self.assertIn(
                "observation_catalog_builder.lua", staged_files,
                "Every source file must be present in the stage after a sync",
            )
            shutil.rmtree(raw, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
