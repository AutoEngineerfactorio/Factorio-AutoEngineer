"""Fail-closed assembly of paged, same-snapshot recipe catalog observations."""

import asyncio
import json
import time

from dashboard_feed import snapshot
from read_only_planning import accounted_recipe_count, validate_exclusions

PAGE_SIZE = 16
# The backend accepts catalog pages 1..10000 and 1..32 entries per page, so
# the addressable catalog is bounded by the page count, not by a flat entry
# cap. A large modpack (the Pyanodons suite alone carries far more than
# 10,000 recipes) must page instead of being rejected outright, so the entry
# bound is derived from the backend's own page limit.
MAX_CATALOG_PAGES = 10000
MAX_CATALOG_ENTRIES = MAX_CATALOG_PAGES * PAGE_SIZE
MAX_ASSEMBLED_CAPABILITY_BYTES = 12 * 1048576
PAGE_TIMEOUT_SECONDS = 12
ASSEMBLY_TIMEOUT_SECONDS = 15
MAX_MULTI_TICK_ASSEMBLY_SECONDS = 3600


class CatalogAssemblyError(ValueError):
    """The catalog pages could not be proven to describe one complete snapshot."""


def _validated_page(raw, expected_page, *, allow_multi_tick=False):
    try:
        snapshot(raw)
    except (TypeError, ValueError, KeyError) as exc:
        raise CatalogAssemblyError("Invalid recipe catalog page") from exc
    status = raw.get("catalog_status")
    caps = raw.get("capabilities")
    if (not isinstance(status, dict) or status.get("status") != "ok"
            or status.get("page") != expected_page
            or not isinstance(caps, dict)):
        raise CatalogAssemblyError("Recipe catalog page is missing or out of sequence")
    count, pages, page_size = (
        status.get("total_count"), status.get("total_pages"), status.get("page_size")
    )
    if (type(count) is not int or not 0 <= count <= MAX_CATALOG_ENTRIES
            or type(pages) is not int or not 0 <= pages <= MAX_CATALOG_PAGES
            or type(page_size) is not int or page_size not in (16, 32, 64, 128)
            or pages != (count + page_size - 1) // page_size
            or expected_page > max(pages, 1)):
        raise CatalogAssemblyError("Inconsistent recipe catalog page bounds")
    if ((not allow_multi_tick and caps.get("source_fingerprint") is None)
            or len(caps["recipes"]) > page_size):
        raise CatalogAssemblyError("Catalog page lacks a bounded source fingerprint")
    return status, caps


