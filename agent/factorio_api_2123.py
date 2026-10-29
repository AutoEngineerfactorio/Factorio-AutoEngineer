"""Exact Factorio 2.1.23 API signature lookup for offline verification.

This module is the machine-readable half of the project's exact-signature rule.
Before modifying any Lua source, look the API up here instead of guessing.

The single source of truth is the offline archive
``.local/factorio-api-offline/2.1.23/files/``, which is a verbatim copy of the
verified Factorio 2.1.23 installation's ``doc-html``. Its ``runtime-api.json``
and ``prototype-api.json`` both declare ``application_version`` ``2.1.23``.

Every lookup fails closed: an API name that is absent from the 2.1.23 archive
raises :class:`UnknownApiError` rather than returning a guess. Archived 2.1.22
and 2.0.77 copies are deliberately **not** consulted, so a name that only
exists in an older version is reported as unknown instead of silently
succeeding.

This module performs no network access, starts no Factorio process and reads no
save. It only reads local JSON files.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SUPPORTED_VERSION = "2.1.23"

ARCHIVE_ROOT = Path(__file__).resolve().parents[1] / ".local" / "factorio-api-offline"
SUPPORTED_ARCHIVE = ARCHIVE_ROOT / SUPPORTED_VERSION / "files"
RUNTIME_API = SUPPORTED_ARCHIVE / "runtime-api.json"
PROTOTYPE_API = SUPPORTED_ARCHIVE / "prototype-api.json"


class UnknownApiError(KeyError):
    """Raised when an API name is not present in the 2.1.23 archive."""

    def __init__(self, kind: str, name: str) -> None:
        self.kind = kind
        self.name = name
        super().__init__(
            f"{kind} {name!r} is not present in the Factorio "
            f"{SUPPORTED_VERSION} offline API archive. Treat it as UNVERIFIED "
            f"and report the missing documentation; do not guess a signature "
            f"and do not substitute an archived 2.1.22 or 2.0.77 signature."
        )


def _load(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(
            f"Factorio {SUPPORTED_VERSION} offline API archive missing: {path}. "
            f"Populate .local/factorio-api-offline/{SUPPORTED_VERSION}/files/ "
            f"before relying on API lookups."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("application_version")
    if version != SUPPORTED_VERSION:
        raise ValueError(
            f"{path} declares application_version {version!r}, expected "
            f"{SUPPORTED_VERSION!r}. The offline archive is not the supported API."
        )
    return data


@lru_cache(maxsize=None)
def runtime_api() -> dict:
    """The 2.1.23 runtime (control stage) API document."""
    return _load(RUNTIME_API)


@lru_cache(maxsize=None)
def prototype_api() -> dict:
    """The 2.1.23 prototype (data stage) API document."""
    return _load(PROTOTYPE_API)


def _classes(stage: str) -> list:
    """Return the class list of the requested stage.

    The 2.1.23 archive stores the two stages under different keys: the
    runtime (control stage) document keeps its classes under ``classes`` and
    the prototype (data stage) document keeps them under ``prototypes``.
    """
    if stage == "runtime":
        return runtime_api()["classes"]
    return prototype_api()["prototypes"]


def find_class(name: str, stage: str = "runtime") -> dict:
    """Return the 2.1.23 class definition, or raise :class:`UnknownApiError`."""
    for entry in _classes(stage):
        if entry.get("name") == name:
            return entry
    raise UnknownApiError("class", name)


def find_method(class_name: str, method_name: str, stage: str = "runtime") -> dict:
    """Return the exact 2.1.23 method signature, or raise :class:`UnknownApiError`.

    The returned mapping contains ``name``, ``parameters``, ``return_type`` and
    ``description`` exactly as the official archive records them.
    """
    entry = find_class(class_name, stage)
    for method in entry.get("methods", []):
        if method.get("name") == method_name:
            return method
    raise UnknownApiError("method", f"{class_name}.{method_name}")


def find_property(class_name: str, property_name: str, stage: str = "runtime") -> dict:
    """Return the exact 2.1.23 property definition, or raise.

    The 2.1.23 archive stores a class's readable members under two different
    keys depending on the stage. A **runtime** class (control stage) keeps
    them in ``attributes``; a **prototype** class (data stage) keeps them in
    ``properties``. Both are searched, so a runtime attribute such as
    ``LuaEntityPrototype.module_inventory_size`` resolves instead of being
    reported as missing.
    """
    entry = find_class(class_name, stage)
    for group in ("attributes", "properties"):
        for prop in entry.get(group, []):
            if prop.get("name") == property_name:
                return prop
    raise UnknownApiError("property", f"{class_name}.{property_name}")


def find_event(name: str) -> dict:
    """Return the exact 2.1.23 event definition and its payload fields."""
    for event in runtime_api()["events"]:
        if event.get("name") == name:
            return event
    raise UnknownApiError("event", name)


def event_fields(name: str) -> set:
    """The documented payload field names of a 2.1.23 event."""
    return {field["name"] for field in find_event(name).get("data", [])}


def method_signature(class_name: str, method_name: str, stage: str = "runtime") -> str:
    """A compact human-readable signature for reporting.

    Parameters are listed in the archive's documented ``order``, and an
    optional parameter is marked with a trailing ``?``.

    Example: ``LuaGameScript.take_screenshot(player?, path?)``.
    """
    method = find_method(class_name, method_name, stage)
    parameters = sorted(
        method.get("parameters", []), key=lambda p: p.get("order", 0)
    )
    rendered = ", ".join(
        f"{p['name']}{'?' if p.get('optional', False) else ''}"
        for p in parameters
    )
    return f"{class_name}.{method_name}({rendered})"


def has_api(name: str, stage: str = "runtime") -> bool:
    """Whether ``name`` exists in the 2.1.23 archive at all.

    Useful as a fail-closed guard before editing Lua: if this returns False the
    API is unverified and must be reported rather than assumed.
    """
    try:
        find_class(name, stage)
    except UnknownApiError:
        return False
    return True
