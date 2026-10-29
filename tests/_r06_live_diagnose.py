"""Diagnose the live catalog row shortfall by re-reading one page.

The live sweep reported fewer rows per page than the request size. This
probe reads a single page through the **read-only** restricted backend and
reports what the page actually carries, so the cause is measured instead of
assumed.

It is read-only: it calls only the autoengineer_view tool with a catalog
page argument and never performs a gameplay action.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import r06_live_environment as env  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

RESTRICTED_BACKEND = (
    ROOT / ".local" / "live-pillow-2.1.23" / "backend-patched-2.1.23"
    / "FactorioMCP.dll"
)
EVIDENCE = ROOT / ".local" / "live-pillow-2.1.23" / "evidence"


async def call_tool(session: ClientSession, name: str, arguments: dict) -> dict:
    response = await asyncio.wait_for(
        session.call_tool(name, arguments=arguments), 120
    )
    text = next(item.text for item in response.content if item.type == "text")
    return json.loads(text)


async def probe(page: int, page_size: int) -> None:
    password = env.rcon_password()
    params = StdioServerParameters(
        command="dotnet",
        args=[str(RESTRICTED_BACKEND)],
        env=env.backend_launch_environment(27161, password, "helper"),
        cwd=str(env.BACKEND_RUNTIME),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            payload = await call_tool(
                session, "autoengineer_view",
                {"catalogPage": page, "catalogPageSize": page_size},
            )
            status = payload.get("catalog_status") or {}
            capabilities = payload.get("capabilities") or {}
            recipes = capabilities.get("recipes") or []
            print(f"page={page} requested_size={page_size}")
            print(f"status={json.dumps(status)}")
            print(f"rows_on_page={len(recipes)}")
            print(f"capability_keys={sorted(capabilities)[:14]}")
            names = [str(row.get("name")) for row in recipes]
            print(f"first_names={names[:6]}")
            print(f"last_names={names[-6:]}")
            # Report the observed shape of one row so a dropped field is
            # visible without dumping the whole catalog.
            if recipes:
                print(f"row0={json.dumps(recipes[0], sort_keys=True)[:900]}")
            out = EVIDENCE / "r06-live-page-probe.json"
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"evidence={out}")


def main() -> int:
    page = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    asyncio.run(probe(page, size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