async def assemble_catalog(session, first_raw, *, monotonic=time.monotonic,
                           stop_event=None, allow_multi_tick=False):
    """Assemble pages; multi-tick results remain explicitly unverified/partial.

    Strict callers retain same-tick/fingerprint behavior. Large-modpack UI
    callers may browse an ordered, identity-stable multi-tick collection, but
    must never present it as a complete same-tick planning snapshot.
    """
    started = monotonic()
    first_status, first_caps = _validated_page(
        first_raw, 1, allow_multi_tick=allow_multi_tick)
    page_size = first_status["page_size"]
    total_pages = first_status["total_pages"]
    if total_pages > MAX_CATALOG_PAGES:
        raise CatalogAssemblyError("Recipe catalog requires too many pages")

    identity = (
        first_caps["tick"], first_caps["game_version"], first_caps["force"],
        first_caps["surface"], tuple(first_caps["research"]),
        tuple(first_caps["enabled_content"]), first_caps["source_fingerprint"],
    )
    recipes = []
    exclusions = []
    truncated = False
    unverified = first_caps.get("source_fingerprint") is None
    previous_name = None
    budget = (min(MAX_MULTI_TICK_ASSEMBLY_SECONDS,
                  max(ASSEMBLY_TIMEOUT_SECONDS, total_pages * PAGE_TIMEOUT_SECONDS))
              if allow_multi_tick else ASSEMBLY_TIMEOUT_SECONDS)
    if first_status.get("snapshot") is True:
        budget = max(budget, min(120, total_pages * 0.25 + 5))
    for page in range(1, total_pages + 1):
        if stop_event is not None and stop_event.is_set():
            raise CatalogAssemblyError("Recipe catalog assembly stopped")
        if page == 1:
            raw = first_raw
            status, caps = first_status, first_caps
        else:
            if monotonic() - started > budget:
                raise CatalogAssemblyError("Recipe catalog assembly exceeded its time budget")
            try:
                response = await asyncio.wait_for(
                    session.call_tool(
                        "autoengineer_view",
                        arguments={"catalogPage": page, "catalogPageSize": page_size},
                    ),
                    timeout=PAGE_TIMEOUT_SECONDS,
                )
            except (asyncio.TimeoutError, TimeoutError) as exc:
                raise CatalogAssemblyError("Recipe catalog page timed out") from exc
            if getattr(response, "is_error", False):
                raise CatalogAssemblyError("Recipe catalog page request failed")
            try:
                raw = json.loads(next(item.text for item in response.content if item.type == "text"))
            except (StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise CatalogAssemblyError("Recipe catalog page response was invalid") from exc
            status, caps = _validated_page(raw, page, allow_multi_tick=allow_multi_tick)

        current_identity = (
            caps["tick"], caps["game_version"], caps["force"],
            caps["surface"], tuple(caps["research"]),
            tuple(caps["enabled_content"]), caps["source_fingerprint"],
        )
        if (current_identity[1:] if allow_multi_tick else current_identity) != (
                identity[1:] if allow_multi_tick else identity):
            raise CatalogAssemblyError("Recipe catalog changed during page assembly")
        if allow_multi_tick and current_identity[0] != identity[0]:
            unverified = True
        if (status["total_count"] != first_status["total_count"]
                or status["total_pages"] != total_pages
                or status["page_size"] != page_size):
            raise CatalogAssemblyError("Recipe catalog page counts changed during assembly")
        page_recipes = caps["recipes"]
        if page_recipes != sorted(page_recipes, key=lambda item: item["name"]):
            raise CatalogAssemblyError("Recipe catalog page is not deterministically ordered")
        expected_page_count = min(
            page_size, max(0, first_status["total_count"] - (page - 1) * page_size)
        )
        page_exclusions = validate_exclusions(caps)
        represented = accounted_recipe_count(caps)
        if not caps["truncated"] and represented != expected_page_count:
            raise CatalogAssemblyError("Complete recipe page has an unexpected row count")
        page_names = sorted(row["name"] for row in page_recipes + page_exclusions)
        if page_names and previous_name is not None and page_names[0] <= previous_name:
            raise CatalogAssemblyError("Recipe catalog pages overlap or are out of order")
        if page_names:
            previous_name = page_names[-1]
        recipes.extend(page_recipes)
        exclusions.extend(page_exclusions)
        truncated = truncated or caps["truncated"]

    if monotonic() - started > budget:
        raise CatalogAssemblyError("Recipe catalog assembly exceeded its time budget")
    represented = accounted_recipe_count({"recipes": recipes, "excluded": exclusions})
    if represented > first_status["total_count"]:
        raise CatalogAssemblyError("Recipe catalog contains more rows than its declared total")
    if not truncated and represented != first_status["total_count"]:
        raise CatalogAssemblyError("Recipe catalog is incomplete without a truncation marker")

    # A multi-tick/null-fingerprint sweep is browsable, not a verified
    # same-tick catalog for production planning.
    assembled_caps = dict(first_caps, recipes=recipes, excluded=exclusions,
                          truncated=truncated or unverified)
    encoded = json.dumps(assembled_caps, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_ASSEMBLED_CAPABILITY_BYTES:
        raise CatalogAssemblyError("Assembled recipe catalog exceeds payload budget")
    result = dict(first_raw, capabilities=assembled_caps)
    result["catalog_status"] = dict(
        first_status, status="assembled", pages_collected=max(total_pages, 1)
    )
    return result
