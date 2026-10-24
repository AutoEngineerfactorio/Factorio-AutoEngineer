"""R07-A: blueprint and blueprint book structure recognition.

Turns a decoded JSON value into a validated structure. It is offline only: no
network access, no game calls, no placement.

Only the documented, verified schema variants are recognized. An unknown
top-level variant is refused rather than silently treated as an ordinary
blueprint. The JSON structure bounds live here because they are properties of
the document shape rather than of the exchange container.

Blueprint book entries
-----------------------
A blueprint book is not accepted on the strength of its top-level shape alone.
Every entry is validated: the entry must be an object, it must carry exactly
one document member (``blueprint`` or ``blueprint_book``), it must carry a
non-negative integer ``index``, and the carried document is validated with the
same rules as a top-level document. Factorio supports a book inside a book, so
nested books are accepted and validated recursively under an explicit depth
bound; an unsupported nesting depth is refused rather than guessed at.

Entry order, ``index`` values, ``active_index`` and every unknown but
compatible member are left untouched, so a book round-trips unchanged.

Blueprint schema versions
-------------------------
The ``version`` field is a packed game version integer, not a small schema
counter. The game encodes it as
``(major << 48) | (minor << 32) | (build << 16) | revision``; for example
Factorio 2.0.10 is ``562949954076672`` and 2.0.76 is ``562949958402048``. The
upstream reference implementation uses exactly those values for Factorio 2.0
blueprints. A version is therefore accepted as any non-negative integer below
``16 << 48`` (the major version occupies the high 16 bits), and refused when it
is a Boolean, a float, a string, or a number too large to be a game version.
"""
from __future__ import annotations

from typing import Any, NoReturn

from blueprint_codec import BlueprintError, decode_payload

# Packed game version bounds. The major version occupies the high 16 bits of
# a 64-bit value, so any real game version is below 16 << 48. A value at or
# above that cannot be a game version and is refused.
MIN_GAME_VERSION = 0
MAX_GAME_VERSION = (16 << 48) - 1

# The recognised top-level document kinds and the key that carries them.
BLUEPRINT_KEY = "blueprint"
BLUEPRINT_BOOK_KEY = "blueprint_book"

# Document structure bounds. A hostile document must fail on one of these.
MAX_JSON_DEPTH = 64
MAX_JSON_CONTAINER_ITEMS = 20000

# Blueprint book bounds. A book may contain further books, so the entry
# validation recurses. The depth bound stops a hostile document from nesting
# books without end, and the entry bound stops a single book from carrying an
# unbounded list.
MAX_BOOK_DEPTH = 8
MAX_BOOK_ENTRIES = 20000

# The entry kinds a blueprint book entry may carry. A book entry holds exactly
# one of them.
BOOK_ENTRY_KEYS = (BLUEPRINT_KEY, BLUEPRINT_BOOK_KEY)

# The entry index must be a non-negative integer. A Boolean is refused first
# because bool subclasses int.
MAX_BOOK_INDEX = (1 << 31) - 1


def _fail(message: str) -> NoReturn:
    raise BlueprintError(message)


