"""Read-only Helper acceptance on disposable vanilla or Pyanodons profiles.

Reuses the owned-process lifecycle and source-save integrity checks of R10-B.
Only registered observation tools are called; no gameplay commands are issued.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

import live_r10b_inventory_acceptance as inventory
import r06_live_catalog_sweep as catalog


async def run(profile: str) -> dict:
    original = inventory.verify_inventory
    original_evidence = inventory.harness.EVIDENCE
    evidence = original_evidence / time.strftime("helper-catalog-%Y%m%d-%H%M%S")
    inventory.harness.EVIDENCE = evidence

    async def verify(session, report):
        await original(session, report)
        result = {}
        await catalog.sweep(session, result)
        report["catalog"] = result
        machines = result.get("machines", {}).get("rows", [])
        speeds = [m for m in machines if isinstance(m.get("crafting_speed"), (int, float))
                  and m["crafting_speed"] > 0]
        slots = [m for m in machines if type(m.get("module_slots")) is int]
        report["machine_rates"] = {"machines": len(machines),
            "observed_positive_speeds": len(speeds), "observed_slot_counts": len(slots),
            "verified": bool(speeds) and bool(slots)}
        return report.get("inventory_verified", False)

    inventory.verify_inventory = verify
    try:
        report = await inventory.run(profile)
    finally:
        inventory.verify_inventory = original
        inventory.harness.EVIDENCE = original_evidence
    report["helper_catalog_pass"] = bool(
        report.get("source_save_unchanged") and report.get("inventory_verified")
        and report.get("machine_rates", {}).get("verified")
        and report.get("catalog", {}).get("accounting", {}).get("balanced")
        and report.get("catalog", {}).get("identity", {}).get("source_fingerprint")
        and report.get("catalog", {}).get("identity", {}).get("truncated") is False)
    (evidence / "summary.json").write_text(json.dumps({
        key: report.get(key) for key in ("profile", "machine_rates", "helper_catalog_pass",
                                       "source_save_unchanged", "client_stopped", "server_stopped")
    }, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("vanilla", "pyanodons"), required=True)
    parser.add_argument("--save", type=Path,
                        help="Existing Pyanodons save inside the isolated saves directory")
    args = parser.parse_args()
    if args.save is not None:
        selected = args.save.resolve()
        allowed = inventory.harness.PYAN_SAVE.parent.resolve()
        if (args.profile != "pyanodons" or selected.parent != allowed
                or selected.suffix.lower() != ".zip" or not selected.is_file()):
            parser.error("Select an existing isolated Pyanodons ZIP save")
        inventory.harness.PYAN_SAVE = selected
    report = asyncio.run(run(args.profile))
    print(json.dumps({key: report.get(key) for key in (
        "profile", "machine_rates", "helper_catalog_pass", "source_save_unchanged",
        "client_stopped", "server_stopped", "report_path")}, indent=2))
    return 0 if report["helper_catalog_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
