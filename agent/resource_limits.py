"""What AutoEngineer can and cannot enforce about the resources it uses.

The Settings offer a CPU limit and a memory limit for the model process.
This module is honest about what those two settings actually do.

A Python process **cannot** cap the CPU share or the memory of another
process. Only the operating system can, through the priority and the job
object of the process that is started. AutoEngineer starts the model
itself in the R02 launcher, and it lowers the **priority** of the model it
owns; it does not, and must not, change the priority or the memory of an
unrelated process.

So the two limits are reported as what they are:

* the **CPU** limit is applied as a **priority** on the model AutoEngineer
  owns, and on Windows a below-normal priority is the closest the
  application can get to a share without a job object;
* the **memory** limit is **advisory**. It is the budget the application's
  own caches and histories respect, and it is not a hard cap on the
  model's address space.

A setting that is not enforced is reported as such. The Settings screen
shows the word *advisory* for it, so the user is never told that a limit
is enforced when it is not.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The CPU limit is enforced as a priority on the owned model process.
CPU_ENFORCEMENT = "priority"

#: The memory limit bounds the application's own caches and histories.
MEMORY_ENFORCEMENT = "advisory"

#: The largest CPU share that is accepted.
MAX_CPU_PERCENT = 100

#: The smallest CPU share that is accepted.
MIN_CPU_PERCENT = 1

#: The largest memory budget that is accepted, in megabytes.
MAX_MEMORY_MB = 262144

#: The smallest memory budget that is accepted, in megabytes.
MIN_MEMORY_MB = 128


@dataclass(frozen=True)
class ResourceLimits:
    """The resource limits and how far they are actually enforced."""

    cpu_percent: int
    memory_mb: int
    cpu_enforcement: str = CPU_ENFORCEMENT
    memory_enforcement: str = MEMORY_ENFORCEMENT

    @property
    def cpu_is_advisory(self) -> bool:
        """Whether the CPU limit is only advisory."""
        return self.cpu_enforcement == MEMORY_ENFORCEMENT

    @property
    def memory_is_advisory(self) -> bool:
        """Whether the memory limit is only advisory."""
        return self.memory_enforcement == MEMORY_ENFORCEMENT

    def describe(self) -> dict[str, Any]:
        """Return the limits and their enforcement as a plain dictionary."""
        return {
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "cpu_enforcement": self.cpu_enforcement,
            "memory_enforcement": self.memory_enforcement,
            "cpu_is_advisory": self.cpu_is_advisory,
            "memory_is_advisory": self.memory_is_advisory,
            "note": (
                "The CPU limit is applied as the priority of the model "
                "process AutoEngineer owns. The memory limit is advisory: it "
                "bounds the application's own caches and histories and is "
                "not a hard cap on the model's address space."),
        }

    def summary(self) -> str:
        """Return a one-line summary for the interface."""
        return (f"CPU {self.cpu_percent}% ({self.cpu_enforcement}), "
                f"memory {self.memory_mb} MB ({self.memory_enforcement})")


def _bounded_cpu(value: Any) -> int:
    """Return a CPU share that is safe to use."""
    if type(value) is not int:
        return 50
    return max(MIN_CPU_PERCENT, min(value, MAX_CPU_PERCENT))


def _bounded_memory(value: Any) -> int:
    """Return a memory budget that is safe to use."""
    if type(value) is not int:
        return 4096
    return max(MIN_MEMORY_MB, min(value, MAX_MEMORY_MB))


def resource_limits(settings: Any = None) -> ResourceLimits:
    """Return the resource limits the settings describe.

    A missing or unusable setting falls back to the protective default,
    so the limits are always bounded.
    """
    if settings is None:
        try:
            from importlib import import_module

            effective_settings = getattr(
                import_module("runtime_settings"), "effective_settings")
            settings = effective_settings()
        except Exception:
            settings = None
    cpu = 50
    memory = 4096
    if settings is not None:
        try:
            cpu = _bounded_cpu(settings.get("max_ai_cpu_percent"))
            memory = _bounded_memory(settings.get("max_ai_memory_mb"))
        except Exception:
            pass
    return ResourceLimits(cpu_percent=cpu, memory_mb=memory)


def budget_entries(memory_mb: int, *, entry_bytes: int = 4096) -> int:
    """Return how many cache entries fit in a memory budget.

    The budget is divided by an estimated entry size. The estimate is
    deliberately generous: a budget that is too small would thrash the
    cache, and a cache that is too large would use more memory than the
    user allowed.
    """
    if type(memory_mb) is not int or memory_mb <= 0:
        return 0
    if type(entry_bytes) is not int or entry_bytes <= 0:
        entry_bytes = 4096
    return max(1, (memory_mb * 1024 * 1024) // entry_bytes)
