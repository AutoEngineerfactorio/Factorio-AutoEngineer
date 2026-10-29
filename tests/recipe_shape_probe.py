"""Live read-only probe of the raw 2.1.23 recipe shape.

Answers, with real observations only, why the adapter rejected every recipe row:
which field of a real recipe fails the adapter's strict validation.

Uses the disposable 2.1.23 graphical host and raw RCON with read-only Lua.
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

LUA = """
local out = {}
local function add(name, value) out[#out+1] = {name=name, value=value} end
local samples = {"iron-plate","iron-gear-wheel","copper-cable","advanced-circuit","electronic-circuit"}
for _, rname in ipairs(samples) do
    local r = game.forces.player.recipes[rname]
    if r then
        add(rname .. ".categories", r.categories)
        add(rname .. ".hidden", r.hidden)
        add(rname .. ".enabled", r.enabled)
        add(rname .. ".energy", r.energy)
        local ing = {}
        for i, part in ipairs(r.ingredients) do
            local keys = {}
            for k in pairs(part) do keys[#keys+1] = k end
            table.sort(keys)
            ing[i] = {name=part.name, type=part.type, amount=part.amount, keys=keys}
        end
        add(rname .. ".ingredients", ing)
        local prod = {}
        for i, part in ipairs(r.products) do
            local keys = {}
            for k in pairs(part) do keys[#keys+1] = k end
            table.sort(keys)
            prod[i] = {name=part.name, type=part.type, amount=part.amount, keys=keys}
        end
        add(rname .. ".products", prod)
    else
        add(rname, "MISSING")
    end
end
local counts = {recipes=0, multi_category=0, single_category=0, no_category=0,
    product_extra_fields=0, ingredient_extra_fields=0, hidden=0, disabled=0}
for name in pairs(game.forces.player.recipes) do
    local r = game.forces.player.recipes[name]
    counts.recipes = counts.recipes + 1
    local ncat = type(r.categories) == "table" and #r.categories or 0
    if ncat > 1 then counts.multi_category = counts.multi_category + 1
    elseif ncat == 1 then counts.single_category = counts.single_category + 1
    else counts.no_category = counts.no_category + 1 end
    if r.hidden then counts.hidden = counts.hidden + 1 end
    if not r.enabled then counts.disabled = counts.disabled + 1 end
    for _, part in ipairs(r.products) do
        for k in pairs(part) do
            if k ~= "name" and k ~= "type" and k ~= "amount" then
                counts.product_extra_fields = counts.product_extra_fields + 1
                break
            end
        end
    end
    for _, part in ipairs(r.ingredients) do
        for k in pairs(part) do
            if k ~= "name" and k ~= "type" and k ~= "amount" then
                counts.ingredient_extra_fields = counts.ingredient_extra_fields + 1
                break
            end
        end
    end
end
add("COUNTS", counts)
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
    run_save = EVIDENCE / "recipe-shape-save.zip"
    shutil.copy2(m["save"], run_save)
    password = secrets.token_hex(32)
    log_path = EVIDENCE / "recipe-shape-factorio.log"
    game_port, rcon_port = 34253, 27153

    run_config = EVIDENCE / "recipe-shape-config.ini"
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
        # The first command on a fresh server is gated: send twice.
        command = "/silent-command " + LUA
        first = rcon_exec(sock, command, 2)
        second = rcon_exec(sock, command, 3)
        log("FIRST_LEN=" + str(len(first)))
        log("SECOND_LEN=" + str(len(second)))
        body = second if second.strip() else first
        try:
            parsed = json.loads(body)
        except ValueError:
            log("PARSE_FAILED=" + body[:400])
            return 5
        for entry in parsed:
            log(f"{entry['name']} = {json.dumps(entry['value'], sort_keys=True)[:900]}")
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
