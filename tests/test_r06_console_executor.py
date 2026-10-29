"""Regression tests for the Factorio console first-use gate executor.

The defect these tests pin is the one observed live on Factorio 2.1.23: the
server holds the **first** Lua console command pending, logs

    [WARNING] Using Lua console commands will disable achievements.
    Please repeat the command to proceed.

and returns an **empty** response body. The previous harness sent its probe
twice without checking the response, so it could neither prove that the
command had run nor stop itself from repeating a command that had already
run.

These tests are offline. They drive the executor with a fake sender and
never touch Factorio.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import r06_console_executor as executor  # noqa: E402


class RecordingSender:
    """A fake console sender that records every command it was given."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.commands: list[str] = []

    def __call__(self, command: str) -> str:
        self.commands.append(command)
        if not self.responses:
            return ""
        return self.responses.pop(0)


class MarkerTests(unittest.TestCase):
    """The verification marker must be unique and safe to print."""

    def test_two_markers_are_different(self):
        self.assertNotEqual(executor.new_marker(), executor.new_marker())

    def test_the_marker_has_the_expected_prefix(self):
        self.assertTrue(executor.new_marker().startswith(
            executor.MARKER_PREFIX))

    def test_the_marker_survives_the_probe_command(self):
        marker = executor.new_marker()
        command = executor.build_probe(marker)
        self.assertTrue(command.startswith("rcon.print('"))
        self.assertTrue(command.endswith("')"))
        # The printed token must equal the filtered marker.
        printed = command[len("rcon.print('"):-len("')")]
        self.assertEqual(printed, marker)

    def test_unsafe_characters_are_removed_from_the_marker(self):
        marker = "MARKER-with spaces'and\"quotes"
        printed = executor.build_probe(marker)[len("rcon.print('"):-len("')")]
        self.assertNotIn(" ", printed)
        self.assertNotIn("'", printed)


class ResponseClassificationTests(unittest.TestCase):
    """The response classification must be explicit."""

    def test_a_marker_response_is_recognised(self):
        marker = executor.new_marker()
        self.assertTrue(executor.response_contains_marker(marker, marker))

    def test_an_empty_response_is_the_gated_signature(self):
        self.assertTrue(executor.is_empty_response(""))
        self.assertTrue(executor.is_empty_response("   "))
        self.assertTrue(executor.is_empty_response(None))
        self.assertFalse(executor.is_empty_response("x"))

    def test_the_nothing_response_is_recognised(self):
        self.assertTrue(executor.is_nothing_response("nothing"))
        self.assertTrue(executor.is_nothing_response("Nothing"))
        self.assertFalse(executor.is_nothing_response(""))

    def test_the_classification_names_the_gated_case(self):
        marker = executor.new_marker()
        text = executor.classify_response("", marker)
        self.assertIn("console gate", text)

    def test_the_classification_names_the_missing_marker(self):
        marker = executor.new_marker()
        text = executor.classify_response("something else", marker)
        self.assertIn("without the marker", text)


class FirstUseConfirmationTests(unittest.TestCase):
    """The first-use gate is cleared by exactly one verified repeat."""

    def test_the_gate_is_cleared_when_the_first_attempt_is_held(self):
        marker = executor.new_marker()
        sender = RecordingSender(["", marker])
        outcome = executor.ConsoleExecutor(sender).execute(marker=marker)
        self.assertTrue(outcome.executed)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(len(sender.commands), 2)
        # The repeat must be the identical command.
        self.assertEqual(sender.commands[0], sender.commands[1])

    def test_a_command_that_already_executed_is_never_resent(self):
        """The marker is present, so the command ran and must not repeat."""
        marker = executor.new_marker()
        sender = RecordingSender([marker])
        outcome = executor.ConsoleExecutor(sender).execute(marker=marker)
        self.assertTrue(outcome.executed)
        self.assertEqual(outcome.attempts, 1)
        self.assertEqual(len(sender.commands), 1)

    def test_the_gate_probe_is_a_read_only_print(self):
        sender = RecordingSender([""])
        executor.ConsoleExecutor(sender).clear_gate()
        for command in sender.commands:
            self.assertIn("rcon.print(", command)
            self.assertNotIn("game.", command)
            self.assertNotIn("player", command)

    def test_the_probe_is_never_sent_more_than_twice(self):
        sender = RecordingSender(["", ""])
        outcome = executor.ConsoleExecutor(sender).clear_gate()
        self.assertFalse(outcome.executed)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(len(sender.commands), 2)


