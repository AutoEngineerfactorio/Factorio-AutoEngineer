"""Tests for the pure Factorio-style inventory layout model."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from dashboard_inventory import (
    build_layout,
    changed_slots,
    inventory_columns,
    layout_fingerprint,
    quality_color,
    quality_rank,
    tooltip_text,
)


def observed(slots, capacity=None, **extra):
    data = {"slots": slots, "capacity": capacity if capacity is not None else len(slots)}
    data.update(extra)
    return data


class InventoryColumnsTests(unittest.TestCase):
    def test_columns_adapt_to_width(self):
        self.assertEqual(inventory_columns(408), 10)
        self.assertEqual(inventory_columns(248), 6)
        self.assertEqual(inventory_columns(1), 1)
        self.assertEqual(inventory_columns(0), 1)
        self.assertEqual(inventory_columns(-50), 1)


class SlotNumberTests(unittest.TestCase):
    def test_real_slot_numbers_are_preserved(self):
        data = observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 7, "name": "copper-plate", "quality": "normal", "count": 3},
            {"slot": 12, "name": "stone", "quality": "normal", "count": 9},
        ], capacity=20)
        layout = build_layout(data, 408)
        self.assertTrue(layout.actual)
        self.assertFalse(layout.aggregate)
        self.assertEqual([s.index for s in layout.slots], [1, 7, 12])

    def test_slots_are_not_reordered_by_item_name(self):
        data = observed([
            {"slot": 1, "name": "zinc-plate", "quality": "normal", "count": 1},
            {"slot": 2, "name": "iron-plate", "quality": "normal", "count": 1},
            {"slot": 3, "name": "copper-plate", "quality": "normal", "count": 1},
        ], capacity=3)
        layout = build_layout(data, 408)
        self.assertEqual(
            [s.name for s in layout.slots], ["zinc-plate", "iron-plate", "copper-plate"]
        )

    def test_out_of_range_slots_are_dropped(self):
        data = observed([
            {"slot": 0, "name": "iron-plate", "quality": "normal", "count": 1},
            {"slot": 99, "name": "copper-plate", "quality": "normal", "count": 1},
            {"slot": 2, "name": "stone", "quality": "normal", "count": 1},
        ], capacity=3)
        layout = build_layout(data, 408)
        self.assertEqual([s.index for s in layout.slots], [2])

    def test_positions_follow_the_grid(self):
        data = observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 1},
            {"slot": 11, "name": "copper-plate", "quality": "normal", "count": 1},
        ], capacity=20)
        layout = build_layout(data, 408)
        self.assertEqual(layout.columns, 10)
        self.assertEqual((layout.slots[0].x, layout.slots[0].y), (4, 4))
        self.assertEqual((layout.slots[1].x, layout.slots[1].y), (4, 44))

    def test_aggregate_fallback_is_flagged(self):
        data = {"inventory": [
            {"name": "iron-plate", "quality": "normal", "count": 12},
            {"name": "copper-plate", "quality": "normal", "count": 4},
        ]}
        layout = build_layout(data, 408)
        self.assertFalse(layout.actual)
        self.assertTrue(layout.aggregate)
        self.assertEqual([s.index for s in layout.slots], [1, 2])
        self.assertEqual(layout.slots[0].count, 12)

    def test_none_data_yields_empty_layout(self):
        layout = build_layout(None, 408)
        self.assertEqual(layout.slots, ())
        self.assertTrue(layout.aggregate)
        self.assertEqual(layout.capacity, 0)


class CapacityTests(unittest.TestCase):
    def test_dynamic_capacity_sets_rows(self):
        layout = build_layout(observed([], capacity=80), 408)
        self.assertEqual(layout.capacity, 80)
        self.assertEqual(layout.columns, 10)
        self.assertEqual(layout.rows, 8)

    def test_truncation_is_reported(self):
        layout = build_layout(observed([], capacity=80, slots_truncated=True), 408)
        self.assertTrue(layout.partial)

    def test_responsive_columns_change_row_count(self):
        data = observed([{"slot": 1, "name": "a", "quality": "normal", "count": 1}], capacity=40)
        wide = build_layout(data, 408)
        narrow = build_layout(data, 248)
        self.assertNotEqual(wide.columns, narrow.columns)
        self.assertNotEqual(wide.rows, narrow.rows)


class DiffTests(unittest.TestCase):
    def test_unchanged_slots_are_not_reported(self):
        before = build_layout(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 2, "name": "copper-plate", "quality": "normal", "count": 3},
        ], capacity=10), 408)
        after = build_layout(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 2, "name": "copper-plate", "quality": "normal", "count": 4},
        ], capacity=10), 408)
        changed, removed = changed_slots(before.slots, after.slots)
        self.assertEqual(changed, {2})
        self.assertEqual(removed, set())

    def test_removed_slots_are_reported(self):
        before = build_layout(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
            {"slot": 2, "name": "copper-plate", "quality": "normal", "count": 3},
        ], capacity=10), 408)
        after = build_layout(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=10), 408)
        changed, removed = changed_slots(before.slots, after.slots)
        self.assertEqual(changed, set())
        self.assertEqual(removed, {2})

    def test_fingerprint_is_stable_for_identical_data(self):
        data = observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=10)
        self.assertEqual(
            layout_fingerprint(build_layout(data, 408)),
            layout_fingerprint(build_layout(data, 408)),
        )

    def test_fingerprint_changes_when_a_count_changes(self):
        before = observed([{"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5}],
                          capacity=10)
        after = observed([{"slot": 1, "name": "iron-plate", "quality": "normal", "count": 6}],
                         capacity=10)
        self.assertNotEqual(
            layout_fingerprint(build_layout(before, 408)),
            layout_fingerprint(build_layout(after, 408)),
        )


class QualityTests(unittest.TestCase):
    def test_quality_colours_match_the_game(self):
        self.assertEqual(quality_color("uncommon"), "#68b64b")
        self.assertEqual(quality_color("rare"), "#529bea")
        self.assertEqual(quality_color("epic"), "#ae61d5")
        self.assertEqual(quality_color("legendary"), "#e6a135")

    def test_unknown_quality_falls_back_to_normal(self):
        self.assertEqual(quality_color("mystery"), quality_color("normal"))

    def test_quality_rank_orders_tiers(self):
        ranks = [quality_rank(q) for q in ("normal", "uncommon", "rare", "epic", "legendary")]
        self.assertEqual(ranks, sorted(ranks))

    def test_missing_quality_defaults_to_normal(self):
        layout = build_layout(
            observed([{"slot": 1, "name": "iron-plate", "count": 2}], capacity=2), 408
        )
        self.assertEqual(layout.slots[0].quality, "normal")


class TooltipTests(unittest.TestCase):
    def test_tooltip_reports_name_count_quality_and_slot(self):
        layout = build_layout(observed([
            {"slot": 4, "name": "iron-plate", "quality": "rare", "count": 17},
        ], capacity=10), 408)
        text = tooltip_text(layout.slots[0])
        self.assertIn("Slot 4", text)
        self.assertIn("iron-plate", text)
        self.assertIn("17", text)
        self.assertIn("rare", text)


class SlotLookupTests(unittest.TestCase):
    def test_slot_at_finds_the_hovered_slot(self):
        layout = build_layout(observed([
            {"slot": 1, "name": "iron-plate", "quality": "normal", "count": 5},
        ], capacity=10), 408)
        found = layout.slot_at(10, 10)
        assert found is not None
        self.assertEqual(found.index, 1)
        self.assertIsNone(layout.slot_at(500, 500))


if __name__ == "__main__":
    unittest.main()
