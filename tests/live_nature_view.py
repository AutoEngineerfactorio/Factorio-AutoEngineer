"""Live READ-ONLY R08 nature verification against the running isolated 2.1.23 game.

Safety contract:
  * Uses the already-running isolated instance that owns the single persistent
    test save ``.local/launcher-profiles/2.1.23/data/saves/autoengineer-test.zip``.
  * Builds the patched backend into a SEPARATE directory so the running
    backend process and the installed backend are never modified.
  * Calls only the read-only MCP tools ``autoengineer_policy`` and
    ``autoengineer_view``. It never calls walk_to_position,
    autoengineer_operation, arm, renew or stop.
  * Never charts, creates, removes or moves anything in the world.
  * Writes only a JSON evidence file under .local/scratch/.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
UPSTREAM = Path(r"D:\AI\Factorio-AutoEngineer\FactorioMCP")
PATCH = ROOT / "backend-safety" / "backend-safety.patch"
PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
SAVE = PROFILE / "data" / "saves" / "autoengineer-test.zip"
# A NEW directory. The running backend's own directory is never touched.
WORK = ROOT / ".local" / "backend-build-r08"
CLONE = WORK / "FactorioMCP"
OUT = ROOT / ".local" / "backend-r08"
EVIDENCE = ROOT / ".local" / "scratch" / "live_nature_evidence.json"

READ_ONLY_CALLS = {"autoengineer_view", "autoengineer_policy"}
EXPECTED_TOOLS = {
    "autoengineer_operation_preview", "autoengineer_operation", "autoengineer_view",
    "autoengineer_policy", "get_player_position", "scan_resources",
    "get_nearby_entities", "walk_to_position", "autoengineer_status",
    "autoengineer_arm", "autoengineer_renew", "autoengineer_stop",
}


def run(argv, cwd, timeout=300):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          timeout=timeout)


def build_backend():
    """Build the patched backend into a separate directory (offline)."""
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    cloned = run(["git", "clone", "--quiet", "--no-hardlinks", str(UPSTREAM),
                  str(CLONE)], ROOT, 120)
    if cloned.returncode:
        raise RuntimeError(f"clone failed: {cloned.stderr[-400:]}")
    applied = run(["git", "apply", str(PATCH)], CLONE)
    if applied.returncode:
        raise RuntimeError(f"patch failed: {applied.stderr[-800:]}")
    project = CLONE / "FactorioMCP" / "FactorioMCP.csproj"
    empty = WORK / "nuget-empty"
    empty.mkdir(exist_ok=True)
    restored = run(["dotnet", "restore", str(project), "--locked-mode", "--source",
                    str(empty), "--verbosity", "quiet"], CLONE, 220)
    if restored.returncode:
        raise RuntimeError(f"restore failed: {(restored.stdout + restored.stderr)[-600:]}")
    built = run(["dotnet", "build", str(project), "-c", "Release", "--no-restore",
                 "--verbosity", "minimal"], CLONE, 300)
    if built.returncode:
        raise RuntimeError(f"build failed: {(built.stdout + built.stderr)[-1200:]}")
    produced = project.parent / "bin" / "Release" / "net9.0"
    if OUT.exists():
        shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(produced, OUT)
    dll = OUT / "FactorioMCP.dll"
    if not dll.is_file():
        raise RuntimeError("patched backend dll missing")
    return dll, built.stdout


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def observe(dll: Path):
    """Call only the read-only MCP tools and return the observed payload."""
    secret = json.loads((PROFILE / "rcon.secret.json").read_text(encoding="utf-8"))
    env = dict(os.environ)
    env["AUTOENGINEER_BACKEND_MODE"] = "helper"
    env["FACTORIO_RCON_HOST"] = env.get("FACTORIO_RCON_HOST", "127.0.0.1")
    env["FACTORIO_RCON_PORT"] = env.get("FACTORIO_RCON_PORT", "27109")
    env["FACTORIO_RCON_PASSWORD"] = secret["rcon_password"]
    params = StdioServerParameters(command="dotnet", args=[str(dll)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            policy_response = await session.call_tool("autoengineer_policy")
            policy = json.loads(next(p.text for p in policy_response.content
                                     if p.type == "text"))
            view_response = await session.call_tool("autoengineer_view")
            raw = next(p.text for p in view_response.content if p.type == "text")
            return names, policy, json.loads(raw)


def main() -> int:
    evidence = {
        "evidence_type": "LIVE READ-ONLY",
        "profile": str(PROFILE),
        "save": str(SAVE),
        "read_only": True,
        "gameplay_performed": False,
    }
    save_before = digest(SAVE)
    evidence["save_sha256_before"] = save_before
    try:
        dll, build_log = build_backend()
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        evidence["status"] = "build_failed"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        return 2
    evidence["backend_dll"] = str(dll)
    evidence["backend_bytes"] = dll.stat().st_size
    evidence["build_ok"] = "Build succeeded" in build_log
    try:
        names, policy, view = asyncio.run(observe(dll))
    except Exception as exc:  # noqa: BLE001 - evidence harness, report everything
        evidence["status"] = "observe_failed"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        evidence["save_sha256_after"] = digest(SAVE)
        evidence["save_unchanged"] = evidence["save_sha256_after"] == save_before
        EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        return 3
    evidence["tool_count"] = len(names)
    evidence["tools"] = names
    evidence["tools_match_policy_v8"] = set(names) == EXPECTED_TOOLS
    evidence["policy"] = policy
    terrain = view.get("terrain", {}) if isinstance(view, dict) else {}
    entities = terrain.get("entities", []) if isinstance(terrain, dict) else []
    nature_entities = [e for e in entities if e.get("kind") == "nature"]
    resource_entities = [e for e in entities if e.get("kind") == "resource"]
    evidence["status"] = "ok"
    evidence["view_status"] = view.get("status") if isinstance(view, dict) else None
    evidence["surface"] = view.get("surface") if isinstance(view, dict) else None
    evidence["tick"] = view.get("tick") if isinstance(view, dict) else None
    # Keep the raw view payload so the visual comparison renders exactly what
    # the dashboard would draw for this observation.
    evidence["observation"] = view
    evidence["entity_count"] = len(entities)
    evidence["nature_count"] = len(nature_entities)
    evidence["nature_entities"] = nature_entities[:24]
    evidence["nature_with_chart_color"] = sum(
        1 for e in nature_entities if e.get("map_color")
    )
    evidence["nature_by_prototype_type"] = {}
    for entity in nature_entities:
        key = entity.get("prototype_type") or entity.get("entity_type") or "unknown"
        evidence["nature_by_prototype_type"][key] = (
            evidence["nature_by_prototype_type"].get(key, 0) + 1
        )
    # The decisive comparison: a prototype whose data-stage map_color is known
    # must report that colour, while a prototype with no map_color at all
    # reports the runtime default. That separates "the game's chart colour"
    # from "the runtime's unset default".
    evidence["nature_distinct_chart_colors"] = sorted({
        json.dumps(e.get("map_color"), sort_keys=True) for e in nature_entities
    })
    evidence["nature_names_sample"] = sorted({
        e.get("name") for e in nature_entities
    })[:20]
    evidence["resource_count"] = len(resource_entities)
    evidence["resource_entities"] = resource_entities[:12]
    evidence["save_sha256_after"] = digest(SAVE)
    evidence["save_unchanged"] = evidence["save_sha256_after"] == save_before
    EVIDENCE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
