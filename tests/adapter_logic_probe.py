"""Live probe: replicate the adapter's exact row validation in 2.1.23.

Runs the same normalized_parts / row acceptance logic as
backend-safety/Tools/RecipeResearchAdapter.cs against the real 2.1.23 game and
reports which condition rejects each sampled recipe.

Read-only: only game reads and rcon.print.
"""
import json
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r"D:\AI\Factorio-AutoEngineer-Source\.local\live-pillow-2.1.23")
EVIDENCE = BASE / "evidence"
SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0

LUA = r"""
local out = {}
local function add(k, v) out[#out+1] = {name=k, value=v} end

-- Mirror of the adapter's normalized_parts with the 2.1 product allowance.
local function normalized_parts(source, limit, is_product)
    if type(source) ~= "table" then return nil, "source_not_table" end
    local result, count = {}, 0
    for key, part in pairs(source) do
        if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then return nil, "bad_key" end
        count = count + 1
        if count > limit then return nil, "over_limit" end
        if type(part) ~= "table" or type(part.name) ~= "string"
            or #part.name < 1 or #part.name > 128
            or (part.type ~= "item" and part.type ~= "fluid")
            or type(part.amount) ~= "number" or part.amount <= 0
            or part.amount ~= part.amount or part.amount == math.huge then
            return nil, "bad_part"
        end
        local deterministic = true
        for field, value in pairs(part) do
            if field == "name" or field == "type" or field == "amount" then
            elseif not is_product then
                return nil, "ingredient_extra_field:" .. tostring(field)
            elseif field == "affected_by_quality" then
                if type(value) ~= "boolean" then return nil, "abq_bad_type" end
            elseif field == "independent_probability" or field == "shared_probability" then
                if type(value) ~= "number" or value ~= value
                    or value < 0 or value > 1 or value == math.huge then return nil, "prob_bad" end
                if value < 1 then deterministic = false end
            else
                return nil, "unknown_field:" .. tostring(field)
            end
        end
        local row = {name=part.name, type=part.type, amount=part.amount}
        if not deterministic then row.deterministic = false end
        result[#result+1] = row
    end
    if count ~= #source then return nil, "count_mismatch" end
    table.sort(result, function(a,b)
        if a.name ~= b.name then return a.name < b.name end
        if a.type ~= b.type then return a.type < b.type end
        return a.amount < b.amount
    end)
    return result, "ok"
end

local samples = {"iron-plate","iron-gear-wheel","copper-cable","advanced-circuit","electronic-circuit","steel-plate"}
-- Apply the CORRECTED adapter rules and report the residual rejection reasons.
do
    local reasons = {}
    local function bump(k) reasons[k] = (reasons[k] or 0) + 1 end
    local accepted, total = 0, 0
    local known = {
        name=true, type=true, amount=true,
        affected_by_quality=true, independent_probability=true, shared_probability=true,
        ignored_by_stats=true, spoil_weight=true, fluidbox_multiplier=true, fluidbox_index=true,
    }
    for name in pairs(game.forces.player.recipes) do
        total = total + 1
        local r = game.forces.player.recipes[name]
        local ok = true
        local cats = r.categories
        local cat = nil
        if type(cats) == "table" and #cats > 0 and #cats <= 8 then
            cat = cats[1]
            for i = 1, #cats do
                if type(cats[i]) ~= "string" or #cats[i] < 1 or #cats[i] > 128 then
                    cat = nil break
                end
            end
        end
        if not cat then bump("no_valid_category"); ok = false end
        if type(r.energy) ~= "number" or r.energy <= 0 then bump("bad_energy"); ok = false end
        if #r.ingredients > 16 then bump("too_many_ingredients"); ok = false end
        if #r.products > 8 then bump("too_many_products"); ok = false end
        if #r.products == 0 then bump("no_products"); ok = false end
        for _, part in ipairs(r.ingredients) do
            for field in pairs(part) do
                if not known[field] then bump("ingredient_unknown:" .. tostring(field)); ok = false end
            end
            if type(part.amount) ~= "number" or part.amount <= 0 then
                bump("ingredient_bad_amount"); ok = false
            end
            if part.type ~= "item" and part.type ~= "fluid" then
                bump("ingredient_bad_type"); ok = false
            end
        end
        for _, part in ipairs(r.products) do
            for field in pairs(part) do
                if not known[field] then bump("product_unknown:" .. tostring(field)); ok = false end
            end
            if type(part.amount) ~= "number" or part.amount < 0 then
                bump("product_bad_amount"); ok = false
            end
            if part.type ~= "item" and part.type ~= "fluid" then
                bump("product_bad_type"); ok = false
            end
        end
        if ok then accepted = accepted + 1 end
    end
    local list = {}
    for k, v in pairs(reasons) do list[#list+1] = {reason=k, count=v} end
    table.sort(list, function(a,b) if a.count ~= b.count then return a.count > b.count end return a.reason < b.reason end)
    add("RESIDUAL_REJECTIONS", {total=total, accepted=accepted, reasons=list})
end
-- Count why each recipe would be rejected, using the corrected rules.
do
    local reasons = {}
    local function bump(k) reasons[k] = (reasons[k] or 0) + 1 end
    local accepted = 0
    for name in pairs(game.forces.player.recipes) do
        local r = game.forces.player.recipes[name]
        local cats = r.categories
        local cat = (type(cats) == "table" and #cats == 1) and cats[1] or nil
        local ok = true
        if not cat then bump("no_single_category"); ok = false end
        if type(r.energy) ~= "number" or r.energy <= 0 then bump("bad_energy"); ok = false end
        -- ingredients: only name/type/amount allowed
        for _, part in ipairs(r.ingredients) do
            for field in pairs(part) do
                if field ~= "name" and field ~= "type" and field ~= "amount" then
                    bump("ingredient_extra:" .. tostring(field)); ok = false
                end
            end
            if type(part.amount) ~= "number" or part.amount <= 0 then
                bump("ingredient_bad_amount"); ok = false
            end
        end
        if #r.ingredients > 16 then bump("too_many_ingredients"); ok = false end
        if #r.products > 8 then bump("too_many_products"); ok = false end
        for _, part in ipairs(r.products) do
            if type(part.amount) ~= "number" or part.amount <= 0 then
                bump("product_bad_amount"); ok = false
            end
        end
        if ok then accepted = accepted + 1 end
    end
    bump("ACCEPTED_WOULD_BE")
    local list = {}
    for k, v in pairs(reasons) do list[#list+1] = {reason=k, count=v} end
    table.sort(list, function(a,b) if a.count ~= b.count then return a.count > b.count end return a.reason < b.reason end)
    add("REJECT_REASONS", list)
end
-- Measure the real value ranges of the 2.1 product fields.
do
    local ranges = {affected_by_quality={types={},count=0},
        independent_probability={min=math.huge,max=-math.huge,types={},count=0},
        shared_probability={min=math.huge,max=-math.huge,types={},count=0}}
    for name in pairs(game.forces.player.recipes) do
        for _, part in ipairs(game.forces.player.recipes[name].products) do
            for field, value in pairs(part) do
                if ranges[field] then
                    local r = ranges[field]
                    r.count = r.count + 1
                    r.types[type(value)] = (r.types[type(value)] or 0) + 1
                    if type(value) == "number" then
                        if value < r.min then r.min = value end
                        if value > r.max then r.max = value end
                    end
                end
            end
        end
    end
    add("FIELD_RANGES", ranges)
    -- Shape of the shared_probability table.
    do
        local shapes, sample = {}, nil
        for name in pairs(game.forces.player.recipes) do
            for _, part in ipairs(game.forces.player.recipes[name].products) do
                local sp = part.shared_probability
                if type(sp) == "table" then
                    local keys = {}
                    for k in pairs(sp) do
                        local kt = type(sp[k])
                        local entry = tostring(k) .. ":" .. kt
                        if kt == "number" then entry = entry .. "=" .. tostring(sp[k])
                        elseif kt == "table" then
                            local inner = {}
                            for ik in pairs(sp[k]) do inner[#inner+1] = tostring(ik) end
                            table.sort(inner)
                            entry = entry .. "{" .. table.concat(inner, ",") .. "}"
                        end
                        keys[#keys+1] = entry
                    end
                    table.sort(keys)
                    local shape = table.concat(keys, ",")
                    shapes[shape] = (shapes[shape] or 0) + 1
                    if not sample then
                        sample = {recipe=name, product=part.name, shape=shape}
                    end
                end
            end
        end
        local list = {}
        for shape, n in pairs(shapes) do list[#list+1] = {shape=shape, count=n} end
        table.sort(list, function(a,b) return a.shape < b.shape end)
        add("SHARED_PROBABILITY_SHAPES", list)
        add("SHARED_PROBABILITY_SAMPLE", sample)
    end
end
for _, rname in ipairs(samples) do
    local r = game.forces.player.recipes[rname]
    local row = {name=rname}
    if not r then
        row.result = "missing"
    else
        local cats = r.categories
        row.categories = cats
        row.category_count = type(cats) == "table" and #cats or -1
        row.category = (type(cats) == "table" and #cats == 1) and cats[1] or nil
        local ing, ing_reason = normalized_parts(r.ingredients, 16, false)
        local prod, prod_reason = normalized_parts(r.products, 8, true)
        row.ingredients_reason = ing_reason
        row.products_reason = prod_reason
        row.energy = r.energy
        row.accepted = (ing ~= nil and prod ~= nil and #prod > 0
            and type(r.energy) == "number" and type(row.category) == "string"
            and #row.category > 0 and #row.category <= 128
            and r.energy > 0)
        row.accepted_reason = row.accepted and "accepted"
            or (ing == nil and ("ingredients:" .. tostring(ing_reason))
                or (prod == nil and ("products:" .. tostring(prod_reason))
                or (type(row.category) ~= "string" and "category_not_single_string"
                or "other")))
    end
    add(rname, row)
end
rcon.print(helpers.table_to_json(out))
"""


