"""Shared generated-document fixtures for the R07-B property tests.

Offline only. These tests never read a user save, never call the game and
never perform network access.

The generator is seeded, so the family of documents is identical on every run
and a failure is always reproducible. The sweep is deliberately bounded: it is
a correctness sweep over the shapes the encoder must support, not a stress
loop.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_blueprint_encoder import VERSION_2_0_10, VERSION_2_0_76  # noqa: E402

# A bounded sweep: enough documents to cover the shapes, few enough to stay
# fast.
SWEEP_SIZE = 40
SEED = 20261024

LABELS = ["Alpha", "Beta 中文", "Gamma", "Delta \U0001f600", "Epsilon"]
PROTOTYPES = ["transport-belt", "assembling-machine-1", "inserter", "fast-splitter"]
QUALITIES = ["normal", "uncommon", "rare", "epic", "legendary"]


def _random_position(rng: random.Random) -> dict[str, float]:
    return {
        "x": rng.choice([0.0, -0.0, 0.5, -1.25, 12.75, rng.uniform(-100, 100)]),
        "y": rng.choice([0.0, -0.5, 3.25, -7.125, rng.uniform(-100, 100)]),
    }


def _random_entity(rng: random.Random, number: int) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "entity_number": number,
        "name": rng.choice(PROTOTYPES),
        "position": _random_position(rng),
        "direction": rng.choice([0, 2, 4, 6, 8, 10, 12, 14]),
    }
    if rng.random() < 0.6:
        entity["recipe"] = rng.choice(
            ["iron-gear-wheel", "copper-plate", "advanced-circuit"]
        )
    if rng.random() < 0.3:
        entity["quality"] = rng.choice(QUALITIES)
    if rng.random() < 0.3:
        entity["filters"] = [
            {"index": index, "name": "iron-plate", "count": rng.randint(0, 100)}
            for index in range(rng.randint(1, 3))
        ]
    if rng.random() < 0.3:
        entity["items"] = {"iron-plate": {"count": rng.randint(0, 999), "amount": 1}}
    if rng.random() < 0.2:
        entity["wires"] = [
            [
                [rng.randint(1, 50), rng.randint(1, 4)],
                [rng.randint(1, 50), rng.randint(1, 4)],
            ]
            for _ in range(rng.randint(1, 2))
        ]
    if rng.random() < 0.2:
        entity["unknown_member"] = {"nested": [rng.randint(0, 9), "keep-me", True]}
    return entity


def random_blueprint(rng: random.Random) -> dict[str, Any]:
    """A random but valid blueprint document."""
    count = rng.randint(0, 6)
    blueprint: dict[str, Any] = {
        "item": "blueprint",
        "label": rng.choice(LABELS),
        "version": VERSION_2_0_10,
        "entities": [_random_entity(rng, number) for number in range(1, count + 1)],
    }
    if rng.random() < 0.5:
        blueprint["icons"] = [
            {"icon": "virtual-signal/signal-A", "icon_size": 1, "type": "item"}
        ]
    if rng.random() < 0.5:
        blueprint["tiles"] = [
            {
                "name": "concrete",
                "position": {"x": float(index), "y": 0.0},
                "position2": {"x": float(index + 1), "y": 0.0},
                "tile": "concrete",
            }
            for index in range(rng.randint(1, 3))
        ]
    if rng.random() < 0.4:
        blueprint["unknown_blueprint_member"] = rng.choice([1, "text", [1, 2], {"a": 1}])
    return {"blueprint": blueprint}


def random_book(rng: random.Random, depth: int = 0) -> dict[str, Any]:
    """A random but valid blueprint book, optionally with a nested book."""
    entries: list[dict[str, Any]] = []
    indexes = rng.sample(range(0, 40), rng.randint(1, 5))
    for index in indexes:
        if depth < 2 and rng.random() < 0.25:
            nested = random_book(rng, depth + 1)["blueprint_book"]
            entries.append({"blueprint_book": nested, "index": index})
        else:
            blueprint = random_blueprint(rng)["blueprint"]
            entries.append({"blueprint": blueprint, "index": index})
    book: dict[str, Any] = {
        "item": "blueprint-book",
        "blueprints": entries,
        "active_index": rng.randint(0, 10),
        "version": VERSION_2_0_76,
    }
    if rng.random() < 0.3:
        book["unknown_book_member"] = {"kept": True}
    return {"blueprint_book": book}


def random_document(rng: random.Random) -> dict[str, Any]:
    """A random supported document: a blueprint or a blueprint book."""
    if rng.random() < 0.5:
        return random_blueprint(rng)
    return random_book(rng)


def coverage(rng: random.Random, count: int = SWEEP_SIZE) -> dict[str, int]:
    """Report what the generated family actually exercises.

    A generator that silently stopped producing, say, wires or quality
    identifiers would make the property sweep much weaker than it looks.
    This self-check keeps the sweep honest: it is called by the property
    tests and asserts that every group is represented.
    """
    stats = {
        "blueprints": 0,
        "books": 0,
        "nested_books": 0,
        "entities": 0,
        "wires": 0,
        "quality": 0,
        "filters": 0,
        "items": 0,
        "icons": 0,
        "tiles": 0,
        "non_ascii_labels": 0,
        "unknown_members": 0,
    }
    for _ in range(count):
        document = random_document(rng)
        if "blueprint" in document:
            stats["blueprints"] += 1
            blueprint = document["blueprint"]
            stats["entities"] += len(blueprint.get("entities", []))
            if "icons" in blueprint:
                stats["icons"] += 1
            if "tiles" in blueprint:
                stats["tiles"] += 1
            if any(ord(char) > 127 for char in blueprint.get("label", "")):
                stats["non_ascii_labels"] += 1
            if "unknown_blueprint_member" in blueprint:
                stats["unknown_members"] += 1
            for entity in blueprint.get("entities", []):
                if "wires" in entity:
                    stats["wires"] += 1
                if "quality" in entity:
                    stats["quality"] += 1
                if "filters" in entity:
                    stats["filters"] += 1
                if "items" in entity:
                    stats["items"] += 1
                if "unknown_member" in entity:
                    stats["unknown_members"] += 1
        else:
            stats["books"] += 1
            for entry in document["blueprint_book"]["blueprints"]:
                if "blueprint_book" in entry:
                    stats["nested_books"] += 1
                    for inner in entry["blueprint_book"]["blueprints"]:
                        if "blueprint_book" in inner:
                            stats["nested_books"] += 1
    return stats
