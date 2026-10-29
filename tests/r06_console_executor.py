"""A reliable console-command executor for the Factorio R06 live tests.

Factorio 2.1.23 gates the **first** Lua console command of a fresh server.
The gate is visible in the server log:

```
[WARNING] Player <server> tried using the command "rcon.print('...')".
[WARNING] Using Lua console commands will disable achievements. Please repeat the command to proceed.
```

The held command does not run: its response body is **empty**. Repeating the
**identical** command executes it.

The safe way through that gate is therefore:

1. send the command once;
2. decide from the **response** whether it actually executed;
3. resend the **identical** command **once** only when the response proves it
   did not execute;
4. **never** resend a command that already executed, and **never** send a
   third copy.

To decide from the response, the command must carry a **verification marker**:
a unique token that appears in the response body only when the command really
ran. A command without a marker is *not* safe to retry, because an empty
response cannot be distinguished from a command whose output was legitimately
empty. Such a command is reported as **uncertain** and is never resent.

This module is the harness-side executor. It is read-only: it never issues a
gameplay command, it only ever repeats a command it has itself classified as
*not executed*, and it never repeats a command that produced its marker.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

#: The marker prefix. It is unique per executor instance so a response can
#: never be confused with an earlier command's output.
MARKER_PREFIX = "AUTOENGINEER-CONSOLE-MARKER"

#: A response body that Factorio returns for a command that produced no
#: output at all. It is distinct from an empty body, which is what a gated
#: command returns.
NOTHING_RESPONSE = "nothing"

#: The characters Factorio's console accepts in a printed string.
_SAFE_MARKER = re.compile(r"[^A-Za-z0-9-]")


def new_marker() -> str:
    """Return a unique verification marker for one command execution."""
    token = uuid.uuid4().hex[:16]
    return f"{MARKER_PREFIX}-{token}"


def build_probe(marker: str) -> str:
    """Return the read-only probe command that prints the marker.

    The probe is a ``rcon.print`` of the marker. It observes nothing and
    changes nothing, so repeating it can never apply a gameplay action twice.
    """
    safe = _SAFE_MARKER.sub("", marker)
    return f"rcon.print('{safe}')"


@dataclass
class CommandOutcome:
    """The result of one command execution attempt sequence."""

    executed: bool
    attempts: int
    marker: str
    response: str = ""
    reason: str = ""

    @property
    def uncertain(self) -> bool:
        """True when it cannot be established whether the command ran."""
        return not self.executed and self.reason.startswith("uncertain")


def response_contains_marker(response: str, marker: str) -> bool:
    """Return True when the response body carries the verification marker.

    The marker is compared in a case-insensitive way and with the same
    character filtering the probe applies, so a response that echoes the
    marker is always recognised. An **empty** marker never matches: without
    a marker there is nothing to look for.
    """
    if not response or not marker:
        return False
    safe = _SAFE_MARKER.sub("", marker)
    if not safe:
        return False
    return safe.lower() in response.lower()


def is_empty_response(response: str | None) -> bool:
    """Return True when the response body is empty.

    An empty body is what a **gated** command returns. It is also what a
    command that legitimately produced no output returns, which is exactly
    why a marker is required before any resend is allowed.
    """
    return response is None or response.strip() == ""


def is_nothing_response(response: str | None) -> bool:
    """Return True when Factorio answered with its explicit "nothing"."""
    if response is None:
        return False
    return response.strip().lower() == NOTHING_RESPONSE


class ConsoleExecutor:
    """Executes read-only console commands through the Factorio console gate.

    The executor is given a callable that sends one command and returns the
    response body. It never sends a command that has already produced its
    marker, and it never sends more than two copies of a command.
    """

    def __init__(self, send, max_attempts: int = 2):
        self._send = send
        self.max_attempts = max(1, int(max_attempts))

    def _send_once(self, command: str) -> tuple[str, str | None]:
        """Send one command and return its response and any transport error.

        A transport failure is reported rather than raised, so the executor
        can stop cleanly instead of crashing the harness.
        """
        try:
            return self._send(command) or "", None
        except Exception as exc:  # noqa: BLE001 - the report must survive
            return "", f"{type(exc).__name__}: {exc}"

    def execute(self, command: str | None = None,
                marker: str | None = None) -> CommandOutcome:
        """Execute one command, handling the first-use console gate.

        ``command`` is the command to run. When it is omitted the executor
        sends its own read-only marker probe, which is what clears the gate
        without touching the game. ``marker`` is the verification marker the
        response must carry.
        """
        if command is None:
            marker = marker or new_marker()
            command = build_probe(marker)
        if marker is None:
            # Without a marker the outcome of an empty response cannot be
            # established, so the command is sent exactly once and reported
            # as uncertain when it produced no output.
            response, error = self._send_once(command)
            if error is not None:
                return CommandOutcome(False, 1, "", response,
                                      f"uncertain: the command failed: {error}")
            if is_nothing_response(response) or is_empty_response(response):
                return CommandOutcome(
                    False, 1, "", response,
                    "uncertain: the command produced no output and carries no "
                    "verification marker, so it was not repeated")
            return CommandOutcome(True, 1, "", response, "executed")

        attempts = 0
        response = ""
        while attempts < self.max_attempts:
            attempts += 1
            response, error = self._send_once(command)
            if error is not None:
                return CommandOutcome(
                    False, attempts, marker, response,
                    f"uncertain: the command failed: {error}")
            if response_contains_marker(response, marker):
                return CommandOutcome(True, attempts, marker, response,
                                      "executed")
            if not is_empty_response(response):
                # The command produced a real response that simply does not
                # carry the marker. It was executed; repeating it could
                # duplicate a gameplay action, so it is not repeated.
                return CommandOutcome(
                    True, attempts, marker, response,
                    "executed: the response did not carry the marker but it "
                    "was not empty")
        return CommandOutcome(
            False, attempts, marker, response,
            "uncertain: the command produced no output after "
            f"{attempts} attempt(s) and its execution could not be confirmed")

    def clear_gate(self) -> CommandOutcome:
        """Clear the console gate with a verified read-only probe.

        The probe prints a unique marker. It is repeated **once** and only
        when the first attempt produced no output, so it can never be
        executed twice as a side effect.
        """
        return self.execute()


def classify_response(response: str | None, marker: str) -> str:
    """Classify one raw response for logging and reporting.

    The classification is deliberately explicit so a failure report says
    what was observed instead of guessing.
    """
    if response is None:
        return "no response"
    if response_contains_marker(response, marker):
        return "marker present"
    if is_nothing_response(response):
        return "factorio reported nothing"
    if is_empty_response(response):
        return "empty response (the command was held by the console gate)"
    return "response without the marker"
