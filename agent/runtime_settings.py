"""The bridge between the stored settings and the running services.

The Settings screen stores values in ``settings_store``. The services read
their configuration from ``autoengineer_config.get_settings()`` and from
their own constructors. This module is the single place where a stored
setting becomes a runtime value, so a control in the interface and the
service that consumes it can never drift apart.

Three rules shape the design.

**Nothing is read at import time.** The earlier code did
``API = get_settings()["llm_api_url"]`` at module level, which froze the
endpoint when the module was first imported: a Settings change could never
reach it. Every accessor here is a *function*, so the value is read when
it is used.

**A broken or unsafe configuration falls back to the safe default.** A
model endpoint that is not a loopback address, a timeout of zero or a
cache limit of nothing are all refused, and the previous working value is
kept. The service keeps working with a known-good configuration instead
of failing.

**No credential is ever read, returned or logged.** The credential stays
in the environment; this module only reports whether one is present.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The provider names the Settings offer and what they mean.
PROVIDER_LOCAL = "Local"
PROVIDER_OPENAI_COMPATIBLE = "OpenAI-compatible"
PROVIDER_OLLAMA = "Ollama"
PROVIDER_LM_STUDIO = "LM Studio"
PROVIDER_LLAMA_CPP = "llama.cpp"

#: The providers that serve an OpenAI-compatible ``/chat/completions``
#: API. Every supported provider speaks it, so the runtime does not need a
#: separate client per provider.
OPENAI_COMPATIBLE_PROVIDERS = frozenset({
    PROVIDER_LOCAL,
    PROVIDER_OPENAI_COMPATIBLE,
    PROVIDER_OLLAMA,
    PROVIDER_LM_STUDIO,
    PROVIDER_LLAMA_CPP,
})

#: The default model endpoint, used when the stored one is unusable.
DEFAULT_MODEL_ENDPOINT = "http://127.0.0.1:8080/v1"

#: The default request timeout in seconds.
DEFAULT_TIMEOUT_SECONDS = 120

#: The default number of model requests that may run at the same time.
DEFAULT_PARALLEL_REQUESTS = 1

#: The default observation interval in seconds.
DEFAULT_OBSERVATION_INTERVAL = 20

#: The default observation page interval in seconds.
DEFAULT_PAGE_INTERVAL = 120

#: The default observation request budget per round.
DEFAULT_REQUEST_BUDGET = 4

#: The default cache entry limit.
DEFAULT_CACHE_ENTRIES = 512

#: The default cache lifetime in seconds.
DEFAULT_CACHE_TTL = 300

#: The default telemetry history length in samples.
DEFAULT_HISTORY_SAMPLES = 240


class RuntimeSettingError(ValueError):
    """A stored setting could not be turned into a usable runtime value."""


@dataclass(frozen=True)
class ModelRuntime:
    """The model configuration the inference services must use."""

    provider: str
    endpoint: str
    model: str
    context_tokens: int
    max_output_tokens: int
    timeout_seconds: int
    max_parallel_requests: int
    credential_present: bool
    problem: str | None = None

    @property
    def usable(self) -> bool:
        """Whether the model can be addressed with this configuration."""
        return self.problem is None

    def as_dict(self) -> dict[str, Any]:
        """Return the configuration without the credential itself."""
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "model": self.model,
            "context_tokens": self.context_tokens,
            "max_output_tokens": self.max_output_tokens,
            "timeout_seconds": self.timeout_seconds,
            "max_parallel_requests": self.max_parallel_requests,
            "credential_present": self.credential_present,
            "problem": self.problem,
            "usable": self.usable,
        }


@dataclass(frozen=True)
class TelemetryRuntime:
    """The observation and cache configuration the telemetry uses."""

    observation_interval_seconds: int
    page_interval_seconds: int
    request_budget: int
    cache_max_entries: int
    cache_ttl_seconds: int
    history_retention_samples: int
    problem: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the configuration as a plain dictionary."""
        return {
            "observation_interval_seconds": self.observation_interval_seconds,
            "page_interval_seconds": self.page_interval_seconds,
            "request_budget": self.request_budget,
            "cache_max_entries": self.cache_max_entries,
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "history_retention_samples": self.history_retention_samples,
            "problem": self.problem,
        }


