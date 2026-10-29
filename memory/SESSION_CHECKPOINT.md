# R10-B — Session checkpoint

**R10-B is COMPLETE.** The four missing Inventory & Logistics observation
categories are implemented, integrated, and observed live on both active
Factorio 2.1.23 profiles. The full record is in
`memory/R10_B_COMPLETION_AND_LIVE_ACCEPTANCE.md`.

## The result

| criterion | verdict |
| --- | --- |
| The four observation categories have implemented handlers | **PASS** |
| The backend and the mod protocols agree | **PASS** — the allowlist and the parser are compared as derived sets in the offline suite |
| The Qt Inventory and Logistics workspaces display real observed information | **PASS** — 8 rows on vanilla, 6 on Pyanodons |
| The pagination, the caching and the freshness handling work | **PASS** |
| The AI Helper consumes the same authoritative observation snapshot | **PASS** |
| The vanilla live acceptance passes | **PASS** |
| The Pyanodons live acceptance passes | **PASS** |
| The full regression and quality gates pass | **PASS** — 2,326 tests, Ruff, Pyright, the isolated build, the complete gate |
| The stress shows no unacceptable performance regression | **PASS** — 59.94 UPS average, 1 sample below 58, 312 working machines, 0 observer failures, 0 timeouts |
| The original saves are verified unchanged | **PASS** |
| No unapproved processes remain running | **PASS** |

## The chunks

| # | chunk id | files / lines | outcome |
| --- | --- | --- | --- |
| 1 | `b202d66be6b74d05acbe815a6ff84a8b` | 2 / 966 | the four mod-side observation handlers |
| 2 | `0d99e05d0cb742388699d606f84e1d91` | 2 / 141 | the backend allowlist and `ComposeInventory` |
| 3 | `a4ca45c53eae47faa88c9c2de505b291` | 1 / 2 | the helper-mode filter |
| 4 | `6d06e3dc5c714922aec332928018a976` | 2 / 42 | the observation request and the snapshot |
| 5 | `cc60fd858b0e49d59f82fea01cef7445` | 2 / 43 | the Qt widget, the shell routing and the bridge |
| 6 | `832176b3aa644320af383a8a377f0adc` | 2 / 345 | the AI Helper supply |
| 7 | `78cd494f8e2247a2bab5d5274994840e` | 2 / 26 | the entity filter and the whole-surface search |
| 8 | `738202e333c0453e9efd5ffd0c8189d1` | 2 / 20 | the `position` object and the mod staging for both profiles |
| 9 | `8bb39eedab9848ad853910985436a9df` | 1 / 305 | the creative stress with the R10-B observers |

Every chunk was verified with the guard: the targeted tests, the full
offline suite, the patch against the pinned upstream and the isolated
backend build.

## The four API facts that decided the design

Read out of the **official 2.1.23 offline archive** and confirmed live.
They are recorded in `memory/R10_B_API_FACTS_2123.md`.

1. `defines.inventory` has **no** generic input/output identifier, so the
   handler probes a bounded, transcribed candidate list.
2. `count_entities_filtered` **rejects an array** of types; the count is
   taken one type at a time and summed.
3. `find_entities_filtered` needs the type filter as a **set**, not a list.
4. A bare `pcall(method, receiver)` passes the receiver **twice**; every
   method call is made inside a closure.

## The two things a live run taught that the offline suite could not

* The **vanilla profile's mod was stale**: it had been installed on
  2026-10-26 and did not have the new module, so every observation
  answered `unknown_operation`. The staging now covers **both** active
  profiles.
* The **observer polling was too aggressive**. The first stress run
  polled every 5 s *and* walked 3 pages every round: 59.41 UPS average,
  4 samples below 58, 1 AI response, verdict `partial`. Polling every
  20 s and walking the pages every 120 s gives 59.94 UPS average, 1
  sample below 58, 16 AI responses, verdict **`pass`**.

## The process note

A `git checkout` of `backend-safety/backend-safety.patch` during a chunk
split removed the **uncommitted** R10-A sections from that file. They were
restored from the chunk guard's pre-edit snapshot
(`95bc1bca85ed4b93b1b4ee0d47c9816b`, 169,183 bytes) and the patch was
re-verified against the pinned upstream.

**The lesson:** the combined patch carries uncommitted work that
`git checkout` destroys. The patch is now edited **surgically** by
`tests/surgical_patch_section.py` and is never reverted.

## The standing rules

`python -B tests/sync_mod_stage.py` stages the mod into **both** active
profiles and is required before any live run.

`python -B tests/surgical_patch_section.py --check` reports the delta
between the readable backend sources and the combined patch without
writing it.

## What was not done

See section 13 of the completion document. The two that matter most: a
spatial (bounding-box) filter was not implemented, and neither test save
contains a roboport or a wagon, so the **contents** of a populated
logistic network and of a train were not observed live. The code path is
proven — the sections answer `status: ok` with a real count — but a save
with a roboport would close that gap.
