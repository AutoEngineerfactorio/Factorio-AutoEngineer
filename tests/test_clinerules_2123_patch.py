"""Verify the pending `.clinerules` 2.1.23 patch matches the real files exactly.

The patch in `docs/CLINERULES_2123_PATCH.md` is applied by an authorized
writer, because the `AutoEngineer Code & Review` mode cannot edit
`.clinerules/`. This test guards against the patch drifting away from the
files it claims to patch: every "Before" block must appear verbatim in the
target file.

It also asserts that the chunk guard was not widened to bypass the
restriction.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / ".clinerules"
PATCH = ROOT / "docs" / "CLINERULES_2123_PATCH.md"

TARGETS = (
    "04-factorio-lua-references.md",
    "05-mod-testing.md",
    "06-zoo-docs-and-extensions.md",
    "08-windows-powershell-environment.md",
    "10-edge-case-handling.md",
    "15-exa-web-youtube-research.md",
)

# Strings that must not present an old API version as the current contract.
# Each is removed by the patch.
STALE_MARKERS = (
    "lua-api.factorio.com/2.1.22/",
    "lua-api.factorio.com/2.0.77/",
    "site:lua-api.factorio.com/2.1.22 ",
    "factorio-api-offline/2.1.22/files/",
    "factorio-api-offline/2.0.77/files/",
    "Pin Factorio **2.1.22** for current implementation",
    "Choose the one matching the tested executable, not the newest by default",
    "one for 2.0.77 and one for 2.1.22",
)


def _parse_sections(text):
    """Split the patch into per-file sections keyed by file name."""
    sections = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"^## \d+\. `\.clinerules/(.+)`$", line)
        if match:
            current = match.group(1)
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def _blocks(sections, label):
    """Every fenced code block under the given label, as plain text."""
    found = []
    for lines in sections.values():
        body = "\n".join(lines)
        found.extend(
            re.findall(rf"\*\*{label}\*\*\n\n```\n(.*?)```", body, flags=re.DOTALL)
        )
    return found


class Clinerules2123Patch(unittest.TestCase):
    def setUp(self):
        self.patch_text = PATCH.read_text(encoding="utf-8")
        self.sections = _parse_sections(self.patch_text)

    def test_patch_covers_every_target_file(self):
        for name in TARGETS:
            self.assertIn(name, self.sections, f"patch does not cover {name}")

    def test_every_after_block_exists_verbatim_in_its_file(self):
        """Every documented replacement must now be present in the active rule."""
        checked = 0
        for name, lines in self.sections.items():
            body = "\n".join(lines)
            target_text = (RULES / name).read_text(encoding="utf-8")
            blocks = re.findall(
                r"\*\*After\*\*\n\n```\n(.*?)```", body, flags=re.DOTALL
            )
            self.assertTrue(blocks, f"no After block found for {name}")
            for block in blocks:
                checked += 1
                self.assertIn(
                    block.strip("\n"),
                    target_text,
                    f"After block for {name} missing from active rule:\n{block}",
                )
        self.assertGreaterEqual(checked, 10)

    def test_stale_markers_absent_from_active_rules(self):
        """Old active-version claims must not survive applying the patch."""
        after_text = "\n".join(_blocks(self.sections, "After"))
        targets_text = "\n".join(
            (RULES / name).read_text(encoding="utf-8") for name in TARGETS
        )
        for marker in STALE_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, targets_text, f"{marker} survives in active rules")
                self.assertNotIn(marker, after_text, f"{marker} survives the patch")

    def test_patch_preserves_archived_versions_as_historical(self):
        """The archived versions must stay visible, explicitly marked historical."""
        after_text = "\n".join(_blocks(self.sections, "After"))
        self.assertIn("2.0.77", after_text)
        self.assertIn("2.1.22", after_text)
        self.assertIn("archived", after_text)

    def test_patch_does_not_touch_safety_or_autonomy_gates(self):
        """The patch must not alter approvals, stops, autonomy locks or R07-B."""
        forbidden = (
            "Full Autonomy",
            "fully autonomous",
            "emergency stop",
            "approval",
            "R07-B",
            "chunk_guard",
            "max_walk",
            "five-tile",
        )
        for block in _blocks(self.sections, "After"):
            for term in forbidden:
                with self.subTest(term=term):
                    self.assertNotIn(term, block)

    def test_chunk_guard_was_not_widened(self):
        """The guard's permitted-path logic must be unchanged.

        The guard must still refuse `.clinerules/`; widening it just to permit
        these edits is explicitly out of bounds.
        """
        guard = (ROOT / "memory" / "chunk_guard.py").read_text(encoding="utf-8")
        self.assertIn("Path outside permitted source folders", guard)
        self.assertNotIn(
            '".clinerules/"',
            guard,
            "the chunk guard allowlist was widened to permit .clinerules edits",
        )
        for prefix in ("agent/", "tests/", "memory/", "docs/", "backend-safety/"):
            self.assertIn(f'"{prefix}"', guard)


if __name__ == "__main__":
    unittest.main()
