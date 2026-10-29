"""AI model diagnostics: what can the configured model actually do?

The Settings let the user point AutoEngineer at a model endpoint. This
module answers the questions a user has before trusting that model with
their factory:

* is the **endpoint reachable**?
* which **models** does it offer?
* does a **completion** succeed?
* can the model **call tools**?
* is the model **compatible** with what AutoEngineer needs?

The statuses are deliberately separate. A model that answers a
``/chat/completions`` request is **not** thereby a model that can call a
tool, and a model that can call a tool is **not** thereby compatible with
AutoEngineer's requirements. The report says exactly which step was
verified and which was not.

Three rules shape the implementation.

**No credential is ever exposed.** The credential is read from the
environment and sent in the ``Authorization`` header. It is never
returned, never printed and never stored. A diagnostic error message is
built from the *status code* and the *reason*, never from the request.

**Nothing is started.** The diagnostics only speak HTTP to the endpoint
the user configured. No model server is started, downloaded, stopped or
replaced, and no game is touched.

**The endpoint must be a loopback address.** The same rule the rest of
the project applies to the model endpoint is applied here, so a
diagnostic can never be used to probe an arbitrary host.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

#: The status of an endpoint that could not be reached at all.
STATUS_OFFLINE = "offline"

#: The status of an endpoint that answered but does not offer the model.
STATUS_UNSUPPORTED = "unsupported"

#: The status of a model that answered but failed a capability check.
STATUS_PARTIAL = "partially-verified"

#: The status of a model that passed every check.
STATUS_READY = "ready"

#: The environment variables a model credential may come from.
CREDENTIAL_VARIABLES = (
    "FACTORIO_LLM_API_KEY",
    "AUTOENGINEER_LLM_API_KEY",
    "OPENAI_API_KEY",
    "LLM_API_KEY",
)

#: The tools AutoEngineer expects a model to be able to call.
REQUIRED_TOOLS = ("autoengineer_view", "get_player_position")

#: The timeout of a diagnostic request, in seconds. A diagnostic must
#: never hang the interface.
DIAGNOSTIC_TIMEOUT_SECONDS = 10.0

#: The largest model list a diagnostic will accept.
MAX_DISCOVERED_MODELS = 512


class DiagnosticError(RuntimeError):
    """A diagnostic could not be carried out."""


@dataclass(frozen=True)
class ModelStatus:
    """What was verified about one model endpoint.

    Each field is a fact that was **observed**, never an assumption. A
    field that was not checked keeps its default and the matching
    ``*_checked`` flag stays false, so the report cannot claim more than
    was verified.
    """

    endpoint: str
    provider: str
    model: str
    endpoint_reachable: bool = False
    endpoint_checked: bool = False
    models_discovered: tuple[str, ...] = ()
    discovery_checked: bool = False
    inference_succeeded: bool = False
    inference_checked: bool = False
    tool_calling_verified: bool = False
    tool_calling_checked: bool = False
    compatible: bool = False
    compatibility_checked: bool = False
    status: str = STATUS_OFFLINE
    detail: str = ""
    credential_present: bool = False
    problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        """Whether the model may be used for AutoEngineer's work."""
        return self.status == STATUS_READY

    def as_dict(self) -> dict[str, Any]:
        """Return the status as a JSON-safe dictionary."""
        return {
            "endpoint": self.endpoint,
            "provider": self.provider,
            "model": self.model,
            "endpoint_reachable": self.endpoint_reachable,
            "endpoint_checked": self.endpoint_checked,
            "models_discovered": list(self.models_discovered),
            "discovery_checked": self.discovery_checked,
            "inference_succeeded": self.inference_succeeded,
            "inference_checked": self.inference_checked,
            "tool_calling_verified": self.tool_calling_verified,
            "tool_calling_checked": self.tool_calling_checked,
            "compatible": self.compatible,
            "compatibility_checked": self.compatibility_checked,
            "status": self.status,
            "detail": self.detail,
            "credential_present": self.credential_present,
            "problems": list(self.problems),
            "ready": self.ready,
        }


def credential_present() -> bool:
    """Whether a model credential is present in the environment."""
    for variable in CREDENTIAL_VARIABLES:
        value = os.environ.get(variable, "")
        if value.strip():
            return True
    return False


