# AutoEngineer: Cline GitHub publication target

The only approved publication destination for this repository is the EXISTING GitHub repository:
- Remote: origin
- Repository: AutoEngineerfactorio/Factorio-AutoEngineer
- Destination branch: refs/heads/main

## Before any publish
- Coding, lint, local tests, commits, and publishing are separate actions. NEVER publish, push, merge, make a release, or deploy without explicit user approval for that publication.
- Read git status, active branch, intended commit(s), and actual diff. Confirm only intended public source is included. Never stage or publish secrets, private configuration, runtime files, model weights, saves, or private local handoff/session-memory content. A small, explicitly approved, reviewed allowlist of reusable Zoo rules, `.roomodes` definitions and quality-gate Python tools may be published only after secret scanning, tests and provenance review; see `docs/ZOO_CODE_TASK_PROTOCOL.md`.
- Check fresh remote main (git fetch origin main) before publishing. Require that the remote main tip is an ancestor of HEAD, or stop and ask for human review of divergence. Do not force-push, rewrite history, reset, or bypass branch protections.
- Preserve unfinished local work and other agents' open tasks. Do not switch active branches during Zoo's tasks simply to publish.
- Once the user authorizes the exact commit to publish, use the explicit destination: git push origin HEAD:refs/heads/main
- Verify remote main contains the published commit and report its URL, changed files, test evidence, and any unverified features. A push is NOT a live Factorio acceptance test.
- Do not publish to website-refresh or create any new remote branch. If a tool tries to publish the current feature branch automatically, stop and use the reviewed main-target workflow instead.

This document selects the destination only; it does NOT grant approval to publish or to make commits.
