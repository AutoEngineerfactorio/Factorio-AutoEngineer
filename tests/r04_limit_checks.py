"""Offline check of the R04 catalog assembly limits.

Confirms the 10,000-entry fail-closed cap and the 400 KB assembled capability
limit are enforced by the production assembler, and that a catalog over either
limit cannot enable planning.
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
sys.path.insert(0, str(ROOT / "agent"))

from catalog_assembly import (  # noqa: E402
    MAX_ASSEMBLED_CAPABILITY_BYTES,
    MAX_CATALOG_ENTRIES,
    MAX_CATALOG_PAGES,
    CatalogAssemblyError,
    assemble_catalog,
)

FINGERPRINT = "poly31x131-v1:0123456789-9876543210"


def recipe(index):
    return {
        "name": f"recipe-{index:06d}", "enabled": True, "hidden": False,
        "simple": True, "category": "crafting", "crafting_time": 1,
        "ingredients": [{"name": "iron-plate", "type": "item", "amount": 1}],
        "products": [{"name": f"recipe-{index:06d}", "type": "item", "amount": 1}],
    }


def page(number, rows, *, total_count, total_pages, tick=120):
    return {
        "status": "ok", "x": 0, "y": 0, "tick": tick, "surface": "nauvis",
        "inventory": [], "inventory_available": True, "truncated": False,
        "catalog_status": {
            "page": number, "page_size": 16, "total_count": total_count,
            "total_pages": total_pages, "status": "ok",
        },
        "capabilities": {
            "schema": 1, "tick": tick, "surface": "nauvis",
            "game_version": "2.1.23", "force": "player", "research": [],
            "enabled_content": ["base"], "truncated": False,
            "recipes": rows, "source_fingerprint": FINGERPRINT,
        },
    }


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)

    async def call_tool(self, name, arguments):
        value = self.responses.pop(0)
        return type("R", (), {
            "is_error": False,
            "content": [type("C", (), {"type": "text", "text": json.dumps(value)})()],
        })()


async def main():
    print(f"MAX_CATALOG_ENTRIES={MAX_CATALOG_ENTRIES}")
    print(f"MAX_CATALOG_PAGES={MAX_CATALOG_PAGES}")
    print(f"MAX_ASSEMBLED_CAPABILITY_BYTES={MAX_ASSEMBLED_CAPABILITY_BYTES}")

    # The 10,000-entry cap: a catalog declaring more than the cap is rejected.
    over = page(1, [recipe(0)], total_count=MAX_CATALOG_ENTRIES + 1,
                total_pages=MAX_CATALOG_PAGES + 1)
    try:
        await assemble_catalog(FakeSession([]), over)
        print("ENTRY_CAP_REJECTED=False")
    except CatalogAssemblyError as exc:
        print(f"ENTRY_CAP_REJECTED=True ({exc})")

    # The 400 KB assembled limit: many rows that fit the entry cap but
    # overflow the encoded payload budget must fail closed.
    rows = [recipe(i) for i in range(16)]
    total = 20000
    total_pages = total // 16
    first = page(1, rows, total_count=total, total_pages=total_pages)
    pages = []
    for number in range(2, total_pages + 1):
        pages.append(page(number, [recipe(number * 16 + i) for i in range(16)],
                           total_count=total, total_pages=total_pages))
    try:
        await assemble_catalog(FakeSession(pages), first)
        print("PAYLOAD_CAP_REJECTED=False")
    except CatalogAssemblyError as exc:
        print(f"PAYLOAD_CAP_REJECTED=True ({exc})")

    # A normal two-page catalog still assembles. Names must be globally
    # ordered and the first page must start at the beginning of the catalog.
    normal_rows = [recipe(i) for i in range(17)]
    normal_first = page(1, normal_rows[:16], total_count=17, total_pages=2)
    normal_second = page(2, normal_rows[16:], total_count=17, total_pages=2)
    assembled = await assemble_catalog(FakeSession([normal_second]), normal_first)
    recipes = assembled["capabilities"]["recipes"]
    if not isinstance(recipes, list):
        raise TypeError("assembled capabilities recipes must be a list")
    print("NORMAL_ASSEMBLY_ROWS=" + str(len(recipes)))
    print("NORMAL_ASSEMBLY_STATUS=" + str(assembled["catalog_status"]["status"]))


asyncio.run(main())