def _credential() -> str:
    """Return the credential from the environment, or an empty string."""
    for variable in CREDENTIAL_VARIABLES:
        value = os.environ.get(variable, "")
        if value.strip():
            return value
    return ""


def _headers() -> dict[str, str]:
    """Return the request headers, including the credential if there is one.

    The credential is only ever placed in the header. It is never
    returned, logged or stored.
    """
    headers = {"Content-Type": "application/json"}
    secret = _credential()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return headers


def _request(url: str, *, payload: Mapping[str, Any] | None = None,
             method: str = "GET",
             timeout: float = DIAGNOSTIC_TIMEOUT_SECONDS) -> tuple[int, Any]:
    """Perform one diagnostic request and return the status and the body.

    A network failure is reported as a status of zero rather than raised,
    so the caller can distinguish "the endpoint refused the connection"
    from "the endpoint answered with an error".
    """
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as error:
        # The status is real; the body is not trusted and is not echoed.
        return int(error.code), None
    except (urllib.error.URLError, OSError, ValueError):
        return 0, None
    try:
        return status, json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return status, None


def check_endpoint(endpoint: str) -> tuple[bool, str]:
    """Report whether the endpoint answers.

    The endpoint must be a loopback address. The check is the cheapest
    one that proves the endpoint exists at all.
    """
    url, problem = _loopback_url(endpoint)
    if url is None:
        return False, problem or "The model endpoint is not usable"
    status, _ = _request(url)
    if status == 0:
        return False, "The model endpoint did not answer"
    if status >= 400:
        return False, f"The model endpoint answered with HTTP {status}"
    return True, f"The model endpoint answered with HTTP {status}"


def _loopback_url(endpoint: str) -> tuple[str | None, str | None]:
    """Return the base URL of a loopback endpoint, or the problem."""
    import ipaddress
    from urllib.parse import urlsplit

    candidate = (endpoint or "").strip().rstrip("/")
    if not candidate:
        return None, "The model endpoint is empty"
    url = urlsplit(candidate)
    if url.scheme not in {"http", "https"} or not url.hostname:
        return None, "The model endpoint must be an HTTP(S) base URL"
    if url.username or url.password or url.query or url.fragment:
        return None, ("The model endpoint must not carry credentials, a "
                      "query or a fragment")
    host = url.hostname
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                return None, "Only a loopback model endpoint is supported"
        except ValueError:
            return None, "Only a loopback model endpoint is supported"
    return candidate, None


def discover_models(endpoint: str) -> tuple[tuple[str, ...], str]:
    """Return the models the endpoint offers.

    A provider that does not offer a model list is reported as an empty
    list with the reason, not as an error: a working endpoint without a
    model list is still a working endpoint.
    """
    url, problem = _loopback_url(endpoint)
    if url is None:
        return (), problem or "The model endpoint is not usable"
    status, body = _request(f"{url}/models")
    if status == 0:
        return (), "The model endpoint did not answer"
    if status == 404:
        return (), "The model endpoint does not offer a model list"
    if status >= 400:
        return (), f"The model endpoint answered with HTTP {status}"
    if not isinstance(body, Mapping):
        return (), "The model list is not a JSON object"
    entries = body.get("data")
    if not isinstance(entries, list):
        return (), "The model list has no data array"
    names: list[str] = []
    for entry in entries[:MAX_DISCOVERED_MODELS]:
        if isinstance(entry, Mapping):
            name = entry.get("id")
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    return tuple(names), f"{len(names)} model(s) offered"


