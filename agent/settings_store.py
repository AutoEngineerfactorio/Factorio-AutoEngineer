"""Persistent, validated and non-secret AutoEngineer settings.

This module is the single place where the application's preferences live.
It is used by the Qt Settings workspace and by the services that read the
same values, so a change in the interface reaches the service and not
only the form.

Three rules shape the design.

**Nothing secret is stored here.** No API key, no RCON password, no model
credential. The store refuses any key that looks like a secret and it
never writes one. Credentials stay in the environment or in the separate
secret files, exactly as ``autoengineer_config`` already requires.

**Every value is validated on the way in and on the way out.** A value
that is out of range is refused with a sentence the interface can show.
A settings file that was edited by hand and now carries an invalid value
does not crash the application: the invalid value is reported and the
default is used.

**Every write is atomic.** The file is written to a temporary file in the
same directory and renamed over the target, so an interrupted write can
never leave a half-written configuration behind.

The file lives in ``.local/settings.json`` inside the project. It is
plain JSON on purpose: the user can read it, back it up and move it to
another machine.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

#: The schema version of the settings file.
SCHEMA = 1

#: The relative location of the settings file inside the project.
DEFAULT_RELATIVE_PATH = Path(".local") / "settings.json"

#: A key that looks like a credential is refused. The check is on the
#: name, because a secret is identified by what it is called.
#:
#: The markers are matched as **whole words**. A substring match would
#: refuse legitimate settings such as ``llm_context_tokens``, which is a
#: limit and not a credential.
SECRET_NAME_MARKERS = (
    "password", "passwd", "secret", "api_key", "apikey", "token",
    "credential", "private_key", "access_key", "auth",
)

#: The names that contain a marker as a substring but are not credentials.
#: They are listed explicitly so the rule stays readable and so a new
#: setting cannot silently slip past it.
SECRET_NAME_ALLOWANCES = frozenset({
    "llm_context_tokens",
    "llm_max_output_tokens",
})

#: The name of the environment variable that holds the RCON password.
RCON_PASSWORD_VARIABLE = "FACTORIO_RCON_PASSWORD"


class SettingsError(ValueError):
    """A setting was invalid, or the settings file could not be used."""


@dataclass(frozen=True)
class Field:
    """One setting: its type, its bounds and its default."""

    name: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    description: str = ""

    def validate(self, value: Any) -> Any:
        """Return the validated value or refuse it."""
        if self.kind == "bool":
            if type(value) is not bool:
                raise SettingsError(f"{self.name} must be true or false")
            return value
        if self.kind == "int":
            if type(value) is not int:
                raise SettingsError(f"{self.name} must be a whole number")
            self._check_bounds(value)
            return value
        if self.kind == "float":
            if type(value) not in (int, float) or isinstance(value, bool):
                raise SettingsError(f"{self.name} must be a number")
            number = float(value)
            self._check_bounds(number)
            return number
        if self.kind == "text":
            if not isinstance(value, str):
                raise SettingsError(f"{self.name} must be text")
            if len(value) > 4096:
                raise SettingsError(f"{self.name} is too long")
            return value
        if self.kind == "choice":
            if not isinstance(value, str):
                raise SettingsError(f"{self.name} must be text")
            if value not in self.choices:
                raise SettingsError(
                    f"{self.name} must be one of: {', '.join(self.choices)}")
            return value
        if self.kind == "url":
            return self._validate_url(value)
        raise SettingsError(f"{self.name} has an unsupported type")

    def _validate_url(self, value: Any) -> str:
        """Return a usable loopback base URL, or refuse it.

        Only a loopback address is accepted, exactly as the backend
        configuration already requires. A remote address would send the
        user's observations and prompts to another machine, so it is
        refused here rather than at the point of use.
        """
        if not isinstance(value, str):
            raise SettingsError(f"{self.name} must be text")
        candidate = value.strip().rstrip("/")
        if not candidate:
            raise SettingsError(f"{self.name} must not be empty")
        import ipaddress
        from urllib.parse import urlsplit

        url = urlsplit(candidate)
        if url.scheme not in {"http", "https"} or not url.hostname:
            raise SettingsError(
                f"{self.name} must be an HTTP(S) base URL")
        if url.username or url.password or url.query or url.fragment:
            raise SettingsError(
                f"{self.name} must not carry credentials, a query or a "
                "fragment")
        host = url.hostname
        if host != "localhost":
            try:
                if not ipaddress.ip_address(host).is_loopback:
                    raise ValueError()
            except ValueError:
                raise SettingsError(
                    f"{self.name} must be a loopback address") from None
        return candidate

    def _check_bounds(self, value: float) -> None:
        if self.minimum is not None and value < self.minimum:
            raise SettingsError(f"{self.name} must be at least {self.minimum:g}")
        if self.maximum is not None and value > self.maximum:
            raise SettingsError(f"{self.name} must be at most {self.maximum:g}")


#: The settings of the application, grouped by the Settings section that
#: shows them. The order is the order the interface shows them in.
FIELDS: tuple[Field, ...] = (
    # -- General --------------------------------------------------------
    Field("start_maximized", "bool", False,
          description="Open the dashboard maximized."),
    Field("default_workspace", "choice", "Dashboard",
          choices=("Dashboard", "AI Helper", "Blueprint Planner", "Telemetry",
                   "Research", "Inventory", "Power", "Map", "Logistics",
                   "Logs & Diagnostics", "Saves", "Settings"),
          description="The workspace the dashboard opens on."),
    Field("window_width", "int", 1600, minimum=1024, maximum=7680,
          description="The width of the dashboard window in pixels."),
    Field("window_height", "int", 940, minimum=640, maximum=4320,
          description="The height of the dashboard window in pixels."),
    Field("theme", "choice", "Graphite",
          choices=("Graphite", "System"),
          description="The colour scheme of the interface."),
    Field("scale_percent", "int", 100, minimum=75, maximum=200,
          description="The text and icon scale of the interface."),

    # -- Factorio and profiles ------------------------------------------
    Field("default_profile", "text", "",
          description="The profile the dashboard opens with."),
    Field("factorio_install_root", "text", "",
          description="An additional Factorio installation directory."),
    Field("confirm_before_launch", "bool", True,
          description="Ask for confirmation before the game is started."),
    Field("confirm_before_stop", "bool", True,
          description="Ask for confirmation before the game is stopped."),

    # -- AI models ------------------------------------------------------
    Field("llm_provider", "choice", "Local",
          choices=("Local", "OpenAI-compatible", "Ollama", "LM Studio",
                   "llama.cpp"),
          description="Where the model runs."),
    Field("llm_endpoint", "url", "http://127.0.0.1:8080/v1",
          description="The base URL of the model endpoint. Only a "
                      "loopback address is accepted."),
    Field("llm_model", "text", "",
          description="The model name. An empty value means the endpoint "
                      "decides."),
    Field("llm_context_tokens", "int", 8192, minimum=512, maximum=1048576,
          description="The context window the model is asked to use."),
    Field("llm_max_output_tokens", "int", 2048, minimum=64, maximum=131072,
          description="The largest answer the model may produce."),
    Field("llm_timeout_seconds", "int", 120, minimum=5, maximum=3600,
          description="How long one model request may take."),
    Field("llm_max_parallel_requests", "int", 1, minimum=1, maximum=8,
          description="How many model requests may run at the same time."),

    # -- AI Helper and blueprints ---------------------------------------
    Field("helper_production_units", "choice", "per-minute",
          choices=("per-second", "per-minute", "per-hour"),
          description="The unit the production planner uses."),
    Field("blueprint_spacing_tiles", "int", 8, minimum=4, maximum=32,
          description="The gap between two drafted machines, in tiles."),
    Field("blueprint_columns", "int", 12, minimum=1, maximum=32,
          description="How many machines one row of a draft holds."),
    Field("blueprint_max_machines", "int", 256, minimum=1, maximum=500,
          description="The largest machine array a draft may contain."),
    Field("blueprint_library_root", "text", "",
          description="Where the local blueprint library is kept."),
    Field("require_observed_catalog", "bool", True,
          description="Refuse to plan without a complete observed catalog."),
    Field("research_restriction", "choice", "observed-only",
          choices=("observed-only", "all-observed", "unlocked"),
          description="Which recipes the planner may use."),

    # -- Performance and telemetry --------------------------------------
    Field("ups_target", "int", 60, minimum=30, maximum=240,
          description="The update rate the game runs at."),
    # The three thresholds are floats because the guard's defaults are
    # 58.0 / 59.5 / 52.0. Keeping the exact values means a default
    # installation behaves exactly as it did before the thresholds became
    # configurable.
    Field("ups_degrade_threshold", "float", 58.0, minimum=20.0, maximum=240.0,
          description="Below this update rate the background work is reduced."),
    Field("ups_recover_threshold", "float", 59.5, minimum=20.0, maximum=240.0,
          description="At this update rate the background work resumes."),
    Field("ups_critical_threshold", "float", 52.0, minimum=10.0, maximum=240.0,
          description="Below this update rate the heavy work stops."),
    Field("observation_interval_seconds", "int", 20, minimum=1, maximum=600,
          description="How often the observer reads the game."),
    Field("observation_page_interval_seconds", "int", 120, minimum=5,
          maximum=3600,
          description="How often the observer walks the pages of a catalog."),
    Field("observation_max_requests", "int", 4, minimum=1, maximum=64,
          description="How many observation requests one round may make."),
    Field("cache_max_entries", "int", 512, minimum=16, maximum=65536,
          description="How many entries the catalog cache may hold."),
    Field("cache_ttl_seconds", "int", 300, minimum=1, maximum=86400,
          description="How long a cached catalog entry stays valid."),
    Field("history_retention_samples", "int", 240, minimum=16,
          maximum=100000,
          description="How many samples the telemetry history keeps."),
    Field("catalog_capture_page_seconds", "int", 5, minimum=1, maximum=300,
          description="The pause between the pages of a modded catalog read."),
    Field("max_ai_cpu_percent", "int", 50, minimum=1, maximum=100,
          description="The share of the processor the model may use."),
    Field("max_ai_memory_mb", "int", 4096, minimum=128, maximum=262144,
          description="The memory the model process may use."),

    # -- Safety ---------------------------------------------------------
    Field("helper_read_only", "bool", True,
          description="Keep the AI Helper in read-only mode."),
    Field("require_action_approval", "bool", True,
          description="Ask before every game-changing action."),
    Field("emergency_stop_enabled", "bool", True,
          description="Keep the emergency stop available at all times."),
    Field("supervisor_timeout_seconds", "int", 20, minimum=5, maximum=300,
          description="How long the supervisor waits for the game to answer."),
)

#: The settings that only take effect after the application is started
#: again. The window size and the maximized preference are read when the
#: window is created; the observation and cache limits are read when the
#: observer is created; the model endpoint and the model name are read at
#: every request. The rest are read when the service is created.
RESTART_REQUIRED_SETTINGS: frozenset[str] = frozenset({
    "start_maximized",
    "window_width",
    "window_height",
    "default_workspace",
    "theme",
    "scale_percent",
    "observation_interval_seconds",
    "observation_page_interval_seconds",
    "observation_max_requests",
    "cache_max_entries",
    "cache_ttl_seconds",
    "history_retention_samples",
    "ups_degrade_threshold",
    "ups_recover_threshold",
    "ups_critical_threshold",
    "ups_target",
    "llm_max_parallel_requests",
    "blueprint_max_machines",
    "blueprint_columns",
    "blueprint_spacing_tiles",
    "helper_production_units",
    "require_observed_catalog",
    "research_restriction",
    "max_ai_cpu_percent",
    "max_ai_memory_mb",
    "catalog_capture_page_seconds",
})


def needs_restart(names) -> tuple[str, ...]:
    """Return the settings that only take effect after a restart."""
    if not isinstance(names, (list, tuple, set, frozenset)):
        return ()
    return tuple(sorted(
        name for name in names
        if isinstance(name, str) and name in RESTART_REQUIRED_SETTINGS))


#: The settings grouped by section, in the order the interface shows them.
SECTIONS: dict[str, tuple[str, ...]] = {
    "General": (
        "start_maximized", "default_workspace", "window_width",
        "window_height", "theme", "scale_percent",
    ),
    "Factorio and Profiles": (
        "default_profile", "factorio_install_root",
        "confirm_before_launch", "confirm_before_stop",
    ),
    "AI Models": (
        "llm_provider", "llm_endpoint", "llm_model", "llm_context_tokens",
        "llm_max_output_tokens", "llm_timeout_seconds",
        "llm_max_parallel_requests",
    ),
    "AI Helper and Blueprints": (
        "helper_production_units", "blueprint_spacing_tiles",
        "blueprint_columns", "blueprint_max_machines",
        "blueprint_library_root", "require_observed_catalog",
        "research_restriction",
    ),
    "Performance and Telemetry": (
        "ups_target", "ups_degrade_threshold", "ups_recover_threshold",
        "ups_critical_threshold", "observation_interval_seconds",
        "observation_page_interval_seconds", "observation_max_requests",
        "cache_max_entries", "cache_ttl_seconds",
        "history_retention_samples", "catalog_capture_page_seconds",
        "max_ai_cpu_percent", "max_ai_memory_mb",
    ),
    "Safety": (
        "helper_read_only", "require_action_approval",
        "emergency_stop_enabled", "supervisor_timeout_seconds",
    ),
}

#: The fields by name, for a fast lookup.
FIELD_MAP: dict[str, Field] = {field.name: field for field in FIELDS}


@dataclass
class Settings:
    """The loaded settings, with the problems that were found."""

    values: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    path: Path | None = None

    def get(self, name: str) -> Any:
        """Return one setting, or its default when it is unknown."""
        field = FIELD_MAP.get(name)
        if field is None:
            raise SettingsError(f"Unknown setting {name!r}")
        return self.values.get(name, field.default)

    def as_dict(self) -> dict[str, Any]:
        """Return every setting as a plain dictionary."""
        return {name: self.get(name) for name in FIELD_MAP}

    def section(self, name: str) -> dict[str, Any]:
        """Return the settings of one section."""
        if name not in SECTIONS:
            raise SettingsError(f"Unknown settings section {name!r}")
        return {key: self.get(key) for key in SECTIONS[name]}


def default_settings_path() -> Path:
    """Return the path of the settings file."""
    override = os.environ.get("AUTOENGINEER_SETTINGS")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / DEFAULT_RELATIVE_PATH


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    """Write JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _is_secret_name(name: str) -> bool:
    """Whether a setting name looks like a credential.

    The markers are matched as whole words, so ``llm_context_tokens`` is
    a limit and not a credential, while ``llm_token`` and ``api_key`` are
    refused.
    """
    lowered = name.lower()
    if lowered in SECRET_NAME_ALLOWANCES:
        return False
    parts = set(re.split(r"[^a-z0-9]+", lowered)) - {""}
    for marker in SECRET_NAME_MARKERS:
        if marker in parts:
            return True
        # A compound marker such as ``api_key`` is also matched inside a
        # single part, so ``llm_api_key`` is refused.
        if "_" in marker and marker in lowered:
            return True
    return False


