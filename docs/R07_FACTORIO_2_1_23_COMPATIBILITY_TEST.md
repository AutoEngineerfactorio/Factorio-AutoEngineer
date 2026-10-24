# R07: Factorio 2.1.23 genuine export/import compatibility test

**Status:** LEG A PREPARED, NOT EXECUTED. The disposable profile has been
created and verified; no leg has been run. Running the test requires a
separate, explicit authorisation from the human operator, because it operates
the game.

**Why this document exists.** R07-B proved a **structural** property: the
encoder emits a qualified exchange string that this codec's own R07-A decoder
accepts, and the decoded document has the same values as the input. That says
nothing about whether *Factorio* would import the blueprint. Every fixture used
so far is reconstructed from the pinned upstream reference implementation
(`FactorioMCP/Services/BlueprintCodecService.cs`), not captured from a live
2.1.23 export. This plan closes that gap — or proves it cannot be closed.

## 1. Scope and authorisation boundary

| Item | Value |
|---|---|
| Game | Factorio **2.1.23** (build 87750, win64, full) |
| Executable | `D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe` |
| Fresh disposable profile | `.local/r07-compat-2123` (**created and verified**; **not** reused from other sessions) |
| Network | Not required. The test must run with the network blocked or ignored. |
| Backend | The 12-tool restricted policy-v8 backend, read-only. **No** arbitrary Lua, **no** RCON beyond the approved read-only tools. |

**This test does not grant, use or imply any gameplay capability.** The AI
Helper must not place, ghost, wire, tile or blueprint anything. The test
below is performed by the **human operator**, using the normal game UI, and
the *Helper* only observes and compares offline afterwards.

**Authorisation required before execution:**

1. The human operator runs the export/import steps by hand in the game.
2. The operator confirms the disposable profile is disposable, and that no
   personal save is touched.
3. The operator confirms that a blueprint placed *in the disposable profile
   only* is acceptable for the import leg. If even that is not acceptable,
   stop after leg A (export only) and report the export fixture as
   sufficient for the decoder but not for importability.

**Explicitly out of scope and forbidden:** no placement by the Helper and no
gameplay command over RCON; no modification of any save outside the
disposable profile; no `git commit`, `git push`, publish or upload; no
dependency installation, credential access or model/provider change; and no
unlocking of Full Autonomy, Semi-Autonomous, R08 or Gate H1.

## 2. What the test would prove

| Leg | Action | Proves | Does **not** prove |
|---|---|---|---|
| A | Export a blueprint from the live 2.1.23 game | That the real container format matches the codec's assumption (`0` + base64(zlib-deflate(JSON))) and that the real document shape validates | That the game accepts our output |
| B | Decode the exported string with the R07-A decoder | That the decoder handles a **genuine** fixture, not only reconstructed ones | That the encoder is faithful |
| C | Encode the decoded document and re-import it into the game | That the game **accepts** our encoder's output | That the imported blueprint is semantically identical (needs leg D) |
| D | Export the imported blueprint again and compare the two strings structurally | That the game preserved what we sent | That the layout is "good" gameplay |

Leg C is the one that matters and it is the one that has never been run.
Until it passes, the encoder's output is **not** proven importable.

## 3. Leg A — capture a genuine export (human operator, in-game)

### 3.1 Operator checklist before launching the game

Complete this checklist in the disposable profile only. If any answer is
`no` or `uncertain`, do not launch Factorio; report the blocker instead.

- [ ] The executable is exactly
      `D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe`,
      and `factorio.exe --version` reports `2.1.23 (build 87750, win64, full)`.
- [ ] The profile root is exactly
      `D:\AI\Factorio-AutoEngineer-Source\.local\r07-compat-2123`. This is a
      fresh disposable profile, not `.local/live-pillow-2.1.23` and not a
      personal Factorio profile.
- [ ] No personal save directory is visible in the command line, configuration,
      or profile. Do not copy a personal save into the disposable profile.
- [ ] The exact launch command and profile path are recorded in the run log.
- [ ] The operator accepts that leg C may place a blueprint in this disposable
      profile only. If not, stop after leg A.

Do not use a save-creation or import command until the profile root above is
confirmed. Creating a new profile/save is a game operation and requires the
human operator's explicit approval.

### 3.1.1 The disposable profile is already prepared

The profile scaffolding was created by `tests/r07_compat_profile.py`. It wrote
**only** a `config.ini`, a `profile_manifest.json` and empty directories. It did
**not** launch Factorio, create a save, or touch any existing profile.

Verified state of `.local/r07-compat-2123`:

```
config.ini                 <- write-data redirected to this profile
profile_manifest.json      <- exe, paths and the exact launch command
data/saves/                <- empty; no save exists yet
fixtures/                  <- empty; the two fixture files go here
```

