"""Transport regression: authoritative catalog must reach the planner intact."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RichCatalogComposerTests(unittest.TestCase):
    def test_registered_transport_preserves_envelope(self):
        source = (ROOT / "backend-safety/Tools/ViewComposer.cs").read_text(encoding="utf-8")
        block = source.split("public async Task<string> ComposeCatalog(", 1)[1].split("public async Task<string> ComposeInventory(", 1)[0]
        self.assertIn('rcon, "capabilities", arguments', block)
        self.assertIn('frame["capabilities"] = rich;', block)
        self.assertIn('frame["catalog_status"] = ReadObject(catalog, "catalog_status")', block)
        self.assertIn('frame["tick"] = ReadNumber(rich, "tick")', block)
        self.assertIn('frame["capabilities"] = null', block)
        self.assertNotIn('rcon, "recipes"', block)

    def test_snapshot_metadata_is_not_mixed_with_live_inventory(self):
        source = (ROOT / "backend-safety/Tools/ViewComposer.cs").read_text(encoding="utf-8")
        block = source.split("public async Task<string> ComposeCatalog(", 1)[1].split("public async Task<string> ComposeInventory(", 1)[0]
        self.assertIn("Frame(snapshotStatus, snapshotInventory, null)", block)
        self.assertIn("ModObservation.IsUsable(snapshotStatus)", block)
        self.assertIn("ModObservation.IsUsable(snapshotInventory)", block)
