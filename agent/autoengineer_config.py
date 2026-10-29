import ipaddress
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from app_runtime import data_root
from mode_policy import load_mode

PROJECT_ROOT = data_root()
DEFAULTS = {
    "dotnet_command": "dotnet",
    "mcp_server_dll": "external/FactorioMCP/FactorioMCP/bin/Release/net9.0/FactorioMCP.dll",
    "rcon_host": "127.0.0.1",
    "rcon_port": 27015,
    "llm_api_url": "http://127.0.0.1:8080/v1",
    "llm_model": "phi-4-mini-instruct",
}


def get_settings():
    """Read optional local JSON, resolving paths relative to this project.

    The local JSON file is the base. The **Settings screen** is overlaid
    on top of it, so a change made in the interface reaches every service
    that reads its configuration through this function.

    The order matters and it is a security property: the base
    configuration is validated **first**, and only a valid base is
    overlaid. An invalid base configuration is therefore always refused,
    even when the Settings would have replaced the offending value. The
    overlaid result is validated again, so an overlay can never smuggle an
    unusable value past the checks.

    A stored setting that is missing, broken or unsafe is **ignored** and
    the base configuration is kept. The service therefore keeps working
    with a known-good configuration instead of failing.
    """
    config_path = Path(os.environ.get("AUTOENGINEER_CONFIG", "config.local.json"))
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    overrides = {}
    if config_path.exists():
        try:
            overrides = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raise ValueError("Could not read local configuration JSON") from None
    if not isinstance(overrides, dict) or set(overrides) - set(DEFAULTS):
        raise ValueError(
            "Configuration must contain only supported example keys; credentials belong in the environment"
        )
    settings = DEFAULTS | overrides
    _validate_settings(settings)
    settings = _overlay_stored_settings(settings)
    _validate_settings(settings)
    settings["llm_api_url"] = settings["llm_api_url"].rstrip("/")
    return settings


def _validate_settings(settings):
    """Refuse a configuration that is not usable.

    The model endpoint must be an HTTP(S) base URL without credentials, a
    query or a fragment, and both the RCON host and the model host must
    be loopback. A credential in the URL is never echoed in the error.
    """
    for key in DEFAULTS.keys() - {"rcon_port"}:
        if not isinstance(settings[key], str) or not settings[key].strip():
            raise ValueError(f"Configuration requires a nonempty {key}")
    if type(settings["rcon_port"]) is not int or not 1 <= settings["rcon_port"] <= 65535:
        raise ValueError("rcon_port must be an integer between 1 and 65535")
    url = urlsplit(settings["llm_api_url"])
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "llm_api_url must be an HTTP(S) base URL without credentials, query, or fragment"
        )
    for host in (settings["rcon_host"], url.hostname):
        if host != "localhost":
            try:
                if not ipaddress.ip_address(host).is_loopback:
                    raise ValueError()
            except ValueError:
                raise ValueError("Only loopback RCON and model endpoints are supported") from None


def _overlay_stored_settings(settings):
    """Overlay the Settings screen values onto the base configuration.

    Only the model endpoint and the model name are overlaid, because those
    are the values the Settings own and the services read. The endpoint is
    validated first: a value that is not a loopback address is ignored
    rather than applied, so a wrong setting can never point the
    application's prompts at another machine.
    """
    try:
        from runtime_settings import model_runtime
    except Exception:
        return settings
    try:
        runtime = model_runtime()
    except Exception:
        return settings
    if runtime.problem is not None:
        # The stored endpoint is unusable; the base configuration stays.
        return settings
    overlaid = dict(settings)
    overlaid["llm_api_url"] = runtime.endpoint
    if runtime.model:
        overlaid["llm_model"] = runtime.model
    return overlaid


def mcp_parameters():
    """Fail before backend launch if credentials or prerequisites are missing."""
    policy = load_mode()
    settings = get_settings()
    password = os.environ.get("FACTORIO_RCON_PASSWORD")
    if not password or not password.strip():
        raise ValueError(
            "Set FACTORIO_RCON_PASSWORD in the environment; no default password is provided"
        )
    dll = Path(settings["mcp_server_dll"])
    if not dll.is_absolute():
        dll = PROJECT_ROOT / dll
    if not dll.is_file():
        raise FileNotFoundError(
            "Configured FactorioMCP DLL is missing; build the separately obtained backend first"
        )
    command = shutil.which(settings["dotnet_command"])
    if command is None:
        raise FileNotFoundError(
            "Configured dotnet command is unavailable; install the required runtime or configure its location"
        )
    from mcp import StdioServerParameters

    # The backend receives no cloud keys, model settings or parent config path.
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "DOTNET_ROOT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env.update(
        {
            "FACTORIO_RCON_HOST": settings["rcon_host"],
            "AUTOENGINEER_BACKEND_MODE": policy.mode,
            "FACTORIO_RCON_PORT": str(settings["rcon_port"]),
            "FACTORIO_RCON_PASSWORD": password,
            "Logging__LogLevel__Default": "None",
            "Logging__LogLevel__Microsoft": "None",
        }
    )
    runtime = PROJECT_ROOT / ".local/backend"
    runtime.mkdir(parents=True, exist_ok=True)
    env["FACTORIO_GOALS_FILE"] = str(runtime / "goals.json")
    env["FACTORIO_BUILDINGS_FILE"] = str(runtime / "buildings.json")
    return StdioServerParameters(
        command=command, args=[str(dll.resolve())], env=env, cwd=str(runtime)
    )