The generated `config.ini` redirects **all** writable game state into the
profile, so the game cannot reach the default Factorio user directory:

```ini
[path]
read-data=D:/AI/Factorio-Isolated-2.1.23/Factorio_2.1.22/data
write-data=D:/AI/Factorio-AutoEngineer-Source/.local/r07-compat-2123/data

[other]
enable-blueprint-storage-cloud-sync=false
```

`enable-blueprint-storage-cloud-sync=false` keeps the captured fixtures on the
machine. The whole `.local/` tree is gitignored, so a fixture can never be
committed by accident.

**The exact launch command.** Run this verbatim:

```
"D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe" --config "D:\AI\Factorio-AutoEngineer-Source\.local\r07-compat-2123\config.ini"
```

Do not add `--load-save`, `--start-server`, `--create` or any other argument to
that command. Launch the client with the prepared config and let the operator
create a new game from the main menu. A new game created inside this profile is
a disposable save: the profile's `write-data` is redirected, so the save lands
in `.local/r07-compat-2123/data/saves/` and nowhere else.

To rebuild the profile from scratch (destroys nothing outside this directory):

```
python -B tests/r07_compat_profile.py --reset
```

That command never launches the game and never touches another profile.

### 3.2 Capture the representative single blueprint

1. Build a small but **representative** blueprint. It should include, where
   the prototypes are available in vanilla 2.1.23:
   - a transport belt and a splitter (position and direction);
   - an assembling machine with a recipe set, a filter and an item count;
   - a container with an item and a **quality**;
   - a tile or two;
   - a **non-ASCII label** and an **emoji label** — these are the cases the
     R07-B Unicode contract cares about, and they must round-trip through
     the game;
   - if available: a circuit connection with a wire, and a train stop with a
     schedule. These two are the least certain and are the ones the plan most
     needs.
2. Export the blueprint to a string. In 2.1.23 the export dialog offers a
   string; copy it verbatim.
3. Save the string to
   `.local/r07-compat-2123/fixtures/blueprint.txt`, **inside the disposable
   profile**, never into the repository and never into a personal location.
   Preserve the exact export string; do not add a BOM or alter line endings.
4. Record the SHA-256 of the file and the byte length. A trailing newline added
   by the text editor must be disclosed in the run log and removed only from
   the value passed to the decoder, never from the captured file.

**Do not** edit the string by hand, do not re-wrap it, do not trim it. The
whole point is to capture what the game produced.

#### Recording the file's length, digest and trailing newline

Run this from the repository root. It **reads** the fixture and never modifies
it:

```
python -B -c "import hashlib,pathlib; p=pathlib.Path(r'.local/r07-compat-2123/fixtures/blueprint.txt'); b=p.read_bytes(); print('bytes='+str(len(b))); print('sha256='+hashlib.sha256(b).hexdigest()); print('trailing_newline='+str(b.endswith(b'\n'))); print('bom='+str(b.startswith(b'\xef\xbb\xbf')))"
```

Report the four printed values to the Helper. The Helper uses the byte length
and the digest to prove the fixture was not altered between capture and decode,
and the `trailing_newline` flag to decide whether the decoder input needs one
trailing byte removed — the captured file itself is never rewritten.

### 3.3 Capture a second fixture: a blueprint book

Repeat the export for a **book** containing at least two entries, with
non-contiguous indexes if the game allows it, one nested book if the game
allows it, and a non-ASCII entry label. Save it as
`.local/r07-compat-2123/fixtures/blueprint-book.txt` in the same disposable
profile and record its length and SHA-256 with the same read-only command as
above, substituting the file name.

### 3.3.1 What the operator reports back

Only these values, never the export strings themselves:

| Field | Value |
|---|---|
| `blueprint.txt` byte length | |
| `blueprint.txt` SHA-256 | |
| `blueprint.txt` trailing newline | yes / no |
| `blueprint-book.txt` byte length | |
| `blueprint-book.txt` SHA-256 | |
| `blueprint-book.txt` trailing newline | yes / no |
| entities captured / non-ASCII label / emoji label | |
| wire captured | yes / no / not available |
| schedule captured | yes / no / not available |

### 3.4 Handover contents

Hand the operator instructions to the two files and provide only the relative
names `blueprint.txt` and `blueprint-book.txt` plus their byte lengths and
SHA-256 values. Do not copy the strings into chat, source files, logs, or a
personal location. The offline legs read the two files from the disposable
profile's `fixtures/` directory and preserve their contents byte-for-byte.

## 4. Leg B — offline decode of the genuine fixture

This leg is pure offline work and can be done by the Helper once leg A has
produced the file. It is also the cheapest way to catch a format mismatch
before anyone touches the game again.

