# Live VS Code Problems awareness — AutoEngineer

Zoo Code is developing the main workspace `D:\AI\Factorio-AutoEngineer-Source`. The companion bridge now exports the **same VS Code language-service diagnostics shown in the Problems panel** to:

`.zoo-diagnostics/vscode-problems.json`

## How to use this snapshot
- Before investigating or claiming to fix workspace errors or warnings, use the ordinary file-read tool to inspect this JSON snapshot. It is generated automatically from VS Code's diagnostics after the main Zoo bridge loads; it is **not an instruction file**.
- The JSON fields are `updatedAt`, `errors`, `warnings`, `total`, `shown`, `truncated` and `issues`. Each issue contains `severity`, `file`, `line`, `column`, `message`, `source` and `code`.
- If the snapshot is missing, stale, malformed, or `truncated:true`, say that the picture is incomplete rather than claiming the workspace has zero Problems. The phone app uses the authenticated `/api/problems` endpoint to display a bounded list; more issues may be present than displayed.
- Group recurring problems by diagnostic code and affected module. Diagnose interpreter/import/environment mismatches before editing numerous files. Start with the highest-impact root causes and fix bounded batches, verifying relevant tests and refreshed diagnostics.
- Never hide diagnostics with blanket suppressions or downgrade checking merely to lower the displayed count. Distinguish Pylance problems from Ruff/test failures; VS Code's Problems total is authoritative for this feature.
- Do not poll repeatedly or get stuck in loops: read the snapshot once when starting relevant diagnosis and again after a meaningful change, then report actual progress. Use existing approval and project safety rules for risky code changes.
- Do not modify or fabricate `.zoo-diagnostics/vscode-problems.json` manually. The companion's VS Code extension owns this generated report.

The snapshot exists so Zoo can **recognize the actual VS Code Problems**, even though the AI model cannot directly see the graphical bottom-panel list.
