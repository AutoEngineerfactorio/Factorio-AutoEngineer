"""LIVE READ-ONLY probe: what does Factorio 2.1.23 actually return for decoratives?

The 2.1.23 runtime API documents ``LuaSurface::find_decoratives_filtered`` but
exposes **no** ``LuaDecorative`` class: only ``LuaDecorativePrototype``. This
probe asks the running game directly, with a read-only ``rcon.print`` of the
returned object's fields, so the decorative support is built on what the
runtime really returns and not on a guess.

Safety contract:
* It sends exactly one read-only Lua expression that prints a description.
  No console command creates, changes, charts or removes anything.
* It never writes to the save; the digest is compared before and after.
* It never starts or stops Factorio.

Usage:
    python -B tests/live_r08d_decorative_probe.py
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROFILE = ROOT / ".local" / "launcher-profiles" / "2.1.23"
CONFIG = PROFILE / "config.ini"
SAVE = PROFILE / "data" / "saves" / "autoengineer-test.zip"
OUTPUT = ROOT / ".local" / "live-pillow-2.1.23" / "evidence" / "r08d-decorative-live.json"

SERVERDATA_EXECCOMMAND = 2
SERVERDATA_AUTH_RESPONSE = 2
SERVERDATA_RESPONSE_VALUE = 0


def log(message: str) -> None:
    print(str(message), flush=True)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pack(request_id: int, kind: int, body: str) -> bytes:
    payload = struct.pack("<ii", request_id, kind) + body.encode("utf-8") + b"\x00\x00"
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


def rcon_exec(sock, command: str, request_id: int) -> str:
    import time

    sock.sendall(pack(request_id, SERVERDATA_EXECCOMMAND, command))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        sock.settimeout(max(0.5, deadline - time.monotonic()))
        try:
            rid, ptype, body = read_packet(sock)
        except (TimeoutError, socket.timeout, ConnectionError):
            break
        if rid == request_id and ptype == SERVERDATA_RESPONSE_VALUE:
            return body
    return ""


def read_socket() -> tuple[str, int, str]:
    text = CONFIG.read_text(encoding="utf-8")
    socket_match = re.search(r"local-rcon-socket=(\S+)", text)
    password_match = re.search(r"local-rcon-password=(\S+)", text)
    if not socket_match or not password_match:
        raise SystemExit("RCON socket or password not found in config.ini")
    host, port = socket_match.group(1).rsplit(":", 1)
    return host, int(port), password_match.group(1)


def main() -> int:
    before = digest(SAVE)
    log(f"SAVE_DIGEST_BEFORE={before}")
    host, port, password = read_socket()
    report: dict = {"save_digest_before": before}

    sock = socket.create_connection((host, port), timeout=10)
    sock.sendall(pack(1, 3, password))
    read_packet(sock)

    # A read-only expression. It only reads the surface and prints a
    # description of what find_decoratives_filtered returned.
    lua = (
        "local p=game.get_player(1);"
        "local s=p.surface;"
        "local d=s.find_decoratives_filtered{area={{p.position.x-8,p.position.y-8},"
        "{p.position.x+8,p.position.y+8}},limit=5};"
        "local out='DECOR_COUNT=' .. tostring(#d);"
        "for i=1,math.min(#d,3) do"
        "  local o=d[i];"
        "  local parts={};"
        "  for k,v in pairs(o) do"
        "    if type(v)=='number' or type(v)=='string' or type(v)=='boolean' then"
        "      parts[#parts+1]=tostring(k)..'='..tostring(v)"
        "    end"
        "  end;"
        "  out=out .. ' | ITEM' .. tostring(i) .. ' TYPE=' .. type(o);"
        "  out=out .. ' FIELDS=' .. table.concat(parts,',')"
        "end;"
        "rcon.print(out)"
    )
    command = "/silent-command " + lua
    report["command"] = command
    response = rcon_exec(sock, command, 2)
    report["response"] = response
    log(f"DECOR_RESPONSE={response}")

    # Also record what a single decorative's prototype offers.
    lua2 = (
        "local p=game.get_player(1);"
        "local s=p.surface;"
        "local d=s.find_decoratives_filtered{area={{p.position.x-8,p.position.y-8},"
        "{p.position.x+8,p.position.y+8}},limit=1};"
        "local out='DECOR_PROTO=';"
        "if #d>0 then "
        "  local ok,proto=pcall(function() return d[1].prototype end);"
        "  if ok and proto then "
        "    out=out .. 'name=' .. tostring(proto.name);"
        "    out=out .. ' type=' .. tostring(proto.type);"
        "    local cok,col=pcall(function() return proto.map_color end);"
        "    out=out .. ' map_color_ok=' .. tostring(cok);"
        "    out=out .. ' decal=' .. tostring(proto.decal)"
        "  else "
        "    out=out .. 'NO_PROTOTYPE'"
        "  end "
        "end;"
        "rcon.print(out)"
    )
    response2 = rcon_exec(sock, "/silent-command " + lua2, 3)
    report["prototype_response"] = response2
    log(f"DECOR_PROTO_RESPONSE={response2}")

    sock.close()

    after = digest(SAVE)
    report["save_digest_after"] = after
    report["save_unchanged"] = before == after
    log(f"SAVE_DIGEST_AFTER={after}")
    log(f"SAVE_UNCHANGED={before == after}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log(f"WROTE={OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