class UncertainOutcomeTests(unittest.TestCase):
    """An outcome that cannot be established must be reported, not guessed."""

    def test_an_unconfirmed_probe_is_reported_as_uncertain(self):
        sender = RecordingSender(["", ""])
        outcome = executor.ConsoleExecutor(sender).clear_gate()
        self.assertFalse(outcome.executed)
        self.assertTrue(outcome.uncertain)
        self.assertIn("could not be confirmed", outcome.reason)

    def test_a_command_without_a_marker_is_never_resent(self):
        """An empty response cannot be distinguished from no output."""
        sender = RecordingSender(["", "should never be sent"])
        outcome = executor.ConsoleExecutor(sender).execute("some command")
        self.assertEqual(len(sender.commands), 1)
        self.assertFalse(outcome.executed)
        self.assertTrue(outcome.uncertain)

    def test_a_non_empty_response_without_the_marker_counts_as_executed(self):
        """The command produced output, so it ran and must not repeat."""
        sender = RecordingSender(["some real output"])
        outcome = executor.ConsoleExecutor(sender).execute(
            "some command", marker=executor.new_marker())
        self.assertTrue(outcome.executed)
        self.assertEqual(len(sender.commands), 1)
        self.assertIn("not empty", outcome.reason)

    def test_the_nothing_response_is_not_treated_as_empty(self):
        """Factorio's explicit "nothing" is a real response."""
        sender = RecordingSender(["nothing"])
        outcome = executor.ConsoleExecutor(sender).execute(
            "some command", marker=executor.new_marker())
        self.assertTrue(outcome.executed)
        self.assertEqual(len(sender.commands), 1)


class DuplicateProtectionTests(unittest.TestCase):
    """A gameplay command must never be applied twice."""

    def test_a_successful_gameplay_command_is_sent_once(self):
        sender = RecordingSender(['{"status":"ok"}'])
        outcome = executor.ConsoleExecutor(sender).execute(
            "gameplay command", marker=executor.new_marker())
        self.assertTrue(outcome.executed)
        self.assertEqual(len(sender.commands), 1)

    def test_the_executor_never_sends_more_than_two_copies(self):
        sender = RecordingSender(["", "", "", ""])
        outcome = executor.ConsoleExecutor(sender).execute(
            "gameplay command", marker=executor.new_marker())
        self.assertEqual(len(sender.commands), 2)
        self.assertFalse(outcome.executed)

    def test_the_attempt_cap_is_configurable_but_bounded(self):
        sender = RecordingSender(["", "", ""])
        outcome = executor.ConsoleExecutor(sender, max_attempts=1).execute(
            "gameplay command", marker=executor.new_marker())
        self.assertEqual(len(sender.commands), 1)
        self.assertFalse(outcome.executed)

    def test_a_zero_attempt_cap_still_sends_once(self):
        """A cap of zero is clamped to one attempt, never to zero."""
        sender = RecordingSender([""])
        outcome = executor.ConsoleExecutor(sender, max_attempts=0).execute(
            "gameplay command", marker=executor.new_marker())
        self.assertEqual(len(sender.commands), 1)
        self.assertFalse(outcome.executed)
        self.assertTrue(outcome.uncertain)


class TimeoutBehaviourTests(unittest.TestCase):
    """A sender that never answers must not spin."""

    def test_a_sender_that_raises_is_reported_as_a_failure(self):
        def sender(command: str) -> str:
            raise TimeoutError("no answer")

        outcome = executor.ConsoleExecutor(sender).clear_gate()
        self.assertFalse(outcome.executed)
        self.assertTrue(outcome.uncertain)


if __name__ == "__main__":
    unittest.main()
