"""Pure-task asyncio loop for offline tests, requiring no OS socket pair.

The sandbox's Windows socket-pair initialization can block. This loop supports
timers/tasks/thread callbacks only: it deliberately cannot perform network I/O.
Production continues to use Python's normal asyncio loop.
"""
import asyncio
import selectors
import time


class TimerSelector(selectors.BaseSelector):
    def register(self, *args, **kwargs):
        raise RuntimeError("Network I/O is forbidden in offline tests")

    def unregister(self, *args, **kwargs):
        raise RuntimeError("Network I/O is forbidden in offline tests")

    def get_map(self):
        return {}

    def select(self, timeout=None):
        time.sleep(min(0.005, max(0, timeout if timeout is not None else 0.005)))
        return []


class OfflineLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        super().__init__(selector=TimerSelector())

    def _make_self_pipe(self):
        self._ssock = self._csock = None

    def _close_self_pipe(self):
        pass

    def _write_to_self(self):
        pass  # TimerSelector polls thread-safe callbacks every five milliseconds.