def validate_updates(updates: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a set of changed settings.

    An unknown name is refused, and so is a name that looks like a
    credential: the store must never hold a secret.
    """
    if not isinstance(updates, Mapping):
        raise SettingsError("The settings update must be a mapping")
    validated: dict[str, Any] = {}
    for name, value in updates.items():
        if not isinstance(name, str):
            raise SettingsError("A setting name must be text")
        if _is_secret_name(name):
            raise SettingsError(
                f"{name} looks like a credential. Credentials are never "
                "stored in the settings file; use the environment instead.")
        field = FIELD_MAP.get(name)
        if field is None:
            raise SettingsError(f"Unknown setting {name!r}")
        validated[name] = field.validate(value)
    return validated


def load(path: Path | None = None) -> Settings:
    """Load the settings.

    A file that does not exist yields the defaults. A file that is not
    valid JSON, that carries an unknown field, or that carries an invalid
    value does **not** raise: the problem is collected and the affected
    setting falls back to its default, so a hand-edited file can never
    stop the application from starting.
    """
    target = Path(path) if path is not None else default_settings_path()
    values = {name: field.default for name, field in FIELD_MAP.items()}
    problems: list[str] = []
    if not target.is_file():
        return Settings(values=values, problems=problems, path=target)
    try:
        document = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        problems.append(f"The settings file could not be read: {error}")
        return Settings(values=values, problems=problems, path=target)
    if not isinstance(document, Mapping):
        problems.append("The settings file is not a JSON object")
        return Settings(values=values, problems=problems, path=target)
    if document.get("schema") != SCHEMA:
        problems.append(
            f"The settings file declares schema {document.get('schema')!r}; "
            f"this build uses {SCHEMA}")
    stored = document.get("settings")
    if not isinstance(stored, Mapping):
        problems.append("The settings file has no settings section")
        return Settings(values=values, problems=problems, path=target)
    for name, value in stored.items():
        if not isinstance(name, str):
            problems.append("A setting name is not text; it was ignored")
            continue
        if _is_secret_name(name):
            problems.append(
                f"The setting {name} looks like a credential; it was ignored")
            continue
        field = FIELD_MAP.get(name)
        if field is None:
            problems.append(f"Unknown setting {name!r}; it was ignored")
            continue
        try:
            values[name] = field.validate(value)
        except SettingsError as error:
            problems.append(str(error))
    return Settings(values=values, problems=problems, path=target)


def save(settings: Settings, path: Path | None = None) -> Path:
    """Write the settings atomically and return the file it wrote."""
    target = Path(path) if path is not None else (
        settings.path or default_settings_path())
    _atomic_write(target, {
        "schema": SCHEMA,
        "settings": {name: settings.get(name) for name in FIELD_MAP},
    })
    settings.path = target
    return target


def update(
        updates: Mapping[str, Any],
        path: Path | None = None,
        *,
        settings: Settings | None = None,
) -> Settings:
    """Validate and store a set of changed settings.

    The file is only written when every value in the update is valid, so a
    rejected change leaves the stored settings untouched.
    """
    validated = validate_updates(updates)
    current = settings if settings is not None else load(path)
    current.values.update(validated)
    save(current, path)
    return current


#: The settings that the environment can override, and the variable that
#: overrides them. The environment always wins over the stored file,
#: because that is how the launcher already configures the backend and
#: the model endpoint.
ENVIRONMENT_OVERRIDES: dict[str, str] = {
    "llm_endpoint": "AUTOENGINEER_LLM_ENDPOINT",
    "llm_model": "AUTOENGINEER_LLM_MODEL",
    "llm_timeout_seconds": "AUTOENGINEER_LLM_TIMEOUT",
    "llm_context_tokens": "AUTOENGINEER_LLM_CONTEXT_TOKENS",
    "llm_max_output_tokens": "AUTOENGINEER_LLM_MAX_OUTPUT_TOKENS",
    "ups_target": "AUTOENGINEER_UPS_TARGET",
    "observation_interval_seconds": "AUTOENGINEER_OBSERVATION_INTERVAL",
    "history_retention_samples": "AUTOENGINEER_HISTORY_RETENTION",
    "default_profile": "AUTOENGINEER_PROFILE",
}


def environment_overrides() -> dict[str, str]:
    """Return the settings that the environment overrides."""
    overrides: dict[str, str] = {}
    for name, variable in ENVIRONMENT_OVERRIDES.items():
        value = os.environ.get(variable)
        if value is not None and value.strip():
            overrides[name] = value
    return overrides


def effective_settings(path: Path | None = None) -> Settings:
    """Return the settings the application actually uses.

    The stored file is loaded, the environment overrides are applied on
    top, and an environment value that is invalid is reported as a
    problem rather than silently ignored. The name of the environment
    variable is part of the message, so the user knows which variable to
    fix.
    """
    settings = load(path)
    for name, raw in environment_overrides().items():
        field = FIELD_MAP.get(name)
        if field is None:
            continue
        variable = ENVIRONMENT_OVERRIDES.get(name, name)
        try:
            candidate: Any = raw
            if field.kind == "int":
                candidate = int(raw)
            elif field.kind == "float":
                candidate = float(raw)
            settings.values[name] = field.validate(candidate)
        except (SettingsError, ValueError) as error:
            settings.problems.append(
                f"The environment variable {variable} is invalid: {error}")
    return settings


def credential_status() -> dict[str, Any]:
    """Report whether the credentials the application needs are present.

    The values themselves are never read, printed or stored: only their
    presence is reported.
    """
    password = os.environ.get(RCON_PASSWORD_VARIABLE, "")
    return {
        "rcon_password_present": bool(password.strip()),
        "rcon_password_variable": RCON_PASSWORD_VARIABLE,
        "note": ("Credentials stay in the environment and are never written "
                 "to the settings file."),
    }
