# Permanent prevention of repeated tool calls and missing-file loops

Follow on every Zoo Code task alongside rules 07, 08, 11 and 12. This is a mandatory stop condition, not optional advice.

## Tool-call deduplication
- Before any `execute_command`, `read_file`, or file search, check whether the same effective action (same command, arguments, working directory and target) has already been attempted during this task.
- If a command returns successfully, **record and reuse its result**. Repeating it without new evidence is prohibited.
- If a command returns `[]`, no match, `ENOENT`, or missing-file status, treat that as a completed negative finding. Do not repeat it and do not reinterpret a negative result as a command failure.
- A failed command may be retried **once** only after explicitly identifying and correcting a concrete cause. If the second attempt does not resolve it, stop and report the blocker without further tool calls.
- After any Zoo repetition-loop warning, stop issuing the repeating tool, summarize findings, and ask the user before starting a new execution strategy. Do not evade detection by changing shell syntax or switching from `dir` to Python.

## Package/path diagnostic example
- A missing `agent/__init__.py` is not by itself proof of a Python import problem: namespace packages and direct module imports can be valid. Check existing project imports, configured Pylance interpreter and `extraPaths` first.
- If `agent/__init__.py` is absent, record it once; if present, read it once only if its content matters. Never loop on `os.listdir('agent')`.
- For Windows PowerShell, avoid unescaped Markdown underscores/backslashes in file paths; use literal paths such as `agent/__init__.py` and PowerShell `-LiteralPath`.

## Execution and approvals
- Do not enable blanket command auto-approval, `*` allowlist entries, or unapproved execution shortcuts. Existing specific allowlisted commands remain subject to the user's safety policy.
- Prefer direct file reads and bounded searches; do not repeatedly run `cd D:`, `dir`, `python -c`, or broad diagnostics scans.
- If repeated tool invocation persists despite these instructions, classify it as an agent/tool-use failure rather than a missing dependency, stop, and report the exact action and last output.
