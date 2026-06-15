"""
conf_client.core.env
~~~~~~~~~~~~~~~~~~~~~~~~~~
Environment helpers for the Ophix configuration client.

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
from typing import Dict, Optional, Set

from dotenv import find_dotenv, set_key

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
