"""Cancellation and bounded safety cleanup, independent of gameplay planning."""

import asyncio
import json
import threading
import uuid

from agent_events import emit

PROMPT = "Execute this action? [y/N/q]: "
SAFETY_VERSION = 1


async def daemon_call(function, *args):
    """Cancel waiting for blocking model HTTP without delaying interpreter exit."""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def deliver(value, error):
        if not future.done():
            if error is not None:
                future.set_exception(error)
            else:
                future.set_result(value)

    def run():
        try:
            result, error = function(*args), None
        except Exception as exc:
            result, error = None, exc
        try:
            loop.call_soon_threadsafe(deliver, result, error)
        except RuntimeError:
            pass

    threading.Thread(target=run, daemon=True).start()
    return await future


class StopRequested(Exception):
    pass


class ConsoleControl:
    """One daemon reader consumes stop/EOF immediately, even during a tool call."""

    def __init__(self):
        self.stop = asyncio.Event()
        self.answers = asyncio.Queue()
        self.awaiting_answer = False

    def feed(self, line):
        text = line.strip().lower()
        if not line or text in {"q", "stop"}:
            self.stop.set()
            self.awaiting_answer = False
            while not self.answers.empty():
                self.answers.get_nowait()
        elif self.awaiting_answer and not self.stop.is_set():
            self.awaiting_answer = False
            self.answers.put_nowait(text)

    def start_reader(self, stream):
        loop = asyncio.get_running_loop()

        def read():
            try:
                while True:
                    line = stream.readline()
                    loop.call_soon_threadsafe(self.feed, line)
                    if not line:
                        return
            except (OSError, ValueError):
                try:
                    loop.call_soon_threadsafe(self.stop.set)
                except RuntimeError:
                    pass
            except RuntimeError:
                pass  # Event loop already closed; daemon thread never blocks exit.

        threading.Thread(target=read, daemon=True).start()

    async def approve(self):
        if self.stop.is_set():
            raise StopRequested()
        while not self.answers.empty():
            self.answers.get_nowait()
        self.awaiting_answer = True
        print("\n" + PROMPT, end="", flush=True)
        try:
            return await self.answers.get()
        finally:
            self.awaiting_answer = False


def decode_safety(result):
    if result.is_error:
        raise RuntimeError("Safety tool failed")
    for part in result.content:
        if part.type == "text":
            value = json.loads(part.text)
            if isinstance(value, dict):
                return value
    raise RuntimeError("Safety response missing")


class SafetySession:
    def __init__(self, session, control, *, interval=0.3, call_timeout=1.5):
        self.session = session
        self.control = control
        self.owner = uuid.uuid4().hex
        self.interval = interval
        self.call_timeout = call_timeout
        self.attempted_arm = False

    async def call(self, name):
        result = await asyncio.wait_for(
            self.session.call_tool(name, arguments={"owner": self.owner}),
            timeout=self.call_timeout,
        )
        value = decode_safety(result)
        if value.get("version") != SAFETY_VERSION:
            raise RuntimeError("Backend safety version mismatch")
        return value

    async def heartbeat(self):
        while True:
            await asyncio.sleep(self.interval)
            reply = await self.call("autoengineer_renew")
            if reply.get("status") == "human_takeover":
                self.control.stop.set()
                print("HUMAN_TAKEOVER_CONFIRMED", flush=True)
                raise StopRequested()
            if reply.get("status") != "active":
                raise RuntimeError("Game-side lease no longer active")

    async def confirm_stop(self):
        # The game can still report the prior walking state in the stop tick.
        # Recheck later, within the overall cleanup timeout below.
        while True:
            reply = await self.call("autoengineer_stop")
            if reply.get("status") != "unconfirmed":
                return reply
            await asyncio.sleep(0.05)

    async def run(self, work):
        """Work is a callable so no gameplay starts before capability/lease checks."""
        tasks = []
        try:
            available = await asyncio.wait_for(self.session.list_tools(), self.call_timeout)
            required = {"autoengineer_arm", "autoengineer_renew", "autoengineer_stop"}
            if not required <= {tool.name for tool in available.tools}:
                raise RuntimeError("Patched backend safety tools required; movement disabled")
            if self.control.stop.is_set():
                raise StopRequested()
            self.attempted_arm = True  # Even a timed-out arm may have reached the game.
            reply = await self.call("autoengineer_arm")
            if reply.get("status") != "active":
                raise RuntimeError("Game-side safety lease was not armed")
            if self.control.stop.is_set():
                raise StopRequested()
            worker = asyncio.create_task(work())
            pulse = asyncio.create_task(self.heartbeat())
            stop = asyncio.create_task(self.control.stop.wait())
            tasks = [worker, pulse, stop]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if stop.done() or self.control.stop.is_set():
                raise StopRequested()
            if pulse.done():
                await pulse
                raise RuntimeError("Safety heartbeat ended unexpectedly")
            return await worker
        finally:
            emit("stop_requested")
            self.control.stop.set()  # Latch before cancelling: no later approval/dispatch.
            for task in tasks:
                task.cancel()
            # Stop is deliberately outside the normal gameplay command queue.
            # Start it before waiting for cancellation acknowledgements.
            if self.attempted_arm:
                try:
                    reply = await asyncio.shield(
                        asyncio.wait_for(self.confirm_stop(), timeout=self.call_timeout)
                    )
                    if reply.get("status") == "stopped" and reply.get("walking") is False:
                        emit("stop_confirmed")
                        print("SAFETY_STOP_CONFIRMED", flush=True)
                    else:
                        emit("stop_unconfirmed")
                        print(
                            "SAFETY_STOP_UNCONFIRMED: game-side stop was not acknowledged",
                            flush=True,
                        )
                except (Exception, asyncio.CancelledError):
                    emit("stop_unconfirmed")
                    print("SAFETY_STOP_UNCONFIRMED: relying on game-side lease expiry", flush=True)
            if tasks:
                done, pending = await asyncio.wait(tasks, timeout=self.call_timeout)
                for task in done:
                    if not task.cancelled():
                        task.exception()  # Consume exceptions without masking cleanup outcome.
                for task in pending:
                    task.add_done_callback(
                        lambda item: None if item.cancelled() else item.exception()
                    )