def _check_bounds(value: Any, depth: int = 0) -> None:
    """Reject hostile nesting and oversized containers before interpreting."""
    if depth > MAX_JSON_DEPTH:
        _fail("Blueprint JSON is nested too deeply")
    if isinstance(value, dict):
        if len(value) > MAX_JSON_CONTAINER_ITEMS:
            _fail("Blueprint JSON object has too many members")
        for item in value.values():
            _check_bounds(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_JSON_CONTAINER_ITEMS:
            _fail("Blueprint JSON array has too many items")
        for item in value:
            _check_bounds(item, depth + 1)


def _check_game_version(payload: dict[str, Any], kind: str) -> int:
    """Validate and return the packed game version integer."""
    if "version" not in payload:
        _fail(f"{kind} entry has no version")
    version = payload["version"]
    # bool is a subclass of int, so a Boolean version must be refused first.
    if isinstance(version, bool) or not isinstance(version, int):
        _fail(f"{kind} version must be an integer, got {type(version).__name__}")
    if version < MIN_GAME_VERSION or version > MAX_GAME_VERSION:
        _fail(f"Unsupported {kind} version {version!r}")
    return version


def _check_optional_list(payload: dict[str, Any], key: str, kind: str) -> int:
    """Validate an optional list member and return its length."""
    if key not in payload:
        # The game omits "entities" and "tiles" for an empty blueprint.
        return 0
    value = payload[key]
    if not isinstance(value, list):
        _fail(f"{kind} entry has a non-list {key!r}")
    return len(value)


def _check_blueprint_payload(payload: Any, kind: str) -> dict[str, Any]:
    """Validate a blueprint payload object and return it."""
    if not isinstance(payload, dict):
        _fail(f"{kind} entry is not an object")
    _check_game_version(payload, kind)
    _check_optional_list(payload, "entities", kind)
    _check_optional_list(payload, "tiles", kind)
    return payload


def _check_book_payload(payload: Any, kind: str, depth: int) -> dict[str, Any]:
    """Validate a blueprint book payload object and return it."""
    if not isinstance(payload, dict):
        _fail(f"{kind} entry is not an object")
    _check_game_version(payload, kind)
    entries = payload.get("blueprints")
    if not isinstance(entries, list):
        _fail(f"{kind} entry has no blueprint list")
    if len(entries) > MAX_BOOK_ENTRIES:
        _fail(f"{kind} entry has too many blueprint entries")
    for entry in entries:
        _check_book_entry(entry, depth + 1)
    return payload


def _check_book_entry(entry: Any, depth: int) -> None:
    """Validate one blueprint book entry.

    A game book entry carries exactly one document member (``blueprint`` or
    ``blueprint_book``) plus an integer ``index``. The game supports a book
    inside a book, so the entry is validated recursively under a depth bound.
    Every other member is an unknown but compatible field and is preserved.
    """
    if depth > MAX_BOOK_DEPTH:
        _fail("Blueprint book is nested too deeply")
    if not isinstance(entry, dict):
        _fail("Blueprint book entry is not an object")
    present = [key for key in BOOK_ENTRY_KEYS if key in entry]
    if not present:
        _fail("Blueprint book entry has no blueprint or blueprint book")
    if len(present) > 1:
        _fail("Blueprint book entry declares conflicting blueprint types")
    index = entry.get("index")
    if index is None:
        _fail("Blueprint book entry has no index")
    if isinstance(index, bool) or not isinstance(index, int):
        _fail(f"Blueprint book entry index must be an integer, got {type(index).__name__}")
    if index < 0 or index > MAX_BOOK_INDEX:
        _fail(f"Unsupported blueprint book entry index {index!r}")
    if present[0] == BLUEPRINT_KEY:
        _check_blueprint_payload(entry[BLUEPRINT_KEY], "Blueprint")
    else:
        _check_book_payload(entry[BLUEPRINT_BOOK_KEY], "Blueprint book", depth)


def classify(document: Any) -> str:
    """Return ``blueprint`` or ``blueprint_book``, or refuse the document."""
    if not isinstance(document, dict):
        _fail("Blueprint payload is not a JSON object")
    _check_bounds(document)
    has_blueprint = BLUEPRINT_KEY in document
    has_book = BLUEPRINT_BOOK_KEY in document
    if has_blueprint and has_book:
        _fail("Document declares conflicting blueprint types")
    if has_blueprint:
        _check_blueprint_payload(document[BLUEPRINT_KEY], "Blueprint")
        return "blueprint"
    if has_book:
        _check_book_payload(document[BLUEPRINT_BOOK_KEY], "Blueprint book", 0)
        return "blueprint_book"
    _fail("Document is neither a blueprint nor a blueprint book")


def describe(document: Any) -> dict[str, Any]:
    """Return classification metadata for a validated document.

    The metadata is deliberately separate from the document so the document
    itself stays byte-faithful to the source and can round-trip unchanged.
    """
    kind = classify(document)
    key = BLUEPRINT_KEY if kind == "blueprint" else BLUEPRINT_BOOK_KEY
    payload = document[key]
    metadata: dict[str, Any] = {"kind": kind, "version": payload["version"]}
    if kind == "blueprint":
        metadata["entity_count"] = len(payload.get("entities", []))
        metadata["tile_count"] = len(payload.get("tiles", []))
    else:
        metadata["blueprint_count"] = len(payload["blueprints"])
    return metadata


def decode(encoded: str) -> dict[str, Any]:
    """Decode a qualified blueprint string into a validated structure.

    The result keeps every field of the source document, so unknown but
    compatible fields survive for a later encoder to round-trip. No synthetic
    key is inserted into the document; use describe() for the classification.
    """
    document = decode_payload(encoded)
    classify(document)
    return document
