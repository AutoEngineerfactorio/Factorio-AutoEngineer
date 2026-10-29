"""Diagnostic: does Factorio 2.1.23 require an identical repeated RCON console command?

Read-only diagnostic. It starts the disposable isolated 2.1.23 server, sends a
trivial read-only Lua command over raw RCON, and records the exact response
body. It then repeats the identical command and records the second response.

Nothing is written to the game world. The only command sent is a read of
game.tick and script.active_mods["base"].
"""
import json
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\AI\Factorio-AutoEngineer-Source")
BASE = ROOT / ".local" / "live-pillow-2.1.23"
EVIDENCE = BASE / "evidence"

SERVERDATA_AUTH = 3
SERVERDATA_EXECCOMMAND = 2
SERVERDATA_RESPONSE_VALUE = 0


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
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        rid, ptype, body = read_packet(sock)
        if rid == request_id and ptype == SERVERDATA_RESPONSE_VALUE:
            return body
    raise TimeoutError("no response")


def main():
    m = json.loads((BASE / "profile_manifest.json").read_text(encoding="utf-8"))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_save = EVIDENCE / "rcon-diagnostic-save.zip"
    shutil.copy2(m["save"], run_save)
    password = secrets.token_hex(32)
    log_path = EVIDENCE / "rcon-diagnostic-factorio.log"
    game_port, rcon_port = 34241, 27141

    out = log_path.open("w", encoding="utf-8")
    err = log_path.with_suffix(".err.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([
        m["exe"], "--config", m["config"], "--mod-directory", m["mods"],
        "--start-server", str(run_save), "--server-settings", m["server_settings"],
        "--bind", f"127.0.0.1:{game_port}", "--rcon-bind", f"127.0.0.1:{rcon_port}",
        "--rcon-password", password,
    ], stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    report: dict = {"pid": proc.pid}
    try:
        started, ready = time.monotonic(), False
        while time.monotonic() - started < 90:
            if proc.poll() is not None:
                break
            text = log_path.read_text(encoding="utf-8", errors="replace")
            if "Starting RCON interface" in text:
                ready = True
                break
            time.sleep(0.6)
        report["server_ready"] = ready
        log(f"SERVER_READY={ready}")
        if not ready:
            return 4

        sock = socket.create_connection(("127.0.0.1", rcon_port), timeout=20)
        sock.sendall(pack(1, SERVERDATA_AUTH, password))
        rid, ptype, body = read_packet(sock)
        if rid == -1:
            log("AUTH_FAILED")
            return 5
        log("AUTH_OK")

        lua = "rcon.print('TICK=' .. tostring(game.tick) .. ' BASE=' .. tostring(script.active_mods['base']))"
        cmd = "/silent-command " + lua
        report["command"] = cmd

        first = rcon_exec(sock, cmd, 2)
        report["first_response"] = first
        log(f"FIRST_RESPONSE={first!r}")

        second = rcon_exec(sock, cmd, 3)
        report["second_response"] = second
        log(f"SECOND_RESPONSE={second!r}")

        third = rcon_exec(sock, cmd, 4)
        report["third_response"] = third
        log(f"THIRD_RESPONSE={third!r}")

        # A DIFFERENT command must also be repeated: the gate is per-command,
        # not a one-time server acknowledgement.
        other = "/silent-command rcon.print('OTHER=' .. tostring(game.tick))"
        report["other_first_response"] = rcon_exec(sock, other, 5)
        report["other_second_response"] = rcon_exec(sock, other, 6)
        log(f"OTHER_FIRST={report['other_first_response']!r}")
        log(f"OTHER_SECOND={report['other_second_response']!r}")

        # Does a RECONNECT reset the gate? A fresh connection should require a repeat again.
        sock2 = socket.create_connection(("127.0.0.1", rcon_port), timeout=20)
        sock2.sendall(pack(1, SERVERDATA_AUTH, password))
        rid2, ptype2, body2 = read_packet(sock2)
        report["reconnect_auth_ok"] = rid2 != -1
        fresh = "/silent-command rcon.print('FRESH=' .. tostring(game.tick))"
        report["reconnect_first_response"] = rcon_exec(sock2, fresh, 2)
        report["reconnect_second_response"] = rcon_exec(sock2, fresh, 3)
        log(f"RECONNECT_FIRST={report['reconnect_first_response']!r}")
        log(f"RECONNECT_SECOND={report['reconnect_second_response']!r}")
        sock2.close()

        # A command that legitimately prints nothing: what does the server return?
        empty = "/silent-command local nothing = 1"
        report["empty_first_response"] = rcon_exec(sock, empty, 7)
        report["empty_second_response"] = rcon_exec(sock, empty, 8)
        log(f"EMPTY_FIRST={report['empty_first_response']!r}")
        log(f"EMPTY_SECOND={report['empty_second_response']!r}")

        text = log_path.read_text(encoding="utf-8", errors="replace")
        report["log_tail"] = text.splitlines()[-8:]
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
        try:
            run_save.unlink()
        except OSError:
            pass
        (EVIDENCE / "rcon-diagnostic.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        log("EVIDENCE=" + str(EVIDENCE / "rcon-diagnostic.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
