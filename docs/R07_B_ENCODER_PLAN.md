# R07-B: faithful encoder — implementation plan

**Status:** IMPLEMENTED AND OFFLINE-VERIFIED through Stage 2. The encoder
exists, the Unicode contract is repaired, and the canonical JSON, fidelity,
book and property test groups are in place. The proof is **structural**: it
says nothing about whether Factorio would import a blueprint. See section 12.

**Scope:** the R07-B encoder is a pure offline codec. It never calls the game,
never places anything, and never performs network access. It is the mirror
image of the corrected R07-A decoder.

**Prerequisite:** R07-A is implemented and verified, including the numeric
finite-value rule and the blueprint-book entry contract. Its corrected
exchange container and document rules are the contract this plan builds on.
Evidence: `memory/SESSION_CHECKPOINT.md`.

## 1. What R07-A guarantees today

The encoder must preserve everything the decoder promises:

| Property | R07-A contract |
|---|---|
| Exchange container | `"0" + base64(zlib-deflate(JSON))`, RFC 1950 |
| Game version | packed integer `(major<<48)\|(minor<<32)\|(build<<16)\|revision`, `0 <= v < 16<<48` |
| Optional members | `entities` and `tiles` may be absent |
| Top-level kinds | `blueprint` and `blueprint_book`, never both |
| Numbers | every accepted numeric value is finite; `NaN`, `Infinity`, `-Infinity` and overflowing literals such as `1e309` are refused at the parse boundary |
| Book entries | every entry is validated: an object carrying exactly one of `blueprint` / `blueprint_book` plus a non-negative integer `index` |
| Nested books | accepted and validated recursively, bounded by `MAX_BOOK_DEPTH` |
| Unknown fields | preserved verbatim, never injected, never dropped |
| Classification | returned separately by `describe()`, never as `_decoded_kind` |
| Bounds | 4 MiB encoded / 2 MiB compressed / 8 MiB decoded / depth 64 / 20000 items / 20000 book entries / 8 book depths |

## 2. Encoder goals

1. **Deterministic round-trip.** `decode(encode(decode(s)))` equals
   `decode(s)` by value for every accepted `s`. The assertion is on the
   *decoded document*, not on the encoded bytes: byte-identical output is a
   bonus, not the contract, because zlib output depends on the compressor
   settings.
2. **Stable encoding.** For a fixed compressor configuration,
   `encode(decode(s))` is a pure function of the decoded document: encoding
   the same decoded document twice yields the same string, and
   `encode(decode(encode(decode(s)))) == encode(decode(s))`.
   This is the determinism property; the earlier `encode(encode(d))` form was
   a type error, because `encode` takes a *document* and returns a *string*,
   so the inner `encode(d)` was a string that the outer `encode` could not
   accept.
3. **Lossless for unknown data.** No field the decoder accepts may be
   dropped, reordered in a lossy way, or type-coerced.
4. **Fail closed.** An encoder never emits a document the R07-A decoder would
   refuse. The encoder validates through the same document layer before
   writing.

## 3. Non-goals for R07-B

- No blueprint *generation* or design optimisation (R08 preview work).
- No library, revisions, provenance or checksums (R07-C).
- No material bills, prototype checks or buildability claims (R07-D).
- No modification of decoded documents except through an explicit, tested
  edit API that preserves unknown fields.
- No support for upgrade/deconstruction planners or parameterised blueprints
  until they are separately qualified.

## 4. Proposed module surface

New file `agent/blueprint_encoder.py`, mirroring `agent/blueprint_codec.py`:

- `encode_document(document)` - the only public encoding entry point. It
  validates the document through the document layer and then emits a qualified
  exchange string.
- `canonical_json(document)` - deterministic JSON text: sorted keys, compact
  separators, UTF-8. This is an **internal** helper, not a public API.
- `round_trip(encoded)` - decode then encode, for tests and revision tooling.

**No public encoding API may bypass validation or the size limits.** The
earlier draft proposed a public `encode_json(document)` that emitted without
validating against the document layer; that is withdrawn. A public escape
hatch would let a caller emit a document the R07-A decoder refuses, and would
break the fail-closed goal in section 2. Consequently:

- There is exactly one public function that produces an exchange string, and
  it always validates first.
- `canonical_json` is module-private (`_canonical_json`) or is clearly marked
  internal and is not re-exported from the package surface.
