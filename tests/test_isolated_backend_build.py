"""Regression tests for the isolated backend build helper.

The pinned upstream FactorioMCP tree contains upstream-author scratch
projects (for example TempInspect, which targets net10.0). When the clone is
restored or built as a whole, the installed .NET SDK fails with NETSDK1045
because it cannot target that framework. These tests pin the behaviour that
keeps only the product project in the build graph and reports an
unsupported framework before any restore or build is attempted.
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent / "build_isolated_backend.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_isolated_backend", _MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec from {_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backend = _load_module()


class ScratchProjectPruningTests(unittest.TestCase):
    def test_scratch_project_is_removed_from_clone(self):
        with tempfile.TemporaryDirectory() as dirname:
            clone = Path(dirname)
            scratch = clone / "TempInspect"
            scratch.mkdir()
            (scratch / "TempInspect.csproj").write_text(
                "<Project><PropertyGroup>"
                "<TargetFramework>net10.0</TargetFramework>"
                "</PropertyGroup></Project>", encoding="utf-8")
            removed = backend.prune_scratch_projects(clone)
            self.assertEqual(removed, ["TempInspect"])
            self.assertFalse(scratch.exists())

    def test_product_project_is_never_removed(self):
        with tempfile.TemporaryDirectory() as dirname:
            clone = Path(dirname)
            product = clone / "FactorioMCP"
            product.mkdir()
            project = product / "FactorioMCP.csproj"
            project.write_text("<Project />", encoding="utf-8")
            backend.prune_scratch_projects(clone)
            self.assertTrue(project.is_file())

    def test_pruning_is_idempotent_and_absent_dirs_are_safe(self):
        with tempfile.TemporaryDirectory() as dirname:
            clone = Path(dirname)
            self.assertEqual(backend.prune_scratch_projects(clone), [])
            (clone / "TempInspect").mkdir()
            self.assertEqual(backend.prune_scratch_projects(clone), ["TempInspect"])
            self.assertEqual(backend.prune_scratch_projects(clone), [])


class TargetFrameworkTests(unittest.TestCase):
    def test_target_frameworks_are_read_from_project(self):
        with tempfile.TemporaryDirectory() as dirname:
            project = Path(dirname) / "Sample.csproj"
            project.write_text(
                "<Project><PropertyGroup>"
                "<TargetFramework>net9.0</TargetFramework>"
                "</PropertyGroup></Project>", encoding="utf-8")
            self.assertEqual(backend.target_frameworks(project), ["net9.0"])

    def test_missing_or_unreadable_project_yields_no_frameworks(self):
        with tempfile.TemporaryDirectory() as dirname:
            self.assertEqual(backend.target_frameworks(Path(dirname) / "none.csproj"), [])

    def test_sdk_ceiling_rejects_newer_framework(self):
        self.assertFalse(backend.tfm_is_supported("net10.0", "net9.0"))
        self.assertTrue(backend.tfm_is_supported("net9.0", "net9.0"))
        self.assertTrue(backend.tfm_is_supported("net8.0", "net9.0"))

    def test_unknown_ceiling_fails_open(self):
        # An unknown SDK version must not block the build on its own.
        self.assertTrue(backend.tfm_is_supported("net10.0", None))

    def test_non_numeric_frameworks_are_not_blocked(self):
        self.assertTrue(backend.tfm_is_supported("netstandard2.0", "net9.0"))


class ProductProjectTests(unittest.TestCase):
    def test_product_project_is_the_backend_project(self):
        self.assertEqual(backend.PRODUCT_PROJECT,
                         Path("FactorioMCP") / "FactorioMCP.csproj")

    def test_scratch_directories_do_not_include_the_product_project(self):
        self.assertNotIn("FactorioMCP", backend.SCRATCH_PROJECT_DIRS)
        self.assertIn("TempInspect", backend.SCRATCH_PROJECT_DIRS)


class CloneSweepInRegressionTests(unittest.TestCase):
    """Reproduce the NETSDK1045 sweep-in shape seen in the isolated clone.

    The pinned vendor tree carries TempInspect (net10.0). A whole-tree
    restore would pull it in and the installed SDK would fail with
    NETSDK1045 even though the shipped backend only targets net9.0.
    """

    def _clone_with_scratch_project(self, root):
        scratch = root / "TempInspect"
        scratch.mkdir()
        (scratch / "TempInspect.csproj").write_text(
            "<Project><PropertyGroup>"
            "<TargetFramework>net10.0</TargetFramework>"
            "</PropertyGroup></Project>", encoding="utf-8")
        product_dir = root / "FactorioMCP"
        product_dir.mkdir()
        product = product_dir / "FactorioMCP.csproj"
        product.write_text(
            "<Project><PropertyGroup>"
            "<TargetFramework>net9.0</TargetFramework>"
            "</PropertyGroup></Project>", encoding="utf-8")
        return product

    def test_prune_leaves_no_scratch_project_in_the_clone(self):
        with tempfile.TemporaryDirectory() as dirname:
            clone = Path(dirname)
            product = self._clone_with_scratch_project(clone)
            backend.prune_scratch_projects(clone)
            remaining = sorted(p.name for p in clone.rglob("*.csproj"))
            self.assertEqual(remaining, ["FactorioMCP.csproj"])
            self.assertTrue(product.is_file())

    def test_product_framework_is_supported_by_the_installed_sdk(self):
        with tempfile.TemporaryDirectory() as dirname:
            clone = Path(dirname)
            product = self._clone_with_scratch_project(clone)
            backend.prune_scratch_projects(clone)
            declared = backend.target_frameworks(product)
            self.assertEqual(declared, ["net9.0"])
            self.assertTrue(backend.tfm_is_supported(declared[0],
                                                    backend.installed_sdk_max_tfm()))

    def test_scratch_framework_would_be_unsupported_on_a_net9_sdk(self):
        # Guards the regression itself: the scratch project is exactly what
        # the installed SDK cannot build.
        self.assertFalse(backend.tfm_is_supported("net10.0", "net9.0"))


if __name__ == "__main__":
    unittest.main()
