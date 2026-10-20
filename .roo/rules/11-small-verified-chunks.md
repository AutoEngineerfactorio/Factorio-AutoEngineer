# Zoo Code default: one small verified chunk at a time

**Use this for ALL coding, refactoring, QA tooling, backend patch repair, test changes, rules and skills in Factorio AutoEngineer.** Small increments are the default, including when a parent task is large. Do not turn a 20-step request into a single giant tool response, script, or patch.

## Required workflow

1. **Plan without editing.** Read `git status --short --branch`, exact current files and relevant milestone acceptance. List 3–8 ordered chunks with a measurable outcome and independent test. Each chunk is a separate action, not 3–8 parallel write operations.
2. **Choose ONE chunk.** Default **1–2 files** (ideally one implementation file and its corresponding test) and **at most 120 added+removed lines**, not counting untouched context. For bigger changes, split a file by function/hunk and checkpoint between chunks. If even one chunk genuinely needs more, STOP and seek explicit user permission for a documented exception; do not silently bypass the guard.
3. **Declare ownership before edit:** run `memory/chunk_guard.py --begin --label "Specific outcome" --file agent/path.py --file tests/test_path.py` using the project's isolated Python. Copy the returned 32-character chunk ID. Existing uncommitted work is the baseline and MUST be preserved.
4. **Implement only that chunk.** Read exact snippets first, apply small targeted edits, never rewrite a giant combined C# patch, and do not touch unnamed files. If a different file is needed, stop and start a separately scoped chunk after resolving the current one.
5. **Verify before proceeding:** run `memory/chunk_guard.py --verify ID --test-file test_relevant.py` for Python or `--test-stage reality|safety|dashboard|learner|skills|offline`. C# or `.patch` work additionally requires `--upstream CLEAN_PINNED_FACTORIOMCP_PATH` and a reproducible isolated backend build. The verifier checks current syntax/JSON, sensitive staged paths, Git diff hygiene, changed-line budget and targeted tests. NEVER invent PASS.
6. **Checkpoint:** record goal, exact changed paths, diff size, tests and exit codes, blockers, next chunk in `memory/SESSION_CHECKPOINT.md` or a concise handoff. Only then begin the next chunk. At a milestone, run the full offline QA; live game is separate.
7. **On failure:** after two equivalent unsuccessful edits/tools, STOP and diagnose one root cause. Stay within the current chunk; do not repeatedly retry a large `apply_diff`, create empty `.patch.new` files, or switch to unrelated source rewrites. A failed gate keeps the file ownership lock. An abandoned session can be marked `--abort ID --reason "Checkpoint written and scope revised"` **after** saving the checkpoint; this never reverts file bytes.

## Important constraints

- This is an **opt-in local command guard**, not a magical VS Code extension hook. It only constrains work when Zoo uses it. No model, rule, or skill can guarantee the agent will obey every instruction; require a verified report and spot-check diffs.
- The guard stores local pre-edit snapshots in ignored `.local/chunk-checkpoints/`; do not upload to GitHub or include secrets. It refuses known sensitive files and duplicate active ownership.
- Do not automatically switch Gemini/ChatGPT/Qwen models, change API quotas, bypass PowerShell sandbox security, publish, touch Factorio saves, run RCON, unlock Full Autonomy, or start R07. Existing approval and safety gates still apply.
- If another agent has active edits to the same file, do not treat the chunk lock alone as proof of cross-tool ownership. Coordinate with Copilot/Zoo before changing it. Never reset/rebase/overwrite their current work.
- If the intended test is missing, first do a separate test-only chunk to create a failing regression, then implement a minimal fix in the next chunk. For C# ensure source and reproducible combined patch remain aligned.