def log(m):
    print(str(m), flush=True)


def pack(request_id, packet_type, body):
    payload = struct.pack("<ii", request_id, packet_type) + body.encode("utf-8") + b"\x00\x00"
    return struct.pack("<i", len(payload)) + payload


def read_packet(sock):
    header = b""
    while len(header) < 4:
        chunk = sock.recv(4 - len(header))
        if not chunk:
            raise ConnectionError("closed")
        header += chunk
    size = struct.unpack("<i", header)[0]
    payload = b""
    while len(payload) < size:
        chunk = sock.recv(size - len(payload))
        if not chunk:
            raise ConnectionError("closed")
        payload += chunk
    request_id, packet_type = struct.unpack("<ii", payload[:8])
    return request_id, packet_type, payload[8:-2].decode("utf-8", errors="replace")


def rcon_exec(sock, command, request_id):
    sock.sendall(pack(request_id, SERVERDATA_EXECCOMMAND, command))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        rid, ptype, body = read_packet(sock)
        if rid == request_id and ptype == SERVERDATA_RESPONSE_VALUE:
            return body
    raise TimeoutError("no response")


def main():
    m = json.loads((BASE / "profile_manifest.json").read_text(encoding="utf-8"))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_save = EVIDENCE / "adapter-logic-save.zip"
    shutil.copy2(m["save"], run_save)
    password = secrets.token_hex(32)
    log_path = EVIDENCE / "adapter-logic-factorio.log"
    game_port, rcon_port = 34257, 27157

    run_config = EVIDENCE / "adapter-logic-config.ini"
    text = Path(m["config"]).read_text(encoding="utf-8-sig")
    text = re.sub(r"(?m)^local-rcon-socket=.*$",
                  f"local-rcon-socket=127.0.0.1:{rcon_port}", text)
    text = re.sub(r"(?m)^local-rcon-password=.*$",
                  f"local-rcon-password={password}", text)
    run_config.write_text(text, encoding="utf-8")

    out = log_path.open("w", encoding="utf-8")
    err = log_path.with_suffix(".err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([
        m["exe"], "--config", str(run_config), "--mod-directory", m["mods"],
        "--host", str(run_save), "--server-settings", m["server_settings"],
        "--bind", f"127.0.0.1:{game_port}",
    ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        started, ready = time.monotonic(), False
        while time.monotonic() - started < 420:
            if proc.poll() is not None:
                break
            body = log_path.read_text(encoding="utf-8", errors="replace")
            if "Hosting game at IP" in body and "Starting RCON interface" in body:
                ready = True
                break
            time.sleep(0.6)
        log("SERVER_READY=" + str(ready))
        if not ready:
            return 4
        sock = socket.create_connection(("127.0.0.1", rcon_port), timeout=30)
        sock.sendall(pack(1, SERVERDATA_AUTH, password))
        read_packet(sock)
        command = "/silent-command " + LUA
        rcon_exec(sock, command, 2)
        body = rcon_exec(sock, command, 3)
        try:
            parsed = json.loads(body)
        except ValueError:
            log("PARSE_FAILED=" + body[:600])
            return 5
        for entry in parsed:
            log(f"{entry['name']}: {json.dumps(entry['value'], sort_keys=True)}")
        sock.close()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        out.close()
        err.close()
        for path in (run_save, run_config):
            try:
                path.unlink()
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
