import asyncio
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
import supervised_agent as agent
from exploration_memory import ExplorationMemory
from mode_policy import SEMI, ModePolicy
from movement_proposals import movement_choices
from offline_loop import OfflineLoop
from session_safety import ConsoleControl, StopRequested


class ExplorationTests(unittest.TestCase):
    def test_restart_retains_visits_and_failures_and_filters_proposals(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ExplorationMemory("disposable-world", directory)
            memory.remember({"x": 0, "y": -4}, failed=True)
            memory.remember({"x": 4, "y": 0})
            memory = ExplorationMemory("disposable-world", directory)
            choices = movement_choices({"position": {"x": 0, "y": 0}, "exploration": memory})
            self.assertFalse(any(c["y"] == -4 for c in choices))
            self.assertFalse(choices[0]["visited"])
            self.assertTrue(choices[-1]["visited"])
            for candidate in choices:
                self.assertIsNotNone(
                    agent.validate(dict(candidate, action="walk"), {"x": 0, "y": 0})
                )
            self.assertFalse(
                ExplorationMemory("another-world", directory).blocked({"x": 0, "y": -4})
            )

    def test_negative_cells_and_failure_radius(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ExplorationMemory("world", directory)
            memory.remember({"x": -0.1, "y": -0.1})
            self.assertTrue(memory.visited({"x": -1.9, "y": -1.9}))
            self.assertFalse(memory.visited({"x": 0, "y": 0}))
            memory.remember({"x": 4, "y": 0}, failed=True)
            self.assertTrue(memory.blocked({"x": 4.5, "y": 0}))
            self.assertFalse(memory.blocked({"x": 5.1, "y": 0}))

    def test_corrupt_map_stops_instead_of_forgetting_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ExplorationMemory("world", directory)
            memory.remember({"x": 0, "y": 0})
            memory.path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                ExplorationMemory("world", directory)

    def test_interrupted_replace_preserves_previous_map(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ExplorationMemory("world", directory)
            memory.remember({"x": 0, "y": 0})
            original = memory.path.read_bytes()
            with patch("exploration_memory.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    memory.remember({"x": 4, "y": 0}, failed=True)
            self.assertEqual(memory.path.read_bytes(), original)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_invalid_values_and_world_names(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                ExplorationMemory("", directory)
            memory = ExplorationMemory("../../world", directory)
            self.assertEqual(memory.path.parent, Path(directory))
            for value in [float("nan"), float("inf"), True, "4", 1e20]:
                with self.assertRaises(ValueError):
                    memory.remember({"x": value, "y": 0})


class MemoryDispatchTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=OfflineLoop)

    async def scenario(self, memory, approval="y", stop=False):
        control = ConsoleControl()

        async def approve():
            if stop:
                control.stop.set()
            return approval

        control.approve = approve
        response = SimpleNamespace(
            is_error=False, content=[SimpleNamespace(type="text", text='{"status":"no_path"}')]
        )
        session = SimpleNamespace(call_tool=AsyncMock(return_value=response))
        with (
            patch.object(agent, "load_memory", return_value=memory),
            patch.object(agent, "MAX_ACTIONS", 1),
            patch.object(agent, "read_tool", AsyncMock(return_value={"x": 0, "y": 0})),
            patch.object(
                agent, "daemon_call", AsyncMock(return_value={"action": "walk", "x": 4, "y": 0})
            ),
            redirect_stdout(io.StringIO()),
        ):
            await agent.run_cycles(session, control, "a" * 32, policy=ModePolicy(SEMI))
        return session

    async def test_failed_dispatch_survives_restart_and_blocks_even_injected_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            first = await self.scenario(ExplorationMemory("world", directory))
            self.assertEqual(first.call_tool.await_count, 1)
            second = await self.scenario(ExplorationMemory("world", directory))
            second.call_tool.assert_not_called()

    async def test_rejection_does_not_persist_failure_or_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            session = await self.scenario(ExplorationMemory("world", directory), approval="n")
            session.call_tool.assert_not_called()
            self.assertFalse(ExplorationMemory("world", directory).blocked({"x": 4, "y": 0}))

    async def test_stop_after_approval_still_prevents_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(StopRequested):
                await self.scenario(ExplorationMemory("world", directory), stop=True)
            self.assertFalse(ExplorationMemory("world", directory).blocked({"x": 4, "y": 0}))
