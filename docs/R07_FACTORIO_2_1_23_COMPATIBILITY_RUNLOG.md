# R07: Factorio 2.1.23 compatibility test — risk register and run log

**Status:** PREPARED, NOT EXECUTED. Companion to
`docs/R07_FACTORIO_2_1_23_COMPATIBILITY_TEST.md`, which holds the test plan
itself (scope, the four legs, and the acceptance wording).

## 1. Risk register

| Risk | Mitigation |
|---|---|
| The real 2.1.23 document shape is refused by the R07-A layer | That is exactly what leg B is for. Fail closed, record the refusal, fix in a bounded chunk, re-review |
| The game rejects our encoded string for a reason we cannot see | The operator records the exact error text; the decoded leg C document is compared against the fixture to isolate the difference |
| The game silently normalises a member | Leg D turns that from invisible into a recorded `normalised` row |
| A personal save is touched | A fresh disposable profile is created for this test; the operator confirms the path before launch, and the save digest is recorded before and after |
| The Helper gains a placement capability | The Helper never places anything; every game action is the operator's, by hand, in the disposable profile |
| The test is read as R08 or Gate H1 approval | The plan's section 1 states the boundary and its section 7 the acceptance wording; R08, Gate H1, Semi-Autonomous and Fully Autonomous remain untouched |
| The game keeps running and the observation drifts | This test is a one-shot export/import, not a continuous sweep, so the tick-consistency limit found in the R04/R06 catalog work does not apply |
| The compressed output differs byte-for-byte | Expected. The comparison is structural (decoded value), not byte-identical; see plan section 6 |

## 2. Run log template

Copy this block into the run record and fill it in. Every field must be
filled from observation, never from expectation. A field that could not be
observed is written `not observed`, with the reason.

```
R07 compat test run
  date:                    operator:
  game version reported:   executable:
  disposable profile path:
  save digest before:      save digest after:
  save digest unchanged:   yes | no | not checked

  Leg A  blueprint fixture path / sha256 / bytes:
  Leg A  book fixture path / sha256 / bytes:
  Leg A  blueprint trailing newline: yes | no | not observed
  Leg A  book trailing newline:      yes | no | not observed
  Leg A  entities captured / labels non-ascii / emoji:
  Leg A  wire captured:      yes | no | not available
  Leg A  schedule captured:  yes | no | not available

  Leg B  recognize prefix:  classify result:
  Leg B  packed version decoded to:
  Leg B  refusal reason (if any):
  Leg B  member inventory:  entities / tiles / icons / filters / items /
                             quality / wires / schedule / book entries

  Leg C  encoded sha256:
  Leg C  game result:        accepted | rejected | accepted-but-different
  Leg C  exact error message (if any):
  Leg C  placed in disposable profile only: yes | no

  Leg D  summary:            preserved / normalised / dropped / added
  Leg D  member table:       <attached>

  Conclusion: importability proven | not proven | not attempted
  Next action:
```

## 3. Recording rules

1. **Observation, not inference.** If the operator did not see it, it is not
   recorded as seen. "The blueprint appeared" is an observation; "the
   blueprint was built correctly" is a claim and needs leg D.
2. **Rejections are results.** A rejected import is a valid and important
   outcome. Record the exact message. Do not retry with a modified string to
   "make it work" without a new bounded decision: a modified string is no
   longer the encoder's output and the test has changed.
3. **One run per conclusion.** A run log covers one attempt. A second attempt
   after a change gets a second log, and both are kept.
4. **The disposition of every fixture is recorded.** A fixture is either
   committed to the repository as a genuine-format regression fixture (with
   its provenance and the game version) or discarded. It is never left
   unlabelled.
5. **No personal data.** Fixture strings are game data, but a profile path or
   operator name must not be committed. Record the path relative to the
   disposable profile root.

## 4. Current status

**Leg A prepared; no leg executed.** The disposable profile
`.local/r07-compat-2123` was created and verified by
`tests/r07_compat_profile.py`. It contains only `config.ini`,
`profile_manifest.json`, an empty `data/saves/` and an empty `fixtures/`.
The executable was confirmed to report `2.1.23 (build 87750, win64, full)`.
No Factorio process was running before or after the preparation, no save was
created or modified, no RCON command was issued and no gameplay operation was
performed.

The next bounded step is **human-authorised**: the operator launches the game
with the prepared profile, performs leg A and hands over the two fixture
files. Everything after that is offline work except the import action in leg C.

## 5. Stage 3 preparation record (leg A not yet run)

This is a preparation record, not a test result. Every leg field stays empty
until the operator has acted.

```
R07 compat test run
  date:                    2026-10-25
  operator:                not observed
  game version reported:   2.1.23 (build 87750, win64, full)  [observed via --version]
  executable:              D:\AI\Factorio-Isolated-2.1.23\Factorio_2.1.22\bin\x64\factorio.exe
  disposable profile path: D:\AI\Factorio-AutoEngineer-Source\.local\r07-compat-2123
  save digest before:      not applicable - no save exists in the profile
  save digest after:       not applicable - no save exists in the profile
  save digest unchanged:   yes (no save was created)

  Leg A  blueprint fixture path / sha256 / bytes:  not observed - awaiting operator
  Leg A  book fixture path / sha256 / bytes:        not observed - awaiting operator
  Leg A  blueprint trailing newline:               not observed - awaiting operator
  Leg A  book trailing newline:                    not observed - awaiting operator
  Leg A  entities captured / labels non-ascii / emoji: not observed - awaiting operator
  Leg A  wire captured:      not observed - awaiting operator
  Leg A  schedule captured:  not observed - awaiting operator

  Leg B  recognise prefix:  not observed - leg A not run
  Leg B  classify result:   not observed - leg A not run
  Leg B  packed version decoded to: not observed - leg A not run
  Leg B  refusal reason (if any): not observed - leg A not run
  Leg B  member inventory:  not observed - leg A not run

  Leg C  encoded sha256:    not observed - leg A not run
  Leg C  game result:       not attempted
  Leg C  exact error message (if any): not applicable - leg C not attempted
  Leg C  placed in disposable profile only: not applicable - leg C not attempted

  Leg D  summary:           not attempted
  Leg D  member table:      not attempted

  Conclusion: importability not proven - leg A not run
  Next action: human operator performs leg A in the disposable profile and
               reports the two file names, byte lengths, SHA-256 values and
               trailing-newline flags.
```

### Preparation evidence observed

- `factorio.exe --version` reported `2.1.23 (build 87750, win64, full)`.
- `tests/r07_compat_profile.py` created the profile scaffolding and printed
  `NO_GAME_LAUNCHED=True` and `NO_SAVE_CREATED=True`.
- A directory listing of the profile showed only `config.ini`,
  `profile_manifest.json`, `data\saves\` and `fixtures\`. No save archive
  was present.
- `tasklist /fi "IMAGENAME eq factorio.exe"` reported no Factorio process
  before the preparation.
- The generated `config.ini` sets `write-data` to the profile's own `data`
  directory and `enable-blueprint-storage-cloud-sync=false`, so no writable
  game state and no blueprint data can reach the default Factorio user
  directory.
- `.local/` is gitignored (`.gitignore` line 55), so the captured fixtures
  cannot be committed by accident.
