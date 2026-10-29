"""Live read-only Qt catalog/planning acceptance on disposable profile copies.

Uses the shared observation service and worker-driven catalog refresh. Screenshots
are offscreen Qt renders of real data, not native Windows visual acceptance.
"""
import argparse
import asyncio
import faulthandler
import json
import time
from importlib import import_module

import live_r10b_inventory_acceptance as inventory
from blueprint_document import decode
from blueprint_encoder import encode_document
from observation_coordinator import STATUS
from observation_service import ObservationService
from qt_observation_bridge import ObservationBridge
from qt_shell import ShellWindow


async def verify_ui(session, report):
    trace=(inventory.harness.EVIDENCE/"ui-stacks.txt").open("w",encoding="utf-8")
    faulthandler.dump_traceback_later(30,repeat=True,file=trace)
    inventory.harness.log("UI_BUILDING_WINDOW")
    QApplication=import_module("PySide6.QtWidgets").QApplication
    app=QApplication.instance() or QApplication([])
    window=ShellWindow()
    window.resize(1600,940)
    window.show_workspace("Recipes")
    window.show()
    service=ObservationService(timeout=12)
    bridge=ObservationBridge(service)
    started=time.monotonic()
    renders=[]
    ticks=[]
    pages=0
    try:
        inventory.harness.log("UI_START_REFRESH")
        bridge.request_catalog(1,page_size=128,refresh=True)
        for _ in range(1024):
            for status_frame in await bridge.poll_once(session):
                window.apply_ui_frame(status_frame)
                if status_frame.kind==STATUS and status_frame.tick is not None:
                    if not ticks or ticks[-1][1]!=status_frame.tick:
                        ticks.append((time.monotonic(),status_frame.tick))
            frame=await bridge.serve_catalog_request(session)
            if frame is None:
                break
            if not frame.observed:
                raise RuntimeError("Catalog refresh failed: "+frame.detail)
            before=time.monotonic()
            window.apply_ui_frame(frame)
            app.processEvents()
            renders.append((time.monotonic()-before)*1000)
            pages+=1
            if pages<=3 or pages%10==0:
                inventory.harness.log(f"UI_CATALOG_PAGES={pages} elapsed={time.monotonic()-started:.1f}s")
        snapshot=window.catalog_widget().snapshot
        report["ui_catalog"]={"pages":pages,"complete":bool(snapshot and snapshot.complete),
            "recipes":len(snapshot.recipes) if snapshot else 0,
            "excluded":len(snapshot.excluded) if snapshot else 0,
            "machines":len(snapshot.machines) if snapshot else 0,
            "seconds":round(time.monotonic()-started,3),
            "apply_ms_max":round(max(renders),3) if renders else None,
            "apply_ms_mean":round(sum(renders)/len(renders),3) if renders else None,
            "tick_rate":inventory.harness.tick_rate(ticks)}
        if snapshot is None or not snapshot.complete:
            raise RuntimeError("Qt did not receive a complete observed catalog")
        window._bridge = bridge
        window.show_workspace("Factory Map")
        map_frame = await bridge.serve_map_request(session)
        if map_frame is None or not map_frame.observed:
            raise RuntimeError("No observed map chunk received")
        window.apply_ui_frame(map_frame)
        app.processEvents()
        scene = window.map_widget().scene
        report["observed_map"] = {"received": True,
            "surface": map_frame.value.get("surface"),
            "scene_built": scene is not None,
            "primitives": len(scene.primitives) if scene else 0,
            "raster_chunks": window.map_widget().stats()["raster_chunks"]}
        if scene is None or not report["observed_map"]["raster_chunks"]:
            raise RuntimeError("Observed map chunk did not produce a visible scene")
        map_image = inventory.harness.EVIDENCE / "factory-map-live.png"
        if not window.grab().save(str(map_image)):
            raise RuntimeError("Map screenshot could not be saved")
        from PIL import Image
        with Image.open(map_image) as image:
            report["observed_map"]["pillow_size"] = list(image.size)
            report["observed_map"]["pillow_colors"] = len(image.convert("RGB").getcolors(2000000) or [])
        window._bridge = None
        window.show_workspace("Recipes")
        planner=window.recipe_widget()
        candidates=[r for r in snapshot.recipes if r.get("enabled") is True
                    and not r.get("hidden") and r.get("simple") is True]
        candidate=next((r for r in candidates if r.get("name")=="iron-gear-wheel"),
                       candidates[0] if candidates else None)
        if candidate is None:
            raise RuntimeError("No observed enabled simple recipe in this test world")
        name=str(candidate["name"])
        planner.catalog.search.setText(name)
        for row in range(planner.catalog.recipe_table.rowCount()):
            if planner.catalog.recipe_table.item(row,0).text()==name:
                planner.catalog.recipe_table.selectRow(row)
                break
        plan=planner.calculate()
        report["ui_plan"]={"recipe":name,"status":plan.get("status") if plan else None,
                           "machine_count":plan.get("machine_count") if plan else None}
        chain = planner.chain
        target = candidate["products"][0]
        chain.output.setText(f"{target['type']}:{target['name']}")
        chain.rate.setValue(60)
        output_amount = float(target["amount"])
        supply_lines = [f"{part['type']}:{part['name']} = {float(part['amount'])/output_amount*60}"
                        for part in candidate["ingredients"]]
        chain.editors["supplies"].setPlainText("\n".join(supply_lines))
        chain_started = chain.calculate()
        chain_deadline = time.monotonic() + 20
        while chain._busy and time.monotonic() < chain_deadline:
            app.processEvents()
            await asyncio.sleep(.02)
        app.processEvents()
        report["observed_chain"] = chain.last_result
        report["observed_chain_pass"] = bool(chain_started and chain.last_result
                                             and chain.last_result.get("status") == "estimated")
        studio=window.blueprint_workspace()
        studio.prompt.clear()
        studio.recipe_choice.setCurrentText(name)
        studio.rate.setValue(60)
        generated=studio.generate()
        document=studio.studio.document
        round_trip=bool(document and decode(encode_document(document))==document)
        report["blueprint_draft"]={"generated":generated,"round_trip":round_trip,
            "scope":"machine layout only; routing/buildability not accepted"}
        app.processEvents()
        image=inventory.harness.EVIDENCE/"qt-live-catalog.png"
        window.grab().save(str(image))
        report["catalog_render"]=str(image)
        # Reuse the shared bridge for bounded logistics, never a per-card poller.
        window.apply_ui_frame(await bridge.poll_inventory(session, machine_page_size=8,
                                                          logistics_page_size=8))
        for ui_frame in await bridge.poll_once(session):
            window.apply_ui_frame(ui_frame)
        window.show_workspace("Overview")
        window.resize(1672, 1000)
        app.processEvents()
        dashboard_image = inventory.harness.EVIDENCE / "qt-live-dashboard.png"
        window.grab().save(str(dashboard_image))
        Image = import_module("PIL.Image")
        with Image.open(dashboard_image) as pixels:
            pixels.load()
            colors = pixels.convert("RGB").getcolors(pixels.width*pixels.height)
            report["pillow_dashboard"] = {"path": str(dashboard_image), "size": list(pixels.size),
                "colors": len(colors or []), "not_blank": len(colors or []) > 100,
                "scope": "Actual observed data rendered offscreen; image check is not gameplay proof"}
        home = window.command_center()
        report["dashboard_fields"] = {key: value.text() for key, value in home.metric_fields.items()}
        model = window.telemetry_widget("Production").model
        report["telemetry_context"] = {"research_active": model.research_active,
            "research_progress": model.research_progress, "pollution_amount": model.pollution_amount,
            "production_status": model.production_status, "power_status": model.power_status,
            "flow_rows": len(model.flows), "network_rows": len(model.networks)}
        report["telemetry_context_pass"] = bool(model.available
            and model.research_active is not None and model.pollution_amount is not None)
        window.apply_disconnect("Acceptance disconnect test")
        disconnected_catalog=window.blueprint_workspace().catalog
        report["disconnect_planning_blocked"]=not bool(disconnected_catalog and disconnected_catalog.complete)
        report["ui_catalog_pass"]=bool(plan and plan.get("status")=="estimated"
            and generated and round_trip and report["disconnect_planning_blocked"]
            and report["observed_chain_pass"] and report["telemetry_context_pass"]
            and report["pillow_dashboard"]["not_blank"])
    except Exception as exc:
        report["ui_catalog_error"]=f"{type(exc).__name__}: {exc}"
        report["ui_catalog_pass"]=False
    finally:
        faulthandler.cancel_dump_traceback_later()
        trace.close()
        window._bridge = None
        window.close()
        service.close()
    return report["ui_catalog_pass"]


async def run(profile):
    original=inventory.verify_inventory
    previous=inventory.harness.EVIDENCE
    evidence=previous/time.strftime("helper-ui-%Y%m%d-%H%M%S")
    inventory.harness.EVIDENCE=evidence
    async def verify(session,report):
        await original(session,report)
        return await verify_ui(session,report)
    inventory.verify_inventory=verify
    try:
        report=await inventory.run(profile)
    finally:
        inventory.verify_inventory=original
        inventory.harness.EVIDENCE=previous
    keys=("profile","ui_catalog","ui_plan","blueprint_draft","disconnect_planning_blocked",
          "ui_catalog_pass","ui_catalog_error","source_save_unchanged","client_stopped",
          "server_stopped","report_path","catalog_render", "observed_chain_pass",
          "observed_chain", "observed_map", "pillow_dashboard", "dashboard_fields", "telemetry_context", "telemetry_context_pass")
    summary={key:report.get(key) for key in keys}
    (evidence/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return bool(report.get("ui_catalog_pass") and report.get("source_save_unchanged"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile",choices=("vanilla","pyanodons"),required=True)
    return 0 if asyncio.run(run(parser.parse_args().profile)) else 1


if __name__=="__main__":
    raise SystemExit(main())
