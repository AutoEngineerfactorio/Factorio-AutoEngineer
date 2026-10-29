"""Scratch probe: is the new backend budget test discriminating?

Runs the SAME Lua harness over two backends:

* the current backend-safety/AutoEngineerTools.cs (with the chunk budget),
* the pre-change merge loop taken from git HEAD (no chunk budget).

The scenario is four 32x32 sub-windows that each hold 600 entities: every
sub-window is under the per-window limit of 2048, but the merged chunk count
of 2400 exceeds the chunk budget of 2048. The old code must report the
chunk as complete, the new code must report it as partial.
"""
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_backend_adapter_contract import (  # noqa: E402
    ChunkEntityBudgetContractTests,
)

case = ChunkEntityBudgetContractTests(
    "test_the_chunk_budget_is_a_separate_documented_bound"
)
case.setUp()

OLD_LUA = """
local MAP_CHUNK_TILES=64
local MAP_CHUNK_ENTITY_LIMIT=2048
local MAP_CHUNK_WINDOW_TILES=32
local ox=0
local oy=0
local partial=false
local chunk_complete=true
local window_counts={}
local function fake_find_entities_filtered(opts)
    local a=opts.area
    local key=(a[1][1])..","..(a[1][2])..":"..(a[2][1]-a[1][1]).."x"..(a[2][2]-a[1][2])
    local held=window_counts[key] or 0
    local limit=opts.limit or held
    local count=held
    if count>limit then count=limit end
    local rows={}
    for i=1,count do rows[i]={name="entity-"..key.."-"..i} end
    return rows
end
local c={surface={find_entities_filtered=fake_find_entities_filtered}}
local p={force={name="player"}}
local groups={
    {kind="resource",types={"resource"},limit=MAP_CHUNK_ENTITY_LIMIT,windowed=true},
    {kind="nature",types={"tree","simple-entity","cliff"},limit=MAP_CHUNK_ENTITY_LIMIT,windowed=true},
    {kind="building",force=p.force.name,limit=256},
    {kind="enemy",force="enemy",limit=128}}
for _,g in ipairs(groups) do
    local found={}
    local windows
    if g.windowed then
        windows={}
        for wy=oy,oy+MAP_CHUNK_TILES-MAP_CHUNK_WINDOW_TILES,MAP_CHUNK_WINDOW_TILES do
            for wx=ox,ox+MAP_CHUNK_TILES-MAP_CHUNK_WINDOW_TILES,MAP_CHUNK_WINDOW_TILES do
                windows[#windows+1]={{wx,wy},{wx+MAP_CHUNK_WINDOW_TILES,wy+MAP_CHUNK_WINDOW_TILES}}
            end
        end
    else
        windows={{{ox,oy},{ox+MAP_CHUNK_TILES,oy+MAP_CHUNK_TILES}}}
    end
    for _,window in ipairs(windows) do
        local part=c.surface.find_entities_filtered{area=window,
            type=g.types,force=g.force,limit=g.limit+1}
        if #part>g.limit then partial=true;chunk_complete=false end
        if #found>g.limit then partial=true;chunk_complete=false end
        for i=1,math.min(#part,g.limit) do found[#found+1]=part[i] end
    end
end
return {partial=partial,chunk_complete=chunk_complete}
"""

COUNTS = (
    'local window_counts={["0,0:32x32"]=600,["32,0:32x32"]=600,'
    '["0,32:32x32"]=600,["32,32:32x32"]=600}'
)


def run(program):
    import lupa

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    result = cast(Any, lua.execute(program))
    return bool(result["partial"]), bool(result["chunk_complete"])


old_partial, old_complete = run(OLD_LUA.replace("local window_counts={}", COUNTS))
print("OLD backend (no chunk budget), 4x600 entities:")
print("  partial =", old_partial, " chunk_complete =", old_complete)

new_program = case._lua_program(case.tools).replace(
    "local window_counts={}", COUNTS
)
new_partial, new_complete = run(new_program)
print("NEW backend (chunk budget), 4x600 entities:")
print("  partial =", new_partial, " chunk_complete =", new_complete)

print()
print("merged count = 2400, chunk budget = 2048")
if old_complete and not new_complete:
    print("DISCRIMINATING: the old backend reported the overflowing chunk as "
          "complete, the new backend reports it as partial.")
else:
    print("NOT DISCRIMINATING: old_complete=%s new_complete=%s"
          % (old_complete, new_complete))
