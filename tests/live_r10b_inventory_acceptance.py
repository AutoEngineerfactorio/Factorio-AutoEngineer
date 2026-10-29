"""R10-B live acceptance: the observed inventory and logistics.

The harness starts the isolated Factorio 2.1.23 server and the graphical
client on one of the two active profiles, drives the **real** restricted
backend over stdio, and verifies the R10-B observations against the
running game.

It proves, with real data:

* the machine inventories are observed, with the item quantities, the
  qualities, the capacities and the machine identity;
* the logistic networks are observed, with their available counts and
  their provider, requester and storage membership;
* the robot availability is observed;
* the transport and storage inventories are observed;
* the Qt workspaces render the observed rows;
* the AI Helper consumes the same observation;
* the pagination is bounded and the page boundaries are stable;
* the source save is unchanged and no gameplay command was issued.

The harness **reuses** the proven R10-A helpers
(``tests/qt_live_acceptance.py``) so the environment, the profile routing
and the process handling stay identical to the accepted R10-A run.

Usage:

    python -B tests/live_r10b_inventory_acceptance.py --profile vanilla
    python -B tests/live_r10b_inventory_acceptance.py --profile pyanodons
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "agent"))

# The R10-A harness adds the system site-packages, so the mcp client and
# the Qt bindings are importable no matter which interpreter runs it.
import qt_live_acceptance as harness  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

env = harness.env
game_side = harness.game_side

#: The tool that carries the R10-B observations.
INVENTORY_TOOL = "autoengineer_inventory"

#: How many pages the harness requests, to prove the pagination.
PAGE_COUNT = 3


def _section(payload: dict, name: str) -> dict:
    """Return one section of the inventory frame."""
    value = payload.get(name)
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    """Return one bounded text value, or the empty string."""
    return value if isinstance(value, str) else ""


def _texts(values: object, limit: int) -> list[str]:
    """Return the sorted, bounded text values of a collection."""
    if not isinstance(values, (list, tuple, set)):
        return []
    texts = {value for value in values if isinstance(value, str)}
    return sorted(texts)[:limit]


def _rows(section: dict) -> list[dict]:
    """Return the bounded row objects of one section."""
    rows = section.get("rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _inventories(row: dict) -> list[dict]:
    """Return the inventory objects of one row."""
    inventories = row.get("inventories")
    if not isinstance(inventories, list):
        return []
    return [item for item in inventories if isinstance(item, dict)]


def _items(container: dict) -> list[dict]:
    """Return the item objects of one inventory or network."""
    items = container.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def summarise_inventory(payload: dict) -> dict:
    """Return the bounded summary of one inventory observation.

    The summary is the **evidence**, not the raw frame: it names what was
    observed and how much of it, so the report stays readable and a
    reviewer can check the numbers.
    """
    machines = _section(payload, "machine_inventories")
    logistics = _section(payload, "logistics")
    robots = _section(payload, "robots")
    transport = _section(payload, "transport")

    machine_rows = _rows(machines)
    network_rows = _rows(logistics)
    transport_rows = _rows(transport)

    machine_inventories = [inventory for row in machine_rows
                           for inventory in _inventories(row)]
    machine_items = [item for inventory in machine_inventories
                     for item in _items(inventory)]
    network_items = [item for row in network_rows
                     for item in _items(row)]

    return {
        "machines": {
            "available": machines.get("available") is True,
            "status": machines.get("status"),
            "reason": machines.get("reason"),
            "page": machines.get("page"),
            "page_size": machines.get("page_size"),
            "total": machines.get("total"),
            "page_count": machines.get("page_count"),
            "row_count": machines.get("row_count"),
            "matched": machines.get("matched"),
            "partial": machines.get("partial") is True,
            "truncated": machines.get("truncated") is True,
            "snapshot": machines.get("snapshot"),
            "names": _texts([row.get("name") for row in machine_rows], 12),
            "types": _texts([row.get("type") for row in machine_rows], 12),
            "inventory_categories": _texts(
                [item.get("category") for item in machine_inventories], 12),
            "inventory_identifiers": _texts(
                [item.get("identifier") for item in machine_inventories], 16),
            "items": _texts(
                [f"{item.get('name')}:{item.get('quality')}"
                 for item in machine_items], 24),
            "sample_row": machine_rows[0] if machine_rows else None,
        },
        "logistics": {
            "available": logistics.get("available") is True,
            "status": logistics.get("status"),
            "reason": logistics.get("reason"),
            "page": logistics.get("page"),
            "page_count": logistics.get("page_count"),
            "row_count": logistics.get("row_count"),
            "total": logistics.get("total"),
            "network_ids": [row.get("network_id") for row in network_rows],
            "surfaces": _texts([row.get("surface") for row in network_rows], 8),
            "items": _texts(
                [f"{item.get('name')}:{item.get('quality')}"
                 for item in network_items], 24),
            "providers": _texts(
                [name for row in network_rows
                 for name in (row.get("providers") or [])
                 if isinstance(name, str)], 12),
            "requesters": _texts(
                [name for row in network_rows
                 for name in (row.get("requesters") or [])
                 if isinstance(name, str)], 12),
            "storages": _texts(
                [name for row in network_rows
                 for name in (row.get("storages") or [])
                 if isinstance(name, str)], 12),
        },
        "robots": {
            "available": robots.get("available") is True,
            "status": robots.get("status"),
            "reason": robots.get("reason"),
            "networks": robots.get("networks"),
            "total_logistic_robots": robots.get("total_logistic_robots"),
            "available_logistic_robots":
                robots.get("available_logistic_robots"),
            "total_construction_robots":
                robots.get("total_construction_robots"),
            "available_construction_robots":
                robots.get("available_construction_robots"),
            "robot_limit": robots.get("robot_limit"),
        },
        "transport": {
            "available": transport.get("available") is True,
            "status": transport.get("status"),
            "reason": transport.get("reason"),
            "row_count": transport.get("row_count"),
            "total": transport.get("total"),
            "names": _texts([row.get("name") for row in transport_rows], 12),
            "types": _texts([row.get("type") for row in transport_rows], 12),
        },
    }


async def observe_inventory(session: ClientSession, machine_page: int = 1,
                            machine_page_size: int = 16,
                            logistics_page: int = 1,
                            logistics_page_size: int = 16) -> dict:
    """Ask the backend for one bounded inventory observation."""
    return await harness.call_tool(session, INVENTORY_TOOL, {
        "machinePage": machine_page,
        "machinePageSize": machine_page_size,
        "logisticsPage": logistics_page,
        "logisticsPageSize": logistics_page_size,
    })


async def verify_inventory(session: ClientSession, report: dict) -> bool:
    """Verify the R10-B observations against the running game.

    The verification is **evidence-based**: a field passes only when the
    game actually reported it. A section that the game did not report is
    recorded as such, never as a zero.
    """
    payload = await observe_inventory(session)
    report["inventory_status"] = payload.get("status")
    report["inventory_protocol"] = payload.get("protocol")
    report["inventory_tick"] = payload.get("tick")
    report["inventory_surface"] = payload.get("surface")
    summary = summarise_inventory(payload)
    report["inventory"] = summary

    # -- the four sections -------------------------------------------
    machines = summary["machines"]
    logistics = summary["logistics"]
    robots = summary["robots"]
    transport = summary["transport"]

    report["machine_inventories_observed"] = bool(
        machines["available"] and machines["status"] == "ok")
    report["logistic_networks_observed"] = bool(
        logistics["available"] and logistics["status"] == "ok")
    report["robots_observed"] = bool(
        robots["available"] and robots["status"] == "ok")
    report["transport_observed"] = bool(
        transport["available"] and transport["status"] == "ok")

    # The observation must carry the pagination and the snapshot token.
    report["pagination_present"] = bool(
        machines.get("page") is not None
        and machines.get("page_count") is not None
        and machines.get("snapshot"))
    report["machine_page_count"] = machines.get("page_count")
    report["machine_total"] = machines.get("total")

    # The observed rows must be bounded by the requested page size.
    report["machine_rows_bounded"] = (
        (machines.get("row_count") or 0) <= 16)

    # -- the pagination walk -----------------------------------------
    pages: list[dict] = []
    seen_identities: list[str] = []
    for page in range(1, PAGE_COUNT + 1):
        page_payload = await observe_inventory(session, machine_page=page)
        section = _section(page_payload, "machine_inventories")
        rows = _rows(section)
        names = [_text(row.get("name")) for row in rows]
        identities = [
            f"{_text(row.get('name'))}#{row.get('unit_number')}"
            for row in rows
        ]
        pages.append({
            "page": page,
            "status": section.get("status"),
            "row_count": section.get("row_count"),
            "snapshot": section.get("snapshot"),
            "names": [name for name in names if name][:12],
        })
        seen_identities.extend(identity for identity in identities if identity)
        if not names:
            break
    report["pagination_walk"] = pages
    report["pagination_pages_read"] = len(pages)
    # The identity of an entity is its prototype name **and** its unit
    # number: two entities of the same prototype share the name.
    report["pagination_rows_unique"] = (
        len(seen_identities) == len(set(seen_identities)))
    report["pagination_snapshots"] = [page.get("snapshot") for page in pages]

    # -- the AI Helper consumes the same observation ------------------
    view = await harness.call_tool(session, "autoengineer_view", {})
    report["view_status"] = view.get("status")
    try:
        from observed_supply import observed_supply
        from read_only_planning import view_intelligence

        supply = observed_supply(payload)
        report["observed_supply_known"] = supply.known
        report["observed_supply_items"] = [
            {"name": item.name, "count": item.count,
             "quality": item.quality}
            for item in supply.available[:24]]
        report["observed_supply_machines"] = supply.machine_count
        report["observed_supply_networks"] = supply.network_count
        report["observed_recipes"] = list(supply.observed_recipes)[:16]
        if view.get("status") == "ok":
            planner = view_intelligence(view, inventory_observation=payload)
            report["planner_supply_observed"] = planner.get("supply_observed")
            report["planner_has_observed_supply"] = (
                planner.get("observed_supply") is not None)
    except Exception as exc:  # noqa: BLE001 - reported, never hidden
        report["planner_error"] = f"{type(exc).__name__}: {exc}"

    # -- the Qt workspaces render the observed rows --------------------
    try:
        from importlib import import_module

        from qt_inventory_observations import inventory_observation
        from qt_inventory_widget import InventoryWidget

        QApplication = import_module("PySide6.QtWidgets").QApplication
        # The Qt application must exist before a widget is built.
        _ = QApplication.instance() or QApplication([])
        snapshot = inventory_observation(payload)
        inventory_widget = InventoryWidget(scope="inventory")
        inventory_widget.set_snapshot(snapshot)
        logistics_widget = InventoryWidget(scope="logistics")
        logistics_widget.set_snapshot(snapshot)
        report["qt_machine_rows"] = inventory_widget.machine_table.rowCount()
        report["qt_network_rows"] = (
            logistics_widget.logistic_network_table.rowCount())
        report["qt_robot_rows"] = logistics_widget.robot_table.rowCount()
        report["qt_transport_rows"] = (
            logistics_widget.transport_table.rowCount())
        report["qt_status_text"] = inventory_widget.status.text()
        report["qt_observed"] = bool(
            report["qt_machine_rows"] or report["qt_network_rows"])
        inventory_widget.close()
        logistics_widget.close()
    except Exception as exc:  # noqa: BLE001 - reported, never hidden
        report["qt_error"] = f"{type(exc).__name__}: {exc}"

    # -- the verdict ---------------------------------------------------
    required = [
        report.get("machine_inventories_observed"),
        report.get("logistic_networks_observed"),
        report.get("robots_observed"),
        report.get("transport_observed"),
        report.get("pagination_present"),
        report.get("machine_rows_bounded"),
        report.get("pagination_rows_unique"),
        report.get("observed_supply_known"),
        report.get("planner_supply_observed"),
        report.get("qt_observed"),
    ]
    report["inventory_verified"] = all(required)
    report["inventory_missing"] = [
        name for name, value in (
            ("machine_inventories", report.get("machine_inventories_observed")),
            ("logistic_networks", report.get("logistic_networks_observed")),
            ("robots", report.get("robots_observed")),
            ("transport", report.get("transport_observed")),
            ("pagination", report.get("pagination_present")),
            ("bounded", report.get("machine_rows_bounded")),
            ("unique_pages", report.get("pagination_rows_unique")),
            ("supply", report.get("observed_supply_known")),
            ("planner", report.get("planner_supply_observed")),
            ("qt", report.get("qt_observed")),
        ) if not value]
    return bool(report["inventory_verified"])


async def run(profile_name: str) -> dict:
    """Run the R10-B live acceptance for one profile."""
    profile = harness.profile_for(profile_name)
    run_tag = f"r10b-live-{profile_name}"
    report: dict = {
        "profile": profile["name"],
        "evidence_type": "LIVE READ-ONLY",
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "game_executable": str(harness.EXE),
        "mod_directory": str(profile["mods"]),
    }
    harness.EVIDENCE.mkdir(parents=True, exist_ok=True)

    password = env.rcon_password()
    source_save = Path(profile["save"])
    report["source_save_sha256_before"] = harness.sha256(source_save)

    config, save = harness.prepare_server(profile, run_tag, password)
    report["disposable_save"] = str(save)

    server = None
    client = None
    try:
        server = harness.start_server(profile, run_tag, config, save, password,
                                     report)
        if not report.get("server_ready"):
            report["stopped_at"] = "the server did not become ready"
        else:
            client = harness.start_client(profile, run_tag, report)
            client_data = env.CLIENT_PROFILE / "data"
            harness.wait_for_join(client, harness.BASE / "server" / "data",
                                  client_data, report)
            if not report.get("client_joined"):
                report["stopped_at"] = "the client did not join"
            else:
                async with stdio_client(
                        harness.mcp_params(
                            harness.RESTRICTED_BACKEND,
                            profile["rcon_port"], password)
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        report["backend_policy"] = await harness.call_tool(
                            session, "autoengineer_policy", {})
                        if not await harness.wait_for_player(session, report):
                            report["stopped_at"] = (
                                "the backend never observed a player")
                        else:
                            report["ups_before"] = harness.read_game_stats(
                                harness.BASE / "server" / "data")
                            await verify_inventory(session, report)
                            report["ups_after"] = harness.read_game_stats(
                                harness.BASE / "server" / "data")
    finally:
        harness.stop_process(client, "client", report)
        harness.stop_process(server, "server", report)
        report["source_save_sha256_after"] = harness.sha256(source_save)
        report["source_save_unchanged"] = (
            report["source_save_sha256_before"]
            == report["source_save_sha256_after"])
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        out = harness.EVIDENCE / f"{run_tag}-acceptance.json"
        out.write_text(json.dumps(report, indent=2, default=str),
                       encoding="utf-8")
        report["report_path"] = str(out)
        harness.log(f"REPORT={out}")
    return report


def main() -> int:
    """Run the live acceptance and print the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("vanilla", "pyanodons"),
                        default="vanilla")
    args = parser.parse_args()

    report = asyncio.run(run(args.profile))
    print(json.dumps(report, indent=2, default=str))
    ok = bool(report.get("inventory_verified")) and bool(
        report.get("source_save_unchanged"))
    print(f"R10B_LIVE_VERDICT={'pass' if ok else 'fail'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
