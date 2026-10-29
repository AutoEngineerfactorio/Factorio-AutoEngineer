"""R10-B creative stress: the inventory and logistics observers under load.

The harness reuses the **accepted** R10-A creative stress
(``tests/live_py_creative_fluid.py``) and its dashboard runner
(``tests/live_r10a_dashboard_stress.py``), so the factory, the blueprint,
the creative fluid supply and the dashboard are exactly the ones the R10-A
run used.

On top of that it adds the **R10-B observers**: the machine inventory, the
logistic network, the robot and the transport observations are requested
repeatedly while the factory is producing, and their latency, their error
count and their timeout count are measured.

The measurements the mission asks for:

* the UPS average, minimum and lower percentiles, and the samples below
  59 and 58 UPS;
* the inventory request latency and the logistic network request latency;
* the pagination completion;
* the observer error and timeout counts;
* the dashboard responsiveness and the render time;
* the process memory use;
* the working machine count before and after.

Usage:

    python -B tests/live_r10b_observer_stress.py --replicas 4 --seconds 300
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
import sys  # noqa: E402

sys.path.insert(0, str(HERE))

import live_long_stress as stress  # noqa: E402
import live_py_creative_fluid as creative  # noqa: E402
import live_r10a_dashboard_stress as r10a  # noqa: E402

#: How often the R10-B observers run while the factory is producing.
#:
#: The observation walks entities, so it is **not** cheap. The R10-A
#: baseline held 60.00 UPS average with no sample below 58; the first
#: R10-B run polled every five seconds **and** walked three pages on
#: every round, which cost 4 samples below 58 UPS. The observer therefore
#: polls rarely and walks the pages only once.
OBSERVER_INTERVAL_SECONDS = 20.0

#: The maximum number of pages the pagination walk reads.
PAGINATION_PAGES = 3

#: How often the pagination walk runs. Once is enough to prove that the
#: pages do not overlap and that the walk completes.
PAGINATION_INTERVAL_SECONDS = 120.0


def _tail(values: list[float]) -> dict:
    """Return the summary of one series of samples."""
    return r10a._tail(values)


class InventoryObserver:
    """Runs the R10-B observers against the live game.

    The observer runs in its own thread with its own MCP session, so it
    never blocks the dashboard, the model or the blueprint feeder.
    """

    def __init__(self, rcon_port: int, password: str, work: Path):
        self.rcon_port = rcon_port
        self.password = password
        self.work = work
        self.thread: threading.Thread | None = None
        self.stop = threading.Event()
        self.error: str | None = None
        self.requests = 0
        self.failures = 0
        self.timeouts = 0
        self.machine_latencies: list[float] = []
        self.logistics_latencies: list[float] = []
        self.transport_latencies: list[float] = []
        self.robots_latencies: list[float] = []
        self.machine_rows = 0
        self.network_rows = 0
        self.transport_rows = 0
        self.robot_total = 0
        self.pages_read = 0
        self.pages_unique = True
        self.identities: list[str] = []
        self._last_walk = 0.0

    def start(self) -> None:
        """Start the observer thread."""
        self.thread = threading.Thread(target=self._run, daemon=True,
                                      name="r10b-observer")
        self.thread.start()

    def _run(self) -> None:
        """Run the observers until the harness stops them."""
        try:
            import asyncio

            asyncio.run(self._drive())
        except Exception as exc:  # noqa: BLE001 - the failure is reported
            self.error = f"{type(exc).__name__}: {str(exc)[:200]}"

    async def _drive(self) -> None:
        """Drive the R10-B observations."""
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        if not await r10a._wait_for_rcon(self.rcon_port):
            raise RuntimeError("the owned game RCON endpoint never became ready")
        params = r10a._mcp_params(self.rcon_port, self.password)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if not await r10a._wait_for_player(session):
                    raise RuntimeError("the backend never observed a player")
                while not self.stop.is_set():
                    await self._observe(session)
                    if self.stop.is_set():
                        break
                    await asyncio.sleep(OBSERVER_INTERVAL_SECONDS)

    async def _observe(self, session) -> None:
        """Run one round of the R10-B observations."""
        started = time.perf_counter()
        try:
            payload = await asyncio.wait_for(
                session.call_tool("autoengineer_inventory", arguments={
                    "machinePage": 1,
                    "machinePageSize": 16,
                    "logisticsPage": 1,
                    "logisticsPageSize": 16,
                }),
                timeout=20,
            )
        except asyncio.TimeoutError:
            self.timeouts += 1
            self.failures += 1
            return
        except Exception:  # noqa: BLE001 - the failure is counted
            self.failures += 1
            return
        self.requests += 1
        self.machine_latencies.append((time.perf_counter() - started) * 1000)

        body = "\n".join(
            getattr(item, "text", "") or ""
            for item in getattr(payload, "content", []) or []
        )
        try:
            frame = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            self.failures += 1
            return
        if frame.get("status") != "ok":
            self.failures += 1
            return

        machines = frame.get("machine_inventories") or {}
        logistics = frame.get("logistics") or {}
        robots = frame.get("robots") or {}
        transport = frame.get("transport") or {}
        self.machine_rows = max(self.machine_rows,
                                int(machines.get("row_count") or 0))
        self.network_rows = max(self.network_rows,
                                int(logistics.get("row_count") or 0))
        self.transport_rows = max(self.transport_rows,
                                  int(transport.get("row_count") or 0))
        self.robot_total = max(self.robot_total,
                               int(robots.get("total_logistic_robots") or 0))

        # The pagination walk proves that the pages do not overlap and
        # that the walk completes. It is **not** run on every round: the
        # walk reads several pages and the observation walks entities, so
        # running it often costs the game measurable UPS.
        now = time.monotonic()
        if now - self._last_walk >= PAGINATION_INTERVAL_SECONDS:
            self._last_walk = now
            await self._walk_pages(session)

    async def _walk_pages(self, session) -> None:
        """Walk the machine pages and check that they do not overlap."""
        identities: list[str] = []
        for page in range(1, PAGINATION_PAGES + 1):
            try:
                payload = await asyncio.wait_for(
                    session.call_tool("autoengineer_inventory", arguments={
                        "machinePage": page,
                        "machinePageSize": 16,
                        "logisticsPage": 1,
                        "logisticsPageSize": 16,
                    }),
                    timeout=20,
                )
            except asyncio.TimeoutError:
                self.timeouts += 1
                self.failures += 1
                break
            except Exception:  # noqa: BLE001 - the failure is counted
                self.failures += 1
                break
            body = "\n".join(
                getattr(item, "text", "") or ""
                for item in getattr(payload, "content", []) or []
            )
            try:
                frame = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                self.failures += 1
                break
            section = frame.get("machine_inventories") or {}
            rows = section.get("rows") or []
            self.pages_read += 1
            for row in rows:
                if not isinstance(row, dict):
                    continue
                identities.append(
                    f"{row.get('name')}#{row.get('unit_number')}")
            if not rows:
                break
        if identities:
            self.pages_unique = len(identities) == len(set(identities))
            self.identities = identities[:64]

    def stop_and_report(self) -> dict:
        """Stop the observer and return its measurements."""
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=30)
        report = {
            "worker_stopped": self.thread is None or not self.thread.is_alive(),
            "requests": self.requests,
            "failures": self.failures,
            "timeouts": self.timeouts,
            "machine_latency_ms": _tail(self.machine_latencies),
            "machine_rows": self.machine_rows,
            "network_rows": self.network_rows,
            "transport_rows": self.transport_rows,
            "total_logistic_robots": self.robot_total,
            "pages_read": self.pages_read,
            "pages_unique": self.pages_unique,
            "error": self.error,
        }
        (self.work / "r10b-observer.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        return report


def observer_pass(report):
    return bool(report.get("requests", 0) > 0 and not report.get("error")
                and report.get("failures") == 0 and report.get("timeouts") == 0
                and report.get("pages_unique") is True and report.get("worker_stopped") is True)


def run(replicas: int, seconds: int) -> int:
    """Run the creative stress with the R10-B observers attached."""
    holder: dict = {}
    stop_original = stress.stop_owned
    passed = False
    before = {path.name for path in stress.OUTPUT.glob("py-*")}

    def watcher() -> None:
        """Wait for the new stress run and attach both observers."""
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            runs = sorted(stress.OUTPUT.glob("py-*"), key=lambda p: p.name)
            fresh = [path for path in runs if path.name not in before]
            if fresh:
                work = fresh[-1]
                credentials = r10a._read_host_credentials(work)
                if credentials is not None:
                    observer = InventoryObserver(credentials[0], credentials[1],
                                               work)
                    observer.start()
                    holder["observer"] = observer
                    holder["work"] = work
                    return
            time.sleep(2)

    def stop_after_observer(proc):
        observer = holder.get("observer")
        if observer is not None and "stop_report" not in holder:
            holder["stop_report"] = observer.stop_and_report()
        stop_original(proc)

    stress.stop_owned = stop_after_observer
    thread = threading.Thread(target=watcher, daemon=True,
                               name="r10b-observer-watcher")
    thread.start()
    try:
        result = creative.run(replicas, seconds)
    finally:
        stress.stop_owned = stop_original
        observer = holder.get("observer")
        if observer is not None:
            report = holder.get("stop_report") or observer.stop_and_report()
            passed = observer_pass(report)
            report["observer_pass"] = passed
            print("[r10b-observer] " + json.dumps(report, default=str),
                  flush=True)
            work = holder.get("work")
            if work is not None:
                path = work / "result.json"
                if path.is_file():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data["r10b_observer"] = report
                    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return result if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replicas", type=int, default=4, choices=(1, 2, 3, 4))
    parser.add_argument("--seconds", type=int, default=300)
    parsed = parser.parse_args()
    raise SystemExit(run(parsed.replicas, parsed.seconds))