- Every path that writes bytes applies the encoder's own size checks against
  the same bounds constants as the decoder, so an encoder can never emit a
  string the decoder would reject for size.

The encoder must reuse `agent/blueprint_document.py` for validation and the
*same* bounds constants from `agent/blueprint_codec.py` rather than declaring
its own.

## 5. Canonical JSON rules

- Keys sorted by Unicode code point, recursively.
- Compact separators (`,` and `:`), no spaces.
- `ensure_ascii=False`, UTF-8 output, matching the game's own output shape.
- **Strict finite-number serialization.** The serializer must be configured so
  that a non-finite number can never reach the output. Concretely:
  `allow_nan=False`, so a float infinity or NaN raises rather than being
  written as the bare tokens `Infinity` / `NaN`, which are not JSON. The
  encoder also walks the document and refuses any non-finite float itself,
  because `allow_nan=False` alone only guards the JSON text and not the
  document that the caller handed in.
- The decoder already refuses `NaN`, `Infinity`, `-Infinity` and overflowing
  literals such as `1e309`, so a decoded document cannot contain a non-finite
  number. The encoder's own check is a second, independent barrier: it also
  covers a document that never came from the decoder.
- Floats: preserved exactly as decoded. Float formatting must be round-trip
  stable — this is a known risk area and needs a dedicated test. Negative zero
  must survive as negative zero.
- Integers stay integers; the packed game version must never become a float
  (`562949954076672` is exactly representable, but the encoder must still
  emit it as an integer token).
- Duplicate keys are impossible in a Python `dict`, so the encoder inherits
  the decoder's guarantee.
- **Malformed Unicode is refused, never repaired.** The JSON grammar permits
  `\uD800`-`\uDFFF` escapes, but a lone surrogate has no UTF-8
  representation: the game can never emit one and Python refuses to encode
  one. Such a document is refused with `BlueprintError` at the decode
  boundary and again at the encode boundary. The text is never silently
  replaced with U+FFFD and never discarded, because the game would then
  import a different blueprint than the one that was exported. A *valid*
  surrogate pair such as `\uD83D\uDE00` decodes to a single astral code
  point and is preserved normally.

## 6. Fidelity areas that need explicit coverage

Each of these is a separate test group. A round-trip that "looks the same"
is not enough; the assertion must be on exact values.

### 6.1 Blueprint books
- Entry `index` values preserved, including gaps and out-of-order indexes.
- Entry order in the list preserved.
- `active_index` preserved.
- Nested books are **accepted** by the document layer and validated
  recursively under `MAX_BOOK_DEPTH`. An earlier draft of this plan claimed
  they were refused; that was inaccurate. The correction is that nested books
  are in scope, so R07-B must preserve the nesting exactly: it must not
  flatten a nested book, rename it, or drop the nested entry list. A book
  nested beyond the depth bound must still be refused by the encoder, exactly
  as the decoder refuses it.
- Every book entry is validated: an object carrying exactly one of
  `blueprint` / `blueprint_book` plus a non-negative integer `index`. The
  encoder must refuse a malformed entry rather than emit it.

### 6.2 Entities
- `entity_number` preserved exactly and not renumbered.
- `position` `x`/`y` preserved exactly, including negative and fractional
  values and the `-0.0` edge case.
- `direction` preserved as the integer the game uses (0/2/4/.../14).
- `recipe` and `name` preserved. Unknown entity members preserved verbatim.

### 6.3 Wires and circuits
- The `wires` member on an entity is a nested list of endpoint pairs. It must
  survive unchanged, including ordering.
- Circuit network identifiers, connection points and signal ids are preserved
  as opaque values, not interpreted.
- The encoder must not renumber or validate wire endpoints in R07-B. The
  earlier draft justified this with the claim that "a wire may legitimately
  reference an entity in another book". **That claim is not backed by
  verified evidence** and is withdrawn as a justification. The encoder's
  position does not change: it treats wire endpoints as opaque and does not
  renumber or resolve them, because resolving them would require game
  semantics the offline codec does not have. But the reason is the absence of
  semantics, not an assumption that cross-entry references are legal.
- Cross-entry wire references must not be assumed to exist, and must not be
  assumed to be impossible either. Until a genuine exported fixture shows a
  wire crossing a book-entry boundary, the encoder neither creates nor
  forbids such a reference, and no test asserts one is valid.
- If a future fixture does show a wire crossing entries, the encoder still
  preserves it verbatim; only the *interpretation* stays out of scope.

