# Qt Dashboard Redesign — staged migration (2026-10-26)

## Decision
Migrate the Windows Tkinter dashboard incrementally to **PySide6/Qt 6**, with Qt Quick
considered for high-volume map/blueprint rendering after profiling. Preserve the
Python R06/R07/observation services and C# RCON/registered-mod-command transport.
Do not rewrite the Factorio transport or bypass the observation coordinator.

## Initial implementation
- `agent/qt_dashboard.py`: optional, dark-themed, read-only Qt UI shell.
- Header: explicit offline/snapshot/Helper state, never fake “connected”.
- Overview metrics and dedicated Overview, Map, Production, Blueprint Studio,
  Recipes & Research, Logistics and Diagnostics workspaces.
- Optional `--frame-file`: bounded local JSON frame (2 MB max), refreshed only on
  file change. No synthetic observations and **no direct Factorio polling**.
- Existing Tkinter UI remains production/default until full live acceptance.

## Migration gates
1. Install PySide6 into a project-isolated virtual environment; smoke test Qt UI.
2. Add a validated read-only adapter for existing dashboard frames. Keep the
   worker-backed observation service as **only** source of live data.
3. Replace text placeholders with map viewport/chunk renderer, cached scene
   objects, level-of-detail, and actual production/power charts.
4. Bring over recipe/research browser, inventory, AI Helper plans and R07
   blueprint editor/preview, keeping the Helper game-state read-only.
5. Verify window close, Stop/takeover controls, errors, stale frames, reconnect,
   2.1.23 vanilla + pY server/client performance and preservation of UPS.
6. Switch launcher default **only after** Qt has parity and independently
   measured no-regression results; retain a rollback path.

## Required architecture
Factorio 2.1.23 mod registered read commands → existing C# restricted backend
→ observation coordinator/cache → bounded read-only UI frames → Qt presentation.
No UI-thread RCON calls, full-catalog scans on telemetry ticks or gameplay writes
in AI Helper. Field absent means unknown, not zero.

## Validation status
Prototype source created; **not** integrated with live R09 transport, not a
replacement for production Tkinter, and not R09/H1 acceptance evidence.
