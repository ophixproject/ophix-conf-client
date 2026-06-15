"""
conf_client.core.env
~~~~~~~~~~~~~~~~~~~~~~~~~~
Environment configuration resolution for the Ophix configuration client.

Reserved environment variable names
-------------------------------------
CONFSERVER_URL        Base URL of the configuration server
CONFSERVER_API_TOKEN  64-character hex API token
CONFSERVER_CA_CERT    Path to CA certificate (optional)

These names are intentionally prefixed so the .conf.env file can
coexist with other application environment variables without collision.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv, find_dotenv, set_key

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENV_FILE_NAME = ".conf.env"

RESERVED_KEY_NAMES: Dict[str, str] = {
    "SERVER":    "CONFSERVER_URL",
    "API_TOKEN": "CONFSERVER_API_TOKEN",
    "CA_CERT":   "CONFSERVER_CA_CERT",
}

RESERVED_ENV_VARS: Set[str] = set(RESERVED_KEY_NAMES.values())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_get(key: str) -> Optional[str]:
    return os.getenv(RESERVED_KEY_NAMES.get(key, key))


def find_project_root() -> Path:
    venv_root = in_venv()
    if venv_root:
        return venv_root.parent

    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if any((parent / marker).exists()
               for marker in ("requirements.txt", ".git", ".env")):
            return parent
    return cwd


def in_venv() -> Optional[Path]:
    if hasattr(sys, "real_prefix") or sys.prefix != sys.base_prefix:
        return Path(sys.prefix)
    return None


def determine_deployment_ref() -> str:
    venv_root = in_venv()
    if not venv_root:
        raise RuntimeError(
            "Cannot determine deployment ref: not running inside a virtual environment."
        )
    return venv_root.parent.name


def ensure_env_file() -> Path:
    existing = find_dotenv(filename=ENV_FILE_NAME, usecwd=True)
    if existing:
        env_path = Path(existing)
        try:
            if (env_path.stat().st_mode & 0o777) != 0o600:
                os.chmod(env_path, 0o600)
                print("✓ Environment file permissions secured (600)")
        except Exception:
            pass
        return env_path

    env_path = find_project_root() / ENV_FILE_NAME
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    print("✓ Environment file created with secure permissions (600)")
    return env_path


def set_env_variable(var: str, value: str, verbose: bool = True) -> None:
    env_file = ensure_env_file()
    set_key(str(env_file), var, value)
    if verbose:
        print(f"Set {var} in {ENV_FILE_NAME}")


def resolve_server_config(
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
    *,
    exit_on_error: bool = True,
    return_env_path: bool = False,
    ignore_missing: Optional[List[str]] = None,
) -> tuple:
    """
    Resolve server connection settings from arguments, env file, or environment.

    Resolution order (first non-empty wins):
      1. Explicit keyword arguments
      2. .conf.env
      3. Process environment
    """
    if ignore_missing is None:
        ignore_missing = []

    env_path_found: Optional[str] = None
    candidate = find_project_root() / ENV_FILE_NAME
    if candidate.exists():
        load_dotenv(str(candidate))
        env_path_found = str(candidate)
    elif not in_venv():
        conf_env = find_dotenv(filename=ENV_FILE_NAME, usecwd=True)
        if conf_env:
            load_dotenv(conf_env)
            env_path_found = conf_env

    server_url = server_url or _env_get("SERVER")
    api_token  = api_token  or _env_get("API_TOKEN")
    ca_cert    = ca_cert    or _env_get("CA_CERT")

    errors: List[str] = []

    token_var  = RESERVED_KEY_NAMES["API_TOKEN"]
    server_var = RESERVED_KEY_NAMES["SERVER"]

    if not server_url and server_var not in ignore_missing:
        errors.append(f"Server URL not set ({server_var})")

    if (not api_token or len(api_token) != 64) and token_var not in ignore_missing:
        errors.append(
            f"API token missing or invalid ({token_var}; must be 64 hex chars)"
        )

    if ca_cert:
        ca_path = Path(ca_cert)
        if not ca_path.exists():
            errors.append(f"CA cert file not found: {ca_cert}")
        else:
            ca_cert = str(ca_path.resolve())

    if errors:
        msg = "\n".join(errors)
        if exit_on_error:
            print(f"Error resolving server config:\n{msg}")
            sys.exit(1)
        else:
            raise ValueError(msg)

    if return_env_path:
        return server_url, api_token, ca_cert, env_path_found

    return server_url, api_token, ca_cert
