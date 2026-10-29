"""Bounded multi-page assembly of the observed recipe/research catalog.

The game exposes the recipe and machine catalog **one page at a time**. A
large modpack such as Pyanodons has thousands of recipes, so the dashboard
needs a way to walk the pages and present one assembled catalog.

This module owns that assembly. It has three rules:

* **Bounded.** A page request is bounded by the page size and the number of
  pages. The assembler never asks for an unbounded number of pages and never
  keeps more than :data:`MAX_CACHED_PAGES` pages in memory.
* **Cached.** A page that was already fetched for the same catalog
  fingerprint is reused. A repeated request for the same page costs no
  backend round trip.
* **Honest.** The assembled catalog reports exactly how many pages were
  loaded, how many rows were seen, and whether the result is complete. A
  partially assembled catalog is never presented as a complete one, and the
  assembler never invents a row, an unlock or a count.

The module is deliberately free of any Qt, Factorio or transport import, so
the whole assembly path is verifiable offline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from qt_catalog import CatalogSnapshot, catalog_snapshot

#: The largest page size the assembler will request in one call.
MAX_PAGE_SIZE = 128

#: The largest number of pages the assembler will hold in its cache.
MAX_CACHED_PAGES = 1024

#: The largest number of pages the assembler will walk in one assembly run.
MAX_PAGES_PER_RUN = 1024

def _bounded_cached_pages(value: Any) -> int:
    """Return the number of pages the cache may hold.

    The bound comes from the settings when the caller does not give one.
    A missing or unsafe value falls back to the protective default, so the
    cache can never become unbounded because of a setting.
    """
    if value is not None:
        if type(value) is not int:
            return MAX_CACHED_PAGES
        return max(1, min(value, MAX_CACHED_PAGES))
    try:
        from cache_context import limits

        entries, _ = limits()
    except Exception:
        return MAX_CACHED_PAGES
    # One page is one cache entry. The configured entry budget bounds the
    # pages that are held in memory.
    return max(1, min(entries, MAX_CACHED_PAGES))


#: The largest number of assembled rows the assembler will retain.
MAX_ASSEMBLED_ROWS = 160_000


def _bounded_int(value: Any) -> int | None:
    """Return a non-negative integer, or ``None`` for a missing value."""
    if type(value) is int and value >= 0:
        return value
    return None


@dataclass(frozen=True)
class CatalogPage:
    """One fetched catalog page and the counts the game reported with it."""

    page: int
    recipes: tuple[Mapping[str, Any], ...]
    machines: tuple[Mapping[str, Any], ...]
    research: tuple[str, ...]
    total_count: int | None
    total_pages: int | None
    page_size: int | None
    status: str
    detail: str
    fingerprint: str | None
    truncated: bool
    excluded: tuple[Mapping[str, Any], ...] = ()
    tick: int | None = None
    game_version: str | None = None
    force: str | None = None
    surface: str | None = None

    @property
    def empty(self) -> bool:
        """Whether this page carried no catalog rows at all."""
        return not self.recipes and not self.excluded and not self.machines and not self.research


@dataclass
class CatalogAssembly:
    """The result of assembling one or more observed catalog pages.

    The assembly records what was actually loaded so the interface can show
    the real totals and the real completeness state.
    """

    snapshot: CatalogSnapshot
    pages_loaded: tuple[int, ...] = ()
    rows_loaded: int = 0
    missing_pages: tuple[int, ...] = ()
    complete: bool = False
    detail: str = ""

    @property
    def page_count(self) -> int:
        """Return how many distinct pages were assembled."""
        return len(self.pages_loaded)

    def counts(self) -> dict[str, int | None]:
        """Return the real recipe, research and machine counts."""
        return {
            "recipes": len(self.snapshot.recipes),
            "research": len(self.snapshot.research),
            "machines": len(self.snapshot.machines),
            "total_recipes": self.snapshot.total_count,
            "total_pages": self.snapshot.total_pages,
        }


def _rows(value: Any, limit: int) -> tuple[Mapping[str, Any], ...]:
    """Return a bounded tuple of observed mapping rows."""
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _names(value: Any, limit: int) -> tuple[str, ...]:
    """Return a bounded tuple of observed names."""
    if not isinstance(value, (list, tuple)) or len(value) > limit:
        return ()
    names = []
    for item in value:
        if isinstance(item, str) and item.strip():
            names.append(item)
    return tuple(names)


def _fingerprint(frame: Mapping[str, Any]) -> str | None:
    """Return the source fingerprint of one observed frame."""
    capabilities = frame.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return None
    value = capabilities.get("source_fingerprint")
    if isinstance(value, str) and value.strip():
        return value
    return None


def page_from_frame(frame: Mapping[str, Any] | None, *, page: int = 1
                    ) -> CatalogPage:
    """Build one :class:`CatalogPage` from one observed catalog frame.

    A frame that carries no capabilities yields an **empty** page that says
    so. It never yields a page that looks populated.
    """
    source = frame if isinstance(frame, Mapping) else {}
    capabilities = source.get("capabilities")
    capabilities = capabilities if isinstance(capabilities, Mapping) else {}
    status = source.get("catalog_status")
    status = status if isinstance(status, Mapping) else {}

    recipes = _rows(capabilities.get("recipes"), MAX_ASSEMBLED_ROWS)
    machines = _rows(capabilities.get("machines"), MAX_ASSEMBLED_ROWS)
    research = _names(capabilities.get("research"), 16_384)

    reported_page = _bounded_int(status.get("page"))
    catalog_state = status.get("status")
    catalog_state = catalog_state if isinstance(catalog_state, str) else ""

    return CatalogPage(
        page=reported_page if reported_page is not None else int(page),
        recipes=recipes,
        excluded=_rows(capabilities.get("excluded"), MAX_ASSEMBLED_ROWS),
        tick=_bounded_int(capabilities.get("tick")),
        game_version=capabilities.get("game_version"),
        force=capabilities.get("force"), surface=capabilities.get("surface"),
        machines=machines,
        research=research,
        total_count=_bounded_int(status.get("total_count")),
        total_pages=_bounded_int(status.get("total_pages")),
        page_size=_bounded_int(status.get("page_size")),
        status=catalog_state or ("ok" if recipes or machines else "unavailable"),
        detail=("Catalog page observed" if recipes or machines
                else "Catalog page carried no rows"),
        fingerprint=_fingerprint(source),
        truncated=capabilities.get("truncated") is True,
    )


class CatalogPager:
    """Assemble the observed catalog from bounded, cached page requests.

    The pager is the only place that knows how to walk the catalog. It
    never blocks: the caller supplies a fetch function and the pager calls
    it for the pages it still needs.
    """

    def __init__(self, *, page_size: int = 16,
                 max_pages: int = MAX_PAGES_PER_RUN,
                 max_cached_pages: int | None = None,
                 context: Any = None,
                 fetch: Callable[[int], Mapping[str, Any] | None] | None = None):
        """Create a pager.

        ``fetch`` receives a page number and returns the observed frame for
        that page, or ``None`` when the page could not be observed.

        ``max_cached_pages`` bounds the cache. When it is not given, the
        bound comes from the settings, so the cache size is configurable
        rather than fixed. ``context`` is the cache context of the content
        the pager may hold; a page whose context differs is never served.
        """
        if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
            raise ValueError("Invalid catalog page size")
        if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES_PER_RUN:
            raise ValueError("Invalid catalog page budget")
        self.page_size = page_size
        self.max_pages = max_pages
        self.max_cached_pages = _bounded_cached_pages(max_cached_pages)
        self._context = context
        self._fetch = fetch
        self._pages: dict[int, CatalogPage] = {}
        self._fingerprint: str | None = None

    # -- cache ------------------------------------------------------------

    def cached_pages(self) -> tuple[int, ...]:
        """Return the pages that are currently cached."""
        return tuple(sorted(self._pages))

    def has_page(self, page: int) -> bool:
        """Whether one page is already cached."""
        return page in self._pages

    def clear(self) -> None:
        """Drop every cached page and the remembered fingerprint."""
        self._pages.clear()
        self._fingerprint = None

    @property
    def context(self) -> Any:
        """The cache context the pager may hold."""
        return self._context

    def set_context(self, context: Any) -> bool:
        """Adopt a new cache context.

        The cached pages belong to the previous context, so they are
        dropped. The method reports whether anything was dropped, so the
        caller can tell a real invalidation from an unchanged context.
        """
        if self._context is not None and context is not None:
            if getattr(self._context, "key", None) == getattr(context, "key", None):
                return False
        self._context = context
        self.clear()
        return True

    def remember_page(self, page: CatalogPage) -> None:
        """Cache one page, honouring the cache bound and the fingerprint.

        The caller uses this when it already holds an observed page frame
        and wants the pager to reuse it instead of requesting it again.
        """
        self._remember(page)

    def _remember(self, page: CatalogPage) -> None:
        """Cache one page, honouring the cache bound and the fingerprint."""
        fingerprint = page.fingerprint
        if fingerprint is not None:
            if self._fingerprint is not None and fingerprint != self._fingerprint:
                # The catalog content changed under us. The old pages are
                # not mixed with the new ones.
                self._pages.clear()
            self._fingerprint = fingerprint
        if (len(self._pages) >= self.max_cached_pages
                and page.page not in self._pages):
            oldest = min(self._pages) if self._pages else 0
            self._pages.pop(oldest, None)
        if self._pages:
            baseline = next(iter(self._pages.values()))
            if baseline.fingerprint == page.fingerprint and baseline.tick == page.tick:
                page = replace(page,
                    machines=baseline.machines if page.machines == baseline.machines else page.machines,
                    research=baseline.research if page.research == baseline.research else page.research)
        self._pages[page.page] = page

    # -- fetching ---------------------------------------------------------

    def load_page(self, page: int) -> CatalogPage | None:
        """Fetch one page through the injected fetch function.

        A cached page is returned without a backend request. A failed fetch
        returns ``None`` and caches nothing.
        """
        if type(page) is not int or page < 1:
            raise ValueError("Invalid catalog page")
        cached = self._pages.get(page)
        if cached is not None:
            # A cached page is only reused while the catalog content is the
            # same. The game reports a source fingerprint; when it changes,
            # the cached pages describe a catalog that no longer exists.
            if self._fingerprint is not None and cached.fingerprint is not None:
                if cached.fingerprint != self._fingerprint:
                    self._pages.clear()
                else:
                    return cached
            else:
                return cached
        if self._fetch is None:
            return None
        frame = self._fetch(page)
        if not isinstance(frame, Mapping):
            return None
        loaded = page_from_frame(frame, page=page)
        self._remember(loaded)
        return self._pages[page]

    def assemble(self, *, pages: int | None = None) -> CatalogAssembly:
        """Assemble the catalog from the cached and newly fetched pages.

        The assembly stops at the page budget, at the number of pages the
        game reported, or at the first page that could not be observed. The
        result records the pages that are missing so the interface can say
        the catalog is partial instead of silently showing less.
        """
        budget = self.max_pages if pages is None else int(pages)
        if budget < 1:
            raise ValueError("Invalid catalog page budget")
        budget = min(budget, self.max_pages)

        loaded: list[CatalogPage] = []
        missing: list[int] = []
        total_pages: int | None = None
        total_count: int | None = None
        truncated = False

        for number in range(1, budget + 1):
            page = self.load_page(number)
            if page is None:
                missing.append(number)
                break
            if loaded:
                baseline = loaded[0]
                def identity(item):
                    return (item.fingerprint, item.tick, item.game_version,
                            item.force, item.surface, item.total_count,
                            item.total_pages, item.page_size)
                if identity(page) != identity(baseline):
                    self.clear()
                    raise ValueError("Catalog snapshot changed during assembly; refresh required")
            loaded.append(page)
            if page.total_pages is not None:
                total_pages = page.total_pages
            if page.total_count is not None:
                total_count = page.total_count
            truncated = truncated or page.truncated
            if page.status == "page_out_of_range":
                # The game says this page is past the end of the catalog.
                # The walk stops here; the catalog ended earlier.
                break
            if total_pages is not None and number >= total_pages:
                break

        if not loaded:
            detail = ("No catalog page could be observed"
                      if missing else "No catalog page requested")
            return CatalogAssembly(
                snapshot=CatalogSnapshot(
                    recipes=(), research=(), machines=(), status="unavailable",
                    detail=detail, state="unavailable", total_count=None,
                    total_pages=total_pages, page=None, truncated=False,
                    source_fingerprint=None, game_version=None, force=None,
                    surface=None, tick=None),
                pages_loaded=(), rows_loaded=0,
                missing_pages=tuple(missing), complete=False, detail=detail)

        recipes: list[Mapping[str, Any]] = []
        exclusions: dict[str, Mapping[str, Any]] = {}
        machines: list[Mapping[str, Any]] = []
        research: list[str] = []
        seen_recipes: set[str] = set()
        seen_machines: set[str] = set()
        seen_research: set[str] = set()

        for page in loaded:
            for row in page.excluded:
                exclusions[str(row.get("name") or "")] = row
            for row in page.recipes:
                key = str(row.get("name") or "")
                if key in seen_recipes:
                    continue
                seen_recipes.add(key)
                recipes.append(row)
                if len(recipes) >= MAX_ASSEMBLED_ROWS:
                    break
            for row in page.machines:
                key = str(row.get("name") or "")
                if key in seen_machines:
                    continue
                seen_machines.add(key)
                machines.append(row)
                if len(machines) >= MAX_ASSEMBLED_ROWS:
                    break
            for name in page.research:
                if name in seen_research:
                    continue
                seen_research.add(name)
                research.append(name)

        # A page that the game reported as out of range means the catalog
        # ended earlier than the page budget. The assembly is then complete.
        out_of_range = any(page.status == "page_out_of_range" for page in loaded)
        expected_pages = total_pages if total_pages is not None else len(loaded)
        covered = len(set(page.page for page in loaded))
        complete = (
            not missing
            and not truncated
            and not out_of_range
            and expected_pages is not None
            and covered >= expected_pages
            and bool(loaded[0].fingerprint)
            and not set(exclusions).intersection(seen_recipes)
            and total_count == len(recipes) + len(exclusions)
        )

        if complete:
            detail = f"Complete observed catalog: {len(recipes)} recipes"
        elif missing:
            detail = (f"Partial catalog: {len(recipes)} recipes from "
                      f"{covered} page(s); page {missing[0]} unavailable")
        elif truncated:
            detail = (f"Partial catalog: {len(recipes)} recipes; the game "
                      "reported the catalog as truncated")
        else:
            detail = (f"Partial catalog: {len(recipes)} recipes from "
                      f"{covered} of {expected_pages} page(s)")

        snapshot = CatalogSnapshot(
            recipes=tuple(recipes), excluded=tuple(exclusions.values()),
            research=tuple(research),
            machines=tuple(machines),
            status="assembled",
            detail=detail,
            state="observed",
            total_count=total_count,
            total_pages=total_pages,
            page=loaded[-1].page if loaded else None,
            truncated=truncated,
            source_fingerprint=loaded[0].fingerprint if loaded else None,
            game_version=loaded[0].game_version,
            force=loaded[0].force,
            surface=loaded[0].surface,
            tick=loaded[0].tick,
        )
        return CatalogAssembly(
            snapshot=snapshot,
            pages_loaded=tuple(page.page for page in loaded),
            rows_loaded=len(recipes) + len(machines),
            missing_pages=tuple(missing),
            complete=complete,
            detail=detail,
        )

    def apply(self, assembly: CatalogAssembly) -> CatalogSnapshot:
        """Return the snapshot of one assembly, for convenience."""
        return assembly.snapshot


def snapshot_for_frame(frame: Mapping[str, Any] | None, *, state: str = "observed",
                       detail: str = "Observed catalog") -> CatalogSnapshot:
    """Return the shared snapshot for one observed frame."""
    return catalog_snapshot(frame, state=state, detail=detail)


__all__ = [
    "MAX_ASSEMBLED_ROWS",
    "MAX_CACHED_PAGES",
    "MAX_PAGES_PER_RUN",
    "MAX_PAGE_SIZE",
    "CatalogAssembly",
    "CatalogPage",
    "CatalogPager",
    "page_from_frame",
    "snapshot_for_frame",
]
