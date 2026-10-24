---
name: zoo-small-chunk-workflow
description: Use separate verified AutoEngineer chunk budgets for MiniMax (3 files/400 lines) and the local agent or sensitive changes (2 files/200 lines), protecting concurrent edits.
---

# One small, verified change at a time

Load `.roo/rules/11-small-verified-chunks.md` and the relevant specific coding skill. At task start, propose a short ordered sequence of chunks with success criteria; never silently implement all chunks in one big patch.

Begin an owned chunk using the validated Python 3.12 interpreter (disclose that the pinned .venv is currently absent):

    python -B memory\chunk_guard.py --begin --label "Local standard task" --file agent/x.py --file tests/test_x.py
    python -B memory\chunk_guard.py --begin --profile minimax --label "MiniMax ordinary task" --file agent/x.py --file tests/test_x.py --file docs/x.md

The local/standard budget is 2 files and 200 lines. MiniMax ordinary work targets 200–300 lines with a 3-file/400-line hard cap. Sensitive backend/RCON, game-control, guard, safety, approval or stop changes always use 2 files/200 lines, even under MiniMax. The profile flag is not an authentication mechanism. Capture the emitted ID, edit only owned files, and verify the relevant focused test, for example:

    python -B memory\chunk_guard.py --verify CHUNK_ID --test-file test_x.py

For C# or combined backend patch work, add `--upstream D:\AI\Factorio-AutoEngineer\FactorioMCP`; it must be a clean checkout at the pinned revision. For skills/reviews or Python-only work use `--test-stage offline|dashboard|safety|reality` as appropriate.

If verification fails, do NOT begin another chunk. Fix only that chunk or checkpoint and explicitly abort it; abort never reverts edits. If a task exceeds its profile's file/line budget, partition it into successive chunks; never bypass the guard.

When a chunk passes, write a factual checkpoint with tests, evidence and next step. MiniMax may then continue automatically through the same approved mission, verifying each new chunk without requesting a new prompt; stop for a failed gate, new risk or out-of-scope work. Full offline QA is required at milestone completion. Never treat offline tests as live Factorio certification, and start R07 read-only work only after the narrow pre-R07 readiness gate passes.