### 6.4 Quality
- Quality is an opaque id in entity/item members. Preserve it exactly.
- Do not map quality ids to names and back. That is catalog-dependent and
  belongs to R07-D, where a qualified catalog exists.

### 6.5 Schedules
- Train schedules are lists of records with `wait_time`, `station`,
  `record_type` and route records. Preserve the whole structure verbatim.
- Do not normalise times or reorder stations.

### 6.6 Items, icons, tiles and unknown members
- `items`, `icons`, `tiles`, `label`, `label_color` and metadata members are
  preserved.
- Any member the decoder did not know about must still survive, because the
  decoder preserves it.

## 7. Determinism and normalisation policy

Normalise **only** what is proven safe:

- JSON key ordering and separator whitespace: safe, because JSON object
  member order is not semantically meaningful and the game does not rely on
  it.
- Nothing else, in R07-B.

Explicitly **not** normalised in R07-B: float formatting, entity ordering,
book entry ordering, `entity_number` assignment, `index` assignment,
`direction` encoding, or any field pruning.

The test suite must prove this by asserting that a document with unusual but
valid ordering and numbering round-trips to the *same values*, not merely to
an equivalent blueprint.

## 8. Proposed chunk sequence

Each chunk: at most two files, at most 120 changed lines (hard cap 200),
a chunk-guard verification with focused tests, and a checkpoint.

1. **Encoder skeleton** — `agent/blueprint_encoder.py` with a private
   `_canonical_json` and a zlib/base64 writer that reuses the decoder's
   bounds. Tests: encoder emits a string the R07-A decoder accepts.
2. **Canonical JSON** — sorted keys, compact separators, UTF-8, integer
   preservation, `allow_nan=False`. Tests: golden JSON text for a fixed
   document; float and large-integer stability; negative zero preserved.
3. **Validation integration** — `encode_document` routes through
   `blueprint_document.classify`. Tests: an invalid document is refused
   before any bytes are written; the module exposes no public function that
   skips validation or the size limits; a document containing `inf` or `nan`
   is refused.
4. **Blueprint round-trip** — entity fidelity, positions, directions,
   recipes, unknown members. Tests: decode -> encode -> decode equality on
   value, for the genuine-format fixtures.
5. **Book round-trip** — indexes, order, `active_index`, nested-book
   preservation. Tests: the same, plus the explicit refusal case for a
   malformed entry and for a nesting depth beyond `MAX_BOOK_DEPTH`.
6. **Wires, circuits, quality, schedules** — opaque preservation groups.
   Tests: exact equality on each group.
7. **Round-trip property harness** — a generated-document sweep asserting
   `decode(encode(decode(s)))` equals `decode(s)` for a family of documents
   exercising the fidelity areas, and that `encode(decode(s))` is stable for a
   fixed compressor configuration.
8. **Fail-closed and bounds tests** — the encoder refuses oversized output,
   unsupported documents, non-finite numbers and non-serialisable values, and
   never emits a string the decoder would reject. There must be no public
   entry point that skips validation or the size limits.

## 9. Acceptance criteria for R07-B

- Every chunk verified by the chunk guard within the line budget.
- Focused encoder tests pass; the full offline suite passes with no
  regressions against the R07-A baseline of 546 tests.
- Ruff clean; `git diff --check` clean; quick code-quality gate PASS.
- The pinned full code-quality gate stays BLOCKED (missing `.venv`) and is
  reported as such, not as a pass.
- Round-trip proof is **structural**. It must be labelled as such. A
  structural proof means: the encoder emits a string that this codec's own
  decoder accepts, and the decoded document has the same values. It says
  nothing about whether the game would accept the blueprint.
- Importability into a real Factorio version is **not** claimed by R07-B. It
  requires a real exported game fixture and a separately authorised read-only
  compatibility check. Structural fidelity and game importability are two
  different claims and must never be reported as one.
- The encoder emits no `NaN` and no `Infinity`, and the encoder's own
  validation refuses a document that contains one.
- Report capabilities and unsupported structures separately.

## 10. Evidence still needed before R07-B can claim real-world correctness

- A blueprint string exported by a real Factorio 2.1.23 session, captured
  read-only, to serve as a genuine-format fixture. The current R07-A
  fixtures are reconstructed from the pinned upstream reference
  implementation, not captured from a live export. R07-B round-trips should
  be re-run against such a fixture once it exists.
