"""Temporary second-pass review probe (deleted after use)."""
import importlib.util
import pathlib
import tempfile

spec = importlib.util.spec_from_file_location(
    "b", "tests/build_isolated_backend.py")
if spec is None:
    raise ImportError("Could not load tests/build_isolated_backend.py")
if spec.loader is None:
    raise ImportError("Could not load loader for tests/build_isolated_backend.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 1. prune must not remove unrelated directories
with tempfile.TemporaryDirectory() as d:
    root = pathlib.Path(d)
    keep = root / "Keep"
    keep.mkdir()
    (keep / "x.txt").write_text("data")
    print("prune_non_clone_removed =", m.prune_scratch_projects(root))
    print("unrelated_dir_intact =", (keep / "x.txt").is_file())

# 2. product project is a fixed constant, not user input
print("product_project =", m.PRODUCT_PROJECT)
print("product_no_traversal =", ".." not in str(m.PRODUCT_PROJECT))

# 3. TFM comparison edge cases
cases = [("net9.0", "net9.0", True), ("net10.0", "net9.0", False),
         ("net8.0", "net10.0", True), ("net10.0", "net10.0", True),
         ("net9.0", None, True), ("netstandard2.0", "net9.0", True),
         ("net11.0", "net9.0", False)]
bad = [c for c in cases if m.tfm_is_supported(c[0], c[1]) != c[2]]
print("tfm_edge_cases_all_correct =", not bad, bad)

# 4. real SDK ceiling on this machine
print("sdk_max_tfm =", m.installed_sdk_max_tfm())