def _int_setting(settings: Any, name: str, default: int,
                 minimum: int, maximum: int) -> int:
    """Return one integer setting, clamped to its safe range."""
    try:
        value = settings.get(name)
    except Exception:
        return default
    if type(value) is not int:
        return default
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def _text_setting(settings: Any, name: str, default: str) -> str:
    """Return one text setting, or the default when it is empty."""
    try:
        value = settings.get(name)
    except Exception:
        return default
    if not isinstance(value, str):
        return default
    return value.strip() or default


def _loopback_endpoint(value: str) -> tuple[str | None, str | None]:
    """Return the endpoint and the problem, if the endpoint is unusable.

    Only a loopback address is accepted, exactly as the backend
    configuration already requires. A remote endpoint would send the
    user's observations and prompts to another machine.
    """
    import ipaddress
    from urllib.parse import urlsplit

    candidate = value.strip().rstrip("/")
    if not candidate:
        return None, "The model endpoint is empty"
    url = urlsplit(candidate)
    if url.scheme not in {"http", "https"} or not url.hostname:
        return None, "The model endpoint must be an HTTP(S) base URL"
    if url.username or url.password or url.query or url.fragment:
        return None, (
            "The model endpoint must not carry credentials, a query or a "
            "fragment")
    host = url.hostname
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                return None, "Only a loopback model endpoint is supported"
        except ValueError:
            return None, "Only a loopback model endpoint is supported"
    return candidate, None


def model_runtime(settings: Any = None) -> ModelRuntime:
    """Return the model configuration the inference services must use.

    The stored settings are the source. A value that is missing or unsafe
    falls back to the safe default, and the reason is reported so the
    interface can show it.
    """
    if settings is None:
        settings = _load_settings()
    provider = _text_setting(settings, "llm_provider", PROVIDER_LOCAL)
    if provider not in OPENAI_COMPATIBLE_PROVIDERS:
        provider = PROVIDER_LOCAL
    endpoint, endpoint_problem = _loopback_endpoint(
        _text_setting(settings, "llm_endpoint", DEFAULT_MODEL_ENDPOINT))
    model = _text_setting(settings, "llm_model", "")
    context = _int_setting(settings, "llm_context_tokens", 8192, 512, 1048576)
    output = _int_setting(settings, "llm_max_output_tokens", 2048, 64, 131072)
    timeout = _int_setting(settings, "llm_timeout_seconds",
                           DEFAULT_TIMEOUT_SECONDS, 5, 3600)
    parallel = _int_setting(settings, "llm_max_parallel_requests",
                             DEFAULT_PARALLEL_REQUESTS, 1, 8)
    credential = bool(_credential_present())
    problem = endpoint_problem
    if not credential:
        # A missing credential is not a configuration error: a local model
        # needs none, and a remote one is not reachable anyway.
        problem = problem or None
    return ModelRuntime(
        provider=provider,
        endpoint=endpoint or DEFAULT_MODEL_ENDPOINT,
        model=model,
        context_tokens=context,
        max_output_tokens=output,
        timeout_seconds=timeout,
        max_parallel_requests=parallel,
        credential_present=credential,
        problem=problem,
    )


