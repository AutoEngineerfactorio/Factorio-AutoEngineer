"""R07-B: faithful, offline-only Factorio blueprint encoder.

The mirror image of the R07-A decoder in ``agent/blueprint_codec.py``. It turns
a validated blueprint or blueprint-book document into a qualified Factorio
exchange string: the versioned prefix ``0`` followed by base64 of a
zlib-deflated JSON document.

It never calls the game, never places anything and never performs network
access. It is a pure offline codec.

Public surface
--------------
Exactly one public function produces an exchange string:

``encode_document(document)``

It always validates first, through the same document layer the decoder uses,
and always applies the same size bounds. There is deliberately no public
escape hatch that emits an unvalidated document, because such a path could
produce a string the R07-A decoder refuses, which would break the fail-closed
contract.

Canonical JSON
--------------
The JSON text is deterministic:

* object keys sorted by Unicode code point, recursively;
* compact separators (``,`` and ``:``) with no whitespace;
* ``ensure_ascii=False`` so the text is UTF-8, matching the game's own shape;
* ``allow_nan=False`` so a non-finite number can never reach the output as the
  bare token ``NaN`` or ``Infinity``, which are not JSON.

Sorting keys and removing separator whitespace are the only normalisations
performed. Nothing else is normalised: float formatting, entity order, book
entry order, ``entity_number`` assignment, ``index`` assignment, ``direction``
encoding and field pruning are all left exactly as the caller supplied them.

The encoder also walks the document itself and refuses a non-finite float
before serialising. ``allow_nan=False`` alone only guards the JSON text; this
independent check also covers a document that never came from the decoder.
"""
from __future__ import annotations

import base64
import json
import math
import zlib
from typing import Any, NoReturn

from blueprint_codec import (
    MAX_COMPRESSED_BYTES,
    MAX_DECOMPRESSED_BYTES,
    MAX_ENCODED_CHARS,
    BlueprintError,
    check_text_unicode,
)
from blueprint_document import classify

# The only exchange prefix the game emits, and the only one the decoder
# accepts: "0" + base64(zlib-deflate(JSON)).
EXCHANGE_PREFIX = "0"

# The compressor configuration is fixed so that encoding the same document
# twice yields the same string. Level 9 is chosen because it is a fixed,
# explicit setting: the game does not depend on a particular compressed byte
# sequence, only on the decompressed JSON, but a fixed configuration keeps the
# encoder a pure function of the document.
_COMPRESSION_LEVEL = 9


def _fail(message: str) -> NoReturn:
    raise BlueprintError(message)


def _check_document(value: Any) -> None:
    """Refuse a document that cannot be represented faithfully.

    Three independent barriers are applied here, all before any bytes are
    produced:

    * a non-finite float, which ``json.dumps(..., allow_nan=False)`` would
      also refuse but only at serialisation time and with a generic message;
    * a non-text object key, which JSON cannot represent at all;
    * an unpaired Unicode surrogate, which has no UTF-8 encoding. Python
      would raise ``UnicodeEncodeError`` from the ``encode("utf-8")`` call
      below, which is an uncontrolled exception rather than a refusal. The
      document is refused with an explicit reason instead, and the text is
      never silently replaced or discarded.

    The walk is iterative so a hostile document cannot use this check to
    exhaust the interpreter stack.
    """
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, float):
            if not math.isfinite(item):
                _fail("Blueprint document contains a non-finite number")
        elif isinstance(item, str):
            check_text_unicode(item, "Blueprint document")
        elif isinstance(item, dict):
            for key, member in item.items():
                if not isinstance(key, str):
                    _fail("Blueprint document has a non-text object key")
                check_text_unicode(key, "Blueprint document")
                stack.append(member)
        elif isinstance(item, list):
            stack.extend(item)


def _canonical_json(document: Any) -> str:
    """Return the deterministic JSON text for a document.

    Module-private on purpose. This helper does not validate the document and
    does not apply the size bounds, so it must not be reachable as a public
    API that emits an exchange string.
    """
    try:
        return json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except RecursionError:
        _fail("Blueprint document is nested too deeply")
    except ValueError as exc:
        _fail(f"Blueprint document is not serialisable as JSON: {exc}")
    except TypeError as exc:
        _fail(f"Blueprint document is not serialisable as JSON: {exc}")


def encode_document(document: Any) -> str:
    """Encode a validated blueprint document into a Factorio exchange string.

    The document is validated through ``blueprint_document.classify`` first, so
    a malformed document, an unsupported top-level variant or an out-of-range
    game version is refused before any bytes are written. The emitted string
    respects the decoder's own bounds, so the decoder is guaranteed to accept
    it.

    Raises ``BlueprintError`` for a refused document.
    """
    classify(document)
    _check_document(document)
    text = _canonical_json(document)
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        # Defensive: _check_document already refuses an unpaired surrogate, so
        # this is unreachable for a plain dict/list/str document. It exists so
        # that no code path can raise an uncontrolled UnicodeEncodeError out
        # of the public API.
        _fail(f"Blueprint document contains text that is not valid UTF-8: {exc}")
    if len(raw) > MAX_DECOMPRESSED_BYTES:
        _fail("Blueprint document exceeds the decoded size limit")
    compressed = zlib.compress(raw, _COMPRESSION_LEVEL)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        _fail("Blueprint document exceeds the compressed byte limit")
    encoded = EXCHANGE_PREFIX + base64.b64encode(compressed).decode("ascii")
    if len(encoded) > MAX_ENCODED_CHARS:
        _fail("Blueprint document exceeds the encoded length limit")
    return encoded
