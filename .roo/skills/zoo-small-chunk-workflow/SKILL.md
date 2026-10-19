---
name: zoo-small-chunk-workflow
description: Break all AutoEngineer Zoo coding and documentation tasks into one or two files and at most 120 changed lines per verified, checkpointed step, stopping retry loops and preserving unfinished Copilot edits.
---

# One small, verified change at a time

Load `.roo/rules/11-small-verified-chunks.md` and the relevant specific coding skill. At task start, propose a short ordered sequence of chunks with success criteria; never silently implement all chunks in one big patch.

Begin an owned chunk using the existing isolated interpreter:

    .\.venv\Scripts\python.exe -B memory\chunk_guard.py --begin --label "Bounded result" --file agent/x.py --file tests/test_x.py

Capture the emitted ID. Edit only those files and no more than 120 changed lines total. Verify with the relevant targeted test, for example:

    .\.venv\Scripts\python.exe -B memory\chunk_guard.py --verify CHUNK_ID --test-file test_x.py

For C# or combined backend patch work, add `--upstream D:\AI\Factorio-AutoEngineer\FactorioMCP`; it must be a clean checkout at the pinned revision. For skills/reviews or Python-only work use `--test-stage skills|learner|reality|offline` as appropriate.

If verification fails, do NOT begin another chunk. Fix only that chunk or checkpoint and explicitly abort it; abort never reverts edits. If a task requires touching more than two files, partition into successive chunks rather than widening one operation.

When a chunk passes, write a factual checkpoint with tests, evidence and next step. Full offline QA is required at milestone completion. Never treat offline tests as live Factorio certification, and keep R07 on hold.