- Evidence about wire endpoints that cross a blueprint-book entry boundary.
  Until a genuine fixture shows one, the encoder treats wire endpoints as
  opaque and no test asserts that a cross-entry reference is valid.
- An independently reviewed R07-A diff.

## 11. Blocked and out of scope

R07-C (private revisions), R07-D (read-only preview and preflight),
catalog-dependent material bills and buildability validation, R08 physical
placement, Gate H1, Semi-Autonomous and Fully Autonomous all remain behind
their own gates. R07-D catalog-dependent work stays blocked until complete,
qualified catalog evidence is available.

## 12. Stage 2 outcome — what is now implemented and verified

### The Unicode defect and its repair

An independent review reproduced that a container holding an escaped lone
surrogate such as `\ud800` was accepted by the decoder and then raised
`UnicodeEncodeError` — an uncontrolled exception — inside
`encode_document()`. A valid surrogate pair round-tripped correctly.

The repair puts the rule at **both** boundaries:

- the decoder refuses the document at the parse boundary, because a lone
  surrogate has no UTF-8 representation and the game can never emit one;
- the encoder refuses it again before writing any byte, because a caller can
  hand it a Python string directly, never via the decoder.

The text is never silently replaced with U+FFFD and never discarded, because
the game would then import a different blueprint than the one that was
exported. Valid source data is preserved exactly by value.

The regression tests were **proven to fail without the fix**: with the fix
reverted in place, 9 of the 13 Unicode tests failed; with the fix restored,
all 13 passed.

### Test coverage added in Stage 2

| Area | File | Tests |
|---|---|---|
| Unicode contract | `tests/test_blueprint_unicode.py` | 16 |
| Canonical JSON golden bytes | `tests/test_blueprint_canonical_json.py` | 17 |
| Entity fidelity | `tests/test_blueprint_fidelity.py` | 13 |
| Opaque-value fidelity (recipes, filters, items, quality, icons, tiles, labels, wires, circuits, schedules, stations, unknown members) | `tests/test_blueprint_fidelity_opaque.py` | 19 |
| Blueprint-book fidelity | `tests/test_blueprint_book_fidelity.py` | 15 |
| Property and security | `tests/test_blueprint_properties.py` | 16 |
| Encoder size limits | `tests/test_blueprint_encoder_limits.py` | 5 |
| Seeded generator and coverage self-check | `tests/blueprint_property_fixtures.py` | (helper) |

The canonical JSON golden strings are the **observed** encoder output,
captured by running the encoder, not a guess.

### Two expectations of mine were corrected against observed behaviour

1. **The compressed-size limit.** A 2 MiB repeated filler compresses to
   2108 bytes, and even base-62 random text compresses to 1 580 330 bytes,
   because deflate encodes a 62-symbol alphabet below eight bits per
   character. The encoder was right and the test was wrong. The limit is now
   driven with the full Unicode range, and the counterpart test asserts that a
   large but *compressible* document is **accepted**, because the decoder
   accepts it too.
2. **The public-surface sweep.** A first version iterated over every public
   name in the module, including imported names such as `BlueprintError`,
   which are not encoding APIs. It now filters by `__module__`.

### Verification (actual output)

- focused blueprint run -> **Ran 208 tests, OK** (was 105 before Stage 2)
- full offline suite -> **Ran 710 tests, FAILED (failures=1)**. The one
  failure is a dashboard catalog-paging test with no blueprint code in it;
  its cause is a concurrent one-line edit by another writer in
  `agent/dashboard_observer.py` that removed an `await`. That file was not
  touched by this work.
- `python -m ruff check agent tests memory` -> All checks passed!
- `git diff --check` -> clean on every R07 file
- quick code-quality gate -> PASS
- pinned full code-quality gate -> **BLOCKED** (missing pinned `.venv`)

### What is still NOT claimed

Importability into Factorio. No game-exported blueprint string has been
decoded or encoded. Every fixture is reconstructed from the pinned upstream
reference implementation, not captured from a live 2.1.23 export. The
single largest outstanding gap is therefore a genuine exported fixture, and
the round-trip proof must be re-run against it.

Entity-level validation (prototype names, numeric types, wire endpoint
references) is preserved verbatim but not validated: the offline codec has no
catalog and no game semantics. That is R07-D work.

The book depth bound (8), the entry bound (20000) and the JSON depth bound
(64) are defensive limits chosen by this codec, not values verified against
the game.