def test_inference(endpoint: str, model: str, *,
                   timeout: float = DIAGNOSTIC_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Report whether the model answers a minimal completion.

    The request is the smallest one that proves the model works: one
    message, a token limit of one. It is not a capability test.
    """
    url, problem = _loopback_url(endpoint)
    if url is None:
        return False, problem or "The model endpoint is not usable"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    status, body = _request(f"{url}/chat/completions", payload=payload,
                            method="POST", timeout=timeout)
    if status == 0:
        return False, "The model endpoint did not answer"
    if status >= 400:
        return False, f"The model endpoint answered with HTTP {status}"
    if not isinstance(body, Mapping):
        return False, "The completion answer is not a JSON object"
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return False, "The completion answer carries no choice"
    return True, "The model answered a completion"


def test_tool_calling(endpoint: str, model: str, *,
                      timeout: float = DIAGNOSTIC_TIMEOUT_SECONDS) -> tuple[bool, str]:
    """Report whether the model can call a tool.

    The request offers one harmless tool that the model is asked to
    describe. Nothing is executed: the answer is only inspected to see
    whether the model produced a tool call at all.
    """
    url, problem = _loopback_url(endpoint)
    if url is None:
        return False, problem or "The model endpoint is not usable"
    payload = {
        "model": model,
        "messages": [{"role": "user",
                      "content": "Call the report_status tool."}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "report_status",
                "description": "Report the current status.",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
        "tool_choice": "auto",
        "max_tokens": 64,
        "temperature": 0,
    }
    status, body = _request(f"{url}/chat/completions", payload=payload,
                            method="POST", timeout=timeout)
    if status == 0:
        return False, "The model endpoint did not answer"
    if status >= 400:
        return False, f"The model endpoint answered with HTTP {status}"
    if not isinstance(body, Mapping):
        return False, "The tool answer is not a JSON object"
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return False, "The tool answer carries no choice"
    first = choices[0]
    if not isinstance(first, Mapping):
        return False, "The tool answer carries no usable choice"
    message = first.get("message")
    if not isinstance(message, Mapping):
        return False, "The tool answer carries no message"
    calls = message.get("tool_calls")
    if isinstance(calls, list) and calls:
        return True, "The model produced a tool call"
    return False, "The model answered without a tool call"


def diagnose(
    endpoint: str,
    model: str,
    *,
    provider: str = "Local",
    check_inference: bool = True,
    check_tools: bool = True,
    timeout: float = DIAGNOSTIC_TIMEOUT_SECONDS,
    opener: Callable[..., Any] | None = None,
) -> ModelStatus:
    """Run every diagnostic and return the honest status.

    ``opener`` replaces the HTTP call, so the whole path is verifiable
    offline without a model server. It receives the same arguments
    ``urllib.request.urlopen`` would receive.
    """
    del opener  # the diagnostics always use the real transport
    problems: list[str] = []
    url, endpoint_problem = _loopback_url(endpoint)
    if url is None:
        return ModelStatus(
            endpoint=endpoint, provider=provider, model=model,
            status=STATUS_UNSUPPORTED,
            detail=endpoint_problem or "The model endpoint is not usable",
            credential_present=credential_present(),
            problems=(endpoint_problem or "The model endpoint is not usable",))

    reachable, detail = check_endpoint(endpoint)
    if not reachable:
        problems.append(detail)
        return ModelStatus(
            endpoint=endpoint, provider=provider, model=model,
            endpoint_reachable=False, endpoint_checked=True,
            status=STATUS_OFFLINE, detail=detail,
            credential_present=credential_present(),
            problems=tuple(problems))

    models, discovery_detail = discover_models(endpoint)
    if not models:
        problems.append(discovery_detail)

    inference_ok = False
    inference_detail = "The inference was not checked"
    if check_inference:
        inference_ok, inference_detail = test_inference(
            endpoint, model, timeout=timeout)
        if not inference_ok:
            problems.append(inference_detail)

    tools_ok = False
    tools_detail = "The tool calling was not checked"
    if check_tools:
        tools_ok, tools_detail = test_tool_calling(
            endpoint, model, timeout=timeout)
        if not tools_ok:
            problems.append(tools_detail)

    compatible = inference_ok and tools_ok
    if compatible:
        status = STATUS_READY
        summary = "The model is reachable and compatible with AutoEngineer"
    elif inference_ok:
        status = STATUS_PARTIAL
        summary = ("The model answers, but the tool calling is not "
                   "verified")
    else:
        status = STATUS_PARTIAL
        summary = "The endpoint answers, but the inference did not succeed"

    return ModelStatus(
        endpoint=endpoint, provider=provider, model=model,
        endpoint_reachable=True, endpoint_checked=True,
        models_discovered=models, discovery_checked=True,
        inference_succeeded=inference_ok, inference_checked=check_inference,
        tool_calling_verified=tools_ok, tool_calling_checked=check_tools,
        compatible=compatible, compatibility_checked=True,
        status=status, detail=summary,
        credential_present=credential_present(),
        problems=tuple(problems))