Required assertions:

1. `blueprint_codec.recognize` accepts the string and reports the prefix `0`.
2. `blueprint_codec.decode_payload` returns a JSON value without raising.
3. `blueprint_document.classify` classifies it as `blueprint` or
   `blueprint_book` — **not** an unknown top-level variant. A failure here is
   the most likely outcome and is a genuine, valuable finding: it would mean
   the R07-A document layer does not accept the real 2.1.23 shape.
4. The real `version` integer is inside `[0, 16 << 48)` and its packed
   `(major << 48) | (minor << 32) | (build << 16) | revision` decoding gives
   major 2 and minor 1. **This is the check that qualifies the fixture as a
   2.1.23 document.**
5. Every number is finite and no string carries an unpaired surrogate (the
   decoder guarantees both; on real data this confirms the game emits
   neither).
6. The document contains the members the R07-B fidelity groups assume:
   `entities` with `entity_number`, `name`, `position` (`x`, `y`),
   `direction`; and for the book, `blueprints` with `index`.

**If assertion 3 or 4 fails: stop.** Record the exact refusal reason and the
observed document shape. That is a real defect in the R07-A layer, and it
must be fixed and re-reviewed before any import leg is attempted.

## 5. Leg C — encode the genuine fixture and import it

1. Encode the decoded document with `agent.blueprint_encoder.encode_document`.
   It must succeed: the document came from the decoder, so it must be
   accepted.
2. Assert `decode(encode_document(document)) == document` by value.
3. Record the encoded string and its SHA-256.
4. Hand the encoded string to the **human operator**, who pastes it into the
   game's import dialog in the disposable profile.
5. The operator reports one of:
   - **accepted** — the blueprint appears;
   - **rejected with an error** — record the exact message;
   - **accepted but visibly wrong** — record what differs.

**A rejection is a valid and important result.** It is not a test failure to
be papered over. It means the encoder is not yet importable, and the
recorded error is the input to the next bounded fix.

## 6. Leg D — the re-export comparison

1. The operator exports the imported blueprint again.
2. Compare the leg C string and the leg D string.

The comparison must be **structural, not byte-identical**. The game may
re-serialise with its own key order, its own float formatting and its own
compression output, so the compressed bytes are *not* expected to match.
What must match is the **decoded value**: `decode(legC) == decode(legD)` for
every member the game preserves. Members the game adds or normalises (for
example a default field the game always writes) are recorded as an explicit
difference, not silently ignored. Anything the game **drops** on re-export is
a fidelity finding against the encoder: it means a field we claim to preserve
is not one the game keeps.

Report the comparison as a table of member, leg C value, leg D value, and
`preserved` / `normalised` / `dropped` / `added`.

## 7. What would count as R07-B acceptance

R07-B is accepted only when **all** of the following hold:

1. Every required R07-B encoder test passes. **This is now satisfied** — see
   `memory/SESSION_CHECKPOINT.md` for the R07-B Stage 2 record.
2. The full offline suite passes with no regression against the R07-A
   baseline, the lint checks are clean, the whitespace check is clean, the
   quick quality gate passes, and the pinned full gate is reported honestly
   (currently BLOCKED for a missing `.venv`, not passed).
3. **Leg B succeeds on a genuine 2.1.23 export** — the document layer accepts
   the real shape and the version decodes to 2.1.
4. **Leg C succeeds** — the game accepts the encoder's output in the
   disposable profile.

Until 3 and 4 hold, R07-B remains *structurally verified but importability
unproven*, and that wording must be used in every report.

## 8. Current status

**Leg A prepared; no leg executed.** The disposable profile
`.local/r07-compat-2123` has been created and its contents verified:
`config.ini`, `profile_manifest.json`, an empty `data/saves/` and an empty
`fixtures/`. The executable was confirmed to report
`2.1.23 (build 87750, win64, full)`. No Factorio process was running before or
after the preparation, no save was created or modified, no RCON command was
issued and no gameplay operation was performed.

The next bounded step is therefore a **human-authorised** one: the operator
performs leg A in the prepared disposable profile and hands over the two
fixture files. Legs B and D are offline and can follow immediately; leg C needs
the operator for the import action.

**R07-B remains structurally verified; Factorio 2.1.23 importability is
unproven.** That wording applies to every report until legs B and C both
succeed.

The risk register and the run-log template live in
`docs/R07_FACTORIO_2_1_23_COMPATIBILITY_RUNLOG.md` (its section 1 is the risk
register, its section 2 the template). The R07-B Stage 2 evidence — the
actual test counts and the verification output that back the "structurally
verified" claim in section 7 — is in `memory/SESSION_CHECKPOINT.md` under
"R07-B Stage 2".
