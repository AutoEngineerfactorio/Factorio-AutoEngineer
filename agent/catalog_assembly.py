"""Fail-closed assembly of paged, same-snapshot recipe catalog observations."""

import asyncio
import json
import time

from dashboard_feed import snapshot

PAGE_SIZE = 16
MAX_CATALOG_ENTRIES = 10000
MAX_CATALOG_PAGES = (MAX_CATALOG_ENTRIES + PAGE_SIZE - 1) // PAGE_SIZE
MAX_ASSEMBLED_CAPABILITY_BYTES = 400000
PAGE_TIMEOUT_SECONDS = 2
ASSEMBLY_TIMEOUT_SECONDS = 15


class CatalogAssemblyError(ValueError):
    """The catalog pages could not be proven to describe one complete snapshot."""


def _validated_page(raw, expected_page):
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
            or type(page_size) is not int or page_size != PAGE_SIZE
            or pages != (count + page_size - 1) // page_size
            or expected_page > max(pages, 1)):
        raise CatalogAssemblyError("Inconsistent recipe catalog page bounds")
    if (caps.get("source_fingerprint") is None
            or len(caps["recipes"]) > page_size):
        raise CatalogAssemblyError("Catalog page lacks a bounded source fingerprint")
    return status, caps


async def assemble_catalog(session, first_raw, *, monotonic=time.monotonic, stop_event=None):
    """Return the first view frame with a complete catalog or raise explicitly.

    All catalog pages must describe one exact game tick and one source
    fingerprint. The function does not weaken the same-tick contract when a
    live game advances while pages are being read.
    """
    started = monotonic()
    first_status, first_caps = _validated_page(first_raw, 1)
    total_pages = first_status["total_pages"]
    if total_pages > MAX_CATALOG_PAGES:
        raise CatalogAssemblyError("Recipe catalog requires too many pages")

    identity = (
        first_caps["tick"], first_caps["game_version"], first_caps["force"],
        first_caps["surface"], tuple(first_caps["research"]),
        tuple(first_caps["enabled_content"]), first_caps["source_fingerprint"],
    )
    recipes = []
    truncated = False
    previous_name = None
    for page in range(1, total_pages + 1):
        if stop_event is not None and stop_event.is_set():
            raise CatalogAssemblyError("Recipe catalog assembly stopped")
        if page == 1:
            raw = first_raw
            status, caps = first_status, first_caps
        else:
            if monotonic() - started > ASSEMBLY_TIMEOUT_SECONDS:
                raise CatalogAssemblyError("Recipe catalog assembly exceeded its time budget")
            try:
                response = await asyncio.wait_for(
                    session.call_tool(
                        "autoengineer_view",
                        arguments={"catalogPage": page, "catalogPageSize": PAGE_SIZE},
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
            status, caps = _validated_page(raw, page)

        current_identity = (
            caps["tick"], caps["game_version"], caps["force"],
            caps["surface"], tuple(caps["research"]),
            tuple(caps["enabled_content"]), caps["source_fingerprint"],
        )
        if current_identity != identity:
            raise CatalogAssemblyError("Recipe catalog changed during page assembly")
        if (status["total_count"] != first_status["total_count"]
                or status["total_pages"] != total_pages
                or status["page_size"] != PAGE_SIZE):
            raise CatalogAssemblyError("Recipe catalog page counts changed during assembly")
        page_recipes = caps["recipes"]
        if page_recipes != sorted(page_recipes, key=lambda item: item["name"]):
            raise CatalogAssemblyError("Recipe catalog page is not deterministically ordered")
        expected_page_count = min(
            PAGE_SIZE, max(0, first_status["total_count"] - (page - 1) * PAGE_SIZE)
        )
        if not caps["truncated"] and len(page_recipes) != expected_page_count:
            raise CatalogAssemblyError("Complete recipe page has an unexpected row count")
        if page_recipes and previous_name is not None and page_recipes[0]["name"] <= previous_name:
            raise CatalogAssemblyError("Recipe catalog pages overlap or are out of order")
        if page_recipes:
            previous_name = page_recipes[-1]["name"]
        recipes.extend(page_recipes)
        truncated = truncated or caps["truncated"]

    if monotonic() - started > ASSEMBLY_TIMEOUT_SECONDS:
        raise CatalogAssemblyError("Recipe catalog assembly exceeded its time budget")
    if len(recipes) > first_status["total_count"]:
        raise CatalogAssemblyError("Recipe catalog contains more rows than its declared total")
    if not truncated and len(recipes) != first_status["total_count"]:
        raise CatalogAssemblyError("Recipe catalog is incomplete without a truncation marker")

    assembled_caps = dict(first_caps, recipes=recipes, truncated=truncated)
    encoded = json.dumps(assembled_caps, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_ASSEMBLED_CAPABILITY_BYTES:
        raise CatalogAssemblyError("Assembled recipe catalog exceeds payload budget")
    result = dict(first_raw, capabilities=assembled_caps)
    result["catalog_status"] = dict(
        first_status, status="assembled", pages_collected=max(total_pages, 1)
    )
    return result