def telemetry_runtime(settings: Any = None) -> TelemetryRuntime:
    """Return the observation and cache configuration the telemetry uses."""
    if settings is None:
        settings = _load_settings()
    return TelemetryRuntime(
        observation_interval_seconds=_int_setting(
            settings, "observation_interval_seconds",
            DEFAULT_OBSERVATION_INTERVAL, 1, 600),
        page_interval_seconds=_int_setting(
            settings, "observation_page_interval_seconds",
            DEFAULT_PAGE_INTERVAL, 5, 3600),
        request_budget=_int_setting(
            settings, "observation_max_requests", DEFAULT_REQUEST_BUDGET, 1, 64),
        cache_max_entries=_int_setting(
            settings, "cache_max_entries", DEFAULT_CACHE_ENTRIES, 16, 65536),
        cache_ttl_seconds=_int_setting(
            settings, "cache_ttl_seconds", DEFAULT_CACHE_TTL, 1, 86400),
        history_retention_samples=_int_setting(
            settings, "history_retention_samples",
            DEFAULT_HISTORY_SAMPLES, 16, 100000),
    )


def _load_settings() -> Any:
    """Return the effective settings, or an empty mapping on failure."""
    try:
        from settings_store import effective_settings

        return effective_settings()
    except Exception:
        return {}


def _credential_present() -> bool:
    """Whether a model credential is present in the environment."""
    import os

    for variable in ("FACTORIO_LLM_API_KEY", "OPENAI_API_KEY",
                      "LLM_API_KEY", "AUTOENGINEER_LLM_API_KEY"):
        value = os.environ.get(variable, "")
        if value.strip():
            return True
    return False


def model_endpoint(settings: Any = None) -> str:
    """Return the model endpoint the inference services must use.

    This is a **function**, not a module-level constant, so a Settings
    change is picked up by the next request instead of being frozen at
    import time.
    """
    return model_runtime(settings).endpoint


def model_name(settings: Any = None) -> str:
    """Return the configured model name, or an empty string."""
    return model_runtime(settings).model


def request_timeout(settings: Any = None) -> float:
    """Return the request timeout in seconds."""
    return float(model_runtime(settings).timeout_seconds)


def observation_interval(settings: Any = None) -> float:
    """Return the observation interval in seconds."""
    return float(telemetry_runtime(settings).observation_interval_seconds)


def observation_page_interval(settings: Any = None) -> float:
    """Return the observation page interval in seconds."""
    return float(telemetry_runtime(settings).page_interval_seconds)


def observation_request_budget(settings: Any = None) -> int:
    """Return the observation request budget per round."""
    return telemetry_runtime(settings).request_budget


def cache_limits(settings: Any = None) -> tuple[int, float]:
    """Return the cache entry limit and the cache lifetime in seconds."""
    runtime = telemetry_runtime(settings)
    return runtime.cache_max_entries, float(runtime.cache_ttl_seconds)


def history_retention(settings: Any = None) -> int:
    """Return how many telemetry samples the history keeps."""
    return telemetry_runtime(settings).history_retention_samples


def requests_per_minute_budget(settings: Any = None) -> int:
    """Return the observation request budget the coordinator must use.

    The coordinator counts the requests it may start **per minute**, while
    the Settings describe the requests of **one round** and how often a
    round happens. The budget is therefore the number of rounds per minute
    times the requests per round, with a floor so the coordinator always
    admits at least one request and a ceiling so a fast interval cannot
    flood the game.
    """
    runtime = telemetry_runtime(settings)
    interval = runtime.observation_interval_seconds
    rounds = max(1, 60 // max(1, interval))
    budget = rounds * runtime.request_budget
    return max(1, min(budget, 600))


def max_in_flight_limit(settings: Any = None) -> int:
    """Return how many observation requests may run at the same time.

    The concurrency limit is at most the request budget, so the
    coordinator never allows more work in flight than the budget permits.
    """
    runtime = telemetry_runtime(settings)
    return max(1, min(runtime.request_budget, 8))


def runtime_report(settings: Any = None) -> dict[str, Any]:
    """Return a JSON-safe report of every runtime configuration."""
    model = model_runtime(settings)
    telemetry = telemetry_runtime(settings)
    return {
        "model": model.as_dict(),
        "telemetry": telemetry.as_dict(),
    }
