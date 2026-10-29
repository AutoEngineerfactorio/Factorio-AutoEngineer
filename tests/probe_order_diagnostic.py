"""Diagnostic: prove the Factorio 2.1.23 console-command gate can be pre-cleared
safely with a harmless read-only probe, before any real command runs.

Starts a FRESH disposable 2.1.23 server, then on the very first RCON
connection sends:
  1. probe  (identical, read-only)   -> expected empty (gate pending)
  2. probe  (identical, read-only)   -> expected to execute
  3. real read-only command           -> expected to execute, no repeat
  4. a second, different real command -> expected to execute, no repeat

Only read-only Lua is used. No game state is modified.
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
    run_save = EVIDENCE / "probe-order-save.zip"
    shutil.copy2(m["save"], run_save)
    password = secrets.token_hex(32)
    log_path = EVIDENCE / "probe-order-factorio.log"
    game_port, rcon_port = 34243, 27143

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
        report["auth_ok"] = rid != -1
        log(f"AUTH_OK={report['auth_ok']}")

        # The probe is the VERY FIRST command on a FRESH server.
        probe = "/silent-command rcon.print('PROBE')"
        report["probe_first"] = rcon_exec(sock, probe, 2)
        report["probe_second"] = rcon_exec(sock, probe, 3)
        log(f"PROBE_FIRST={report['probe_first']!r}")
        log(f"PROBE_SECOND={report['probe_second']!r}")

        report["real_first"] = rcon_exec(
            sock, "/silent-command rcon.print('REAL1=' .. tostring(game.tick))", 4)
        report["real_second"] = rcon_exec(
            sock, "/silent-command rcon.print('REAL2=' .. tostring(game.tick))", 5)
        log(f"REAL_FIRST={report['real_first']!r}")
        log(f"REAL_SECOND={report['real_second']!r}")

        report["gate_cleared"] = (
            report["probe_first"] == ""
            and report["probe_second"].strip() == "PROBE"
            and report["real_first"].strip().startswith("REAL1=")
            and report["real_second"].strip().startswith("REAL2=")
        )
        log(f"GATE_CLEARED_BY_PROBE={report['gate_cleared']}")

        text = log_path.read_text(encoding="utf-8", errors="replace")
        report["console_warning_count"] = text.count("Using Lua console commands")
        report["console_warnings"] = [
            line[:220] for line in text.splitlines()
            if "Using Lua console commands" in line
        ]
        log(f"CONSOLE_WARNING_COUNT={report['console_warning_count']}")
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
        (EVIDENCE / "probe-order.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        log("EVIDENCE=" + str(EVIDENCE / "probe-order.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
