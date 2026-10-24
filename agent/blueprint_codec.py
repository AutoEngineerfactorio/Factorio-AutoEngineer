"""R07-A: bounded, offline-only Factorio blueprint exchange container.

Decodes the exchange container of a Factorio blueprint string: a versioned
prefix, base64 and a zlib-deflated JSON document. It never performs network
access, never calls the game, and never places anything. Every step is bounded
so hostile input cannot exhaust memory, CPU or the JSON parser.

The exchange format is a versioned prefix followed by base64 of a zlib-deflated
JSON document. The prefix is a single character and ``0`` is the only format the
game emits:

  ``0``   base64(zlib-deflate(JSON)) -- the current game format

Anything else is refused rather than guessed. An uncompressed ("stored")
payload is not a documented Factorio exchange format. The prefix is one
character, so it is never confused with the base64 payload that follows.

Format evidence (read-only, offline): the pinned upstream
``FactorioMCP/Services/BlueprintCodecService.cs`` states "Blueprint format:
version char ('0') + base64(zlib-deflate(JSON))" and refuses any other first
character as ``invalid_version``; ``LuaHelpers.encode_string`` is documented as
"Deflates and base64 encodes the given string".

JSON is parsed strictly: duplicate object keys, NaN and Infinity are refused
rather than silently accepted, because the game never emits them and a
last-one-wins parser would hide a hostile or corrupted document.

Numeric overflow is refused at the same boundary. The literals ``NaN`` and
``Infinity`` are rejected by ``parse_constant``, but a plain numeric literal
such as ``1e309`` is not a constant: the JSON parser converts it to a float that
overflows to infinity. Every accepted numeric value must therefore be finite,
otherwise a later encoder would have to serialise an infinity that the game
cannot represent. Negative zero is a finite value and is preserved.

Malformed Unicode is refused at the same boundary. The JSON grammar permits
``\\uD800``-``\\uDFFF`` escapes, but a lone surrogate has no UTF-8
representation: the game can never emit one, and Python refuses to encode
one. Such a document is refused with an explicit reason rather than accepted
and later failing inside an encoder with an uncontrolled
``UnicodeEncodeError``. A *valid* surrogate pair such as ``\\uD83D\\uDE00``
decodes to a single astral code point and is preserved normally. The
surrogate text is never silently replaced with U+FFFD and never discarded,
because the game would then import a different blueprint than the one that
was exported.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import zlib
from typing import Any, NoReturn

# Independent container bounds. A hostile payload must fail on one of these.
MAX_ENCODED_CHARS = 4 * 1024 * 1024
MAX_COMPRESSED_BYTES = 2 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 8 * 1024 * 1024

# Versioned prefixes this decoder accepts. The prefix is one character.
PREFIXES = {"0": "zlib"}


class BlueprintError(ValueError):
    """The blueprint string was refused. The reason is explicit."""


def _fail(message: str) -> NoReturn:
    raise BlueprintError(message)


def recognize(encoded: str) -> tuple[str, str]:
    """Return (prefix, container) for a blueprint string.

    Raises BlueprintError for anything that is not a qualified, versioned
    Factorio blueprint exchange string.
    """
    if not isinstance(encoded, str):
        _fail("Blueprint string must be text")
    if not encoded:
        _fail("Blueprint string is empty")
    if len(encoded) > MAX_ENCODED_CHARS:
        _fail("Blueprint string exceeds the encoded length limit")
    if encoded != encoded.strip():
        # Leading or trailing whitespace is not part of the exchange format.
        _fail("Blueprint string has surrounding whitespace")
    prefix = encoded[0]
    if prefix not in PREFIXES:
        _fail(f"Unsupported blueprint string prefix {prefix!r}")
    if len(encoded) < 2:
        _fail("Blueprint string has no payload")
    return prefix, PREFIXES[prefix]


def _decode_base64(body: str) -> bytes:
    # validate=True rejects any character outside the base64 alphabet, which
    # also rejects embedded whitespace and newlines.
    try:
        raw = base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError) as exc:
        _fail(f"Blueprint payload is not valid base64: {exc}")
    if not raw:
        _fail("Blueprint payload is empty")
    if len(raw) > MAX_COMPRESSED_BYTES:
        _fail("Blueprint payload exceeds the compressed byte limit")
    return raw


def _decompress(raw: bytes) -> bytes:
    # A bounded decompress object refuses to produce more than the limit.
    decompressor = zlib.decompressobj()
    try:
        # max_length bounds the output; the flush is bounded by the same value.
        data = decompressor.decompress(raw, MAX_DECOMPRESSED_BYTES)
        if decompressor.unconsumed_tail:
            _fail("Blueprint payload expands beyond the decoded size limit")
        data += decompressor.flush(MAX_DECOMPRESSED_BYTES - len(data) + 1)
    except zlib.error as exc:
        _fail(f"Blueprint payload is not valid deflate data: {exc}")
    if len(data) > MAX_DECOMPRESSED_BYTES:
        _fail("Blueprint payload expands beyond the decoded size limit")
    if not decompressor.eof:
        _fail("Blueprint payload is truncated")
    if decompressor.unused_data:
        _fail("Blueprint payload has trailing bytes")
    return data


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _value in pairs:
        if key in seen:
            _fail(f"Blueprint JSON has a duplicate key {key!r}")
        seen.add(key)
    return dict(pairs)


def _reject_constant(name: str) -> Any:
    _fail(f"Blueprint JSON contains the non-finite number {name}")


def _parse_finite_float(text: str) -> float:
    """Parse a JSON number and refuse it if it is not finite.

    ``parse_constant`` only sees the non-standard literals ``NaN``, ``Infinity``
    and ``-Infinity``. A standard numeric literal can still overflow: ``1e309``
    converts to ``inf`` and ``-1e309`` to ``-inf``. Such a value is refused here
    so that every number reaching the document layer is finite and can never
    become an unrepresentable ``NaN`` or ``Infinity`` in encoder output.
    """
    value = float(text)
    if not math.isfinite(value):
        _fail(f"Blueprint JSON contains the non-finite number {text}")
    return value


def _has_unpaired_surrogate(text: str) -> bool:
    """Return True when ``text`` holds a surrogate code point with no partner.

    JSON permits ``\\uD800``-``\\uDFFF`` escapes syntactically, but a lone
    surrogate has no UTF-8 representation, so the game can never emit one and
    Python refuses to encode one. A *valid* pair such as ``\\uD83D\\uDE00``
    decodes to a single astral code point and is therefore not reported.
    """
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if "\ud800" <= char <= "\udbff":
            # A high surrogate must be followed by a low surrogate.
            if index + 1 >= length:
                return True
            following = text[index + 1]
            if not ("\udc00" <= following <= "\udfff"):
                return True
            # A valid pair: consume both code points.
            index += 2
            continue
        if "\udc00" <= char <= "\udfff":
            # A low surrogate reached on its own has no high partner.
            return True
        index += 1
    return False


def check_text_unicode(text: Any, where: str = "Blueprint") -> None:
    """Refuse text that carries an unpaired Unicode surrogate.

    This is a shared primitive so that the decoder and the encoder apply the
    identical rule and cannot drift apart. Malformed Unicode is *refused*; it
    is never silently replaced with U+FFFD and never discarded, because the
    game would import a different blueprint than the one that was exported.

    A non-text argument is refused as well, rather than raising an
    uncontrolled ``TypeError`` or ``KeyError`` from the scan.
    """
    if not isinstance(text, str):
        _fail(f"{where} text must be a string, got {type(text).__name__}")
    if _has_unpaired_surrogate(text):
        _fail(f"{where} contains an unpaired Unicode surrogate")


def _parse_json(text: str) -> Any:
    """Parse JSON strictly: no duplicate keys, no NaN, no Infinity."""
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
        )
    except BlueprintError:
        raise
    except RecursionError:
        # The JSON scanner recurses once per nesting level, so a deeply nested
        # payload exhausts the interpreter stack before the document layer can
        # apply its own depth bound. The failure is a refusal, not a crash.
        _fail("Blueprint payload is nested too deeply")
    except ValueError as exc:
        _fail(f"Blueprint payload is not valid JSON: {exc}")
    _check_text_unicode(document)
    return document


def _check_text_unicode(value: Any, where: str = "Blueprint") -> None:
    """Refuse any unpaired surrogate inside a decoded JSON value.

    Applied to every string in the document, including object keys, because a
    key is text too. The walk is iterative so a hostile document cannot use
    this check to exhaust the interpreter stack.
    """
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            check_text_unicode(item, where)
        elif isinstance(item, dict):
            for key, member in item.items():
                check_text_unicode(key, where)
                stack.append(member)
        elif isinstance(item, list):
            stack.extend(item)


def decode_payload(encoded: str) -> Any:
    """Decode a qualified blueprint string into a bounded JSON value.

    The value is not interpreted yet; use agent/blueprint_document.py to
    recognize and validate the blueprint or blueprint book structure.
    """
    recognize(encoded)
    raw = _decode_base64(encoded[1:])
    data = _decompress(raw)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        _fail(f"Blueprint payload is not valid UTF-8: {exc}")
    return _parse_json(text)
