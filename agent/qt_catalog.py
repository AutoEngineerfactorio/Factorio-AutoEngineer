"""Shared, immutable recipe and research catalog snapshots for the Qt UI.

The AI Helper and the Qt dashboard must browse the same observed catalog.
This module turns the already validated ``capabilities`` envelope into a
small immutable snapshot. It does not fetch recipes, infer unlocks, or
calculate production: it only preserves the observed catalog and its
completeness state for presentation.

A missing catalog is never represented as an empty catalog that looks
complete. The snapshot keeps the catalog status, the page/total counts,
the source fingerprint and the truncation marker so the Qt workspaces can
show an explicit loading, partial, stale, or unavailable state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from qt_observation import OBSERVED, STALE, UNAVAILABLE


@dataclass(frozen=True)
class CatalogSnapshot:
    """One immutable view of an observed recipe/research catalog."""

    recipes: tuple[Mapping[str, Any], ...]
    research: tuple[str, ...]
    machines: tuple[Mapping[str, Any], ...]
    status: str
    detail: str
    state: str
    total_count: int | None
    total_pages: int | None
    page: int | None
    truncated: bool
    source_fingerprint: str | None
    game_version: str | None
    force: str | None
    surface: str | None
    tick: int | None
    excluded: tuple[Mapping[str, Any], ...] = ()

    @property
    def complete(self) -> bool:
        """Whether the observed catalog explicitly claims completeness."""
        rows = self.recipes + self.excluded
        names = [row.get("name") for row in rows]
        valid_names = all(isinstance(name, str) and name for name in names)
        return bool(
            self.status == "assembled" and self.state == OBSERVED
            and self.source_fingerprint and not self.truncated
            and self.total_count == len(rows) and valid_names
            and len(set(names)) == len(names)
        )

    @property
    def known(self) -> bool:
        """Whether a catalog was actually observed."""
        return self.state != UNAVAILABLE


def _bounded_int(value: Any) -> int | None:
    """Return a non-negative integer, or ``None`` for a missing value."""
    if type(value) is int and value >= 0:
        return value
    return None


def _bounded_text(value: Any, limit: int = 512) -> str | None:
    """Return bounded single-line text, or ``None``."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit or any(ch in text for ch in "\r\n\x00"):
        return None
    return text


def _names(value: Any, limit: int) -> tuple[str, ...]:
    """Return a bounded tuple of observed names."""
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        return ()
    names = []
    for item in value:
        name = _bounded_text(item)
        if name is not None:
            names.append(name)
    return tuple(names)


def _research_names(value: Any, limit: int) -> tuple[str, ...]:
    """Return the researched technology names.

    The mod's capability envelope carries plain names, while the backend's
    catalog page carries one row object per technology. Both spellings are
    read so the researched list is never silently empty.
    """
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        return ()
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            name = _bounded_text(item)
        elif isinstance(item, Mapping):
            name = _bounded_text(item.get("name"))
        else:
            name = None
        if name is not None:
            names.append(name)
    return tuple(names)


def _rows(value: Any, limit: int) -> tuple[Mapping[str, Any], ...]:
    """Return a bounded tuple of observed mapping rows."""
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def catalog_snapshot(frame: Mapping[str, Any] | None, *,
                     state: str = OBSERVED,
                     detail: str = "Observed catalog") -> CatalogSnapshot:
    """Build an immutable catalog snapshot from one observed frame.

    The caller owns the frame's truthfulness state. A stale frame keeps its
    observed rows but is labelled stale; an unavailable frame keeps no rows.
    """
    source = frame if isinstance(frame, Mapping) else {}
    capabilities = source.get("capabilities")
    status = source.get("catalog_status")
    capabilities = capabilities if isinstance(capabilities, Mapping) else {}
    status = status if isinstance(status, Mapping) else {}

    catalog_state = _bounded_text(status.get("status"), 64) or "unavailable"
    truncated = capabilities.get("truncated") is True
    # The backend reports the catalog totals under "total" and "page_count",
    # while the mod's own envelope reports "total_count" and "total_pages".
    # Both spellings are read so the count is never shown as unknown.
    total_count = _bounded_int(status.get("total_count"))
    if total_count is None:
        total_count = _bounded_int(status.get("total"))
    total_pages = _bounded_int(status.get("total_pages"))
    if total_pages is None:
        total_pages = _bounded_int(status.get("page_count"))
    page = _bounded_int(status.get("page"))

    if state == UNAVAILABLE or not capabilities:
        recipes: tuple[Mapping[str, Any], ...] = ()
        research: tuple[str, ...] = ()
        machines: tuple[Mapping[str, Any], ...] = ()
        if state == OBSERVED:
            state = UNAVAILABLE
            detail = "Recipe/research catalog unavailable"
        catalog_state = "unavailable"
        detail = detail or "Catalog not observed"
    else:
        recipes = _rows(capabilities.get("recipes"), 160_000)
        research = _research_names(capabilities.get("research"), 16_384)
        machines = _rows(capabilities.get("machines"), 16_384)
        if state == STALE:
            detail = detail or "Last observed catalog"

    if catalog_state == "unavailable" and state == OBSERVED:
        detail = detail or "Recipe/research catalog unavailable"

    exclusions = (_rows(capabilities.get("excluded"), 160_000)
                  if state != UNAVAILABLE else ())
    return CatalogSnapshot(
        recipes=recipes, excluded=exclusions,
        research=research,
        machines=machines,
        status=catalog_state,
        detail=detail,
        state=state,
        total_count=total_count,
        total_pages=total_pages,
        page=page,
        truncated=truncated,
        source_fingerprint=_bounded_text(capabilities.get("source_fingerprint")),
        game_version=_bounded_text(capabilities.get("game_version")),
        force=_bounded_text(capabilities.get("force")),
        surface=_bounded_text(capabilities.get("surface")),
        tick=_bounded_int(capabilities.get("tick")),
    )


def catalog_status_text(snapshot: CatalogSnapshot) -> str:
    """Return a concise, truthful status for the catalog workspace."""
    if not snapshot.known:
        return snapshot.detail
    if snapshot.state == STALE:
        return f"Stale: {snapshot.detail}"
    if snapshot.status == "assembled" and not snapshot.complete:
        note = ("planning remains unavailable" if snapshot.truncated
                else "load remaining pages before planning")
        return f"Partial catalog: {len(snapshot.recipes)} observed rows; {note}"
    if snapshot.status == "assembled":
        suffix = (f"; {len(snapshot.excluded)} explicitly unsupported"
                  if snapshot.excluded else "")
        return f"Complete observed catalog: {len(snapshot.recipes)} recipes{suffix}"
    if snapshot.status == "ok":
        page = snapshot.page if snapshot.page is not None else "?"
        pages = snapshot.total_pages if snapshot.total_pages is not None else "?"
        total = snapshot.total_count if snapshot.total_count is not None else "?"
        return f"Partial catalog page {page} of {pages} ({total} total recipes)"
    return snapshot.detail or "Catalog completeness not established"


__all__ = ["CatalogSnapshot", "catalog_snapshot", "catalog_status_text"]
