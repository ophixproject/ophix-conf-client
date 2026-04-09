"""
ophix_conf_client.core.http
~~~~~~~~~~~~~~~~~~~~~~~~~~~
HTTP plumbing for the Ophix configuration client.
"""

import getpass
import platform
import sys
from typing import Optional

from ophix_conf_client._version import __version__
from .env import in_venv

try:
    import distro as _distro
except ImportError:
    _distro = None


def _detect_os() -> str:
    system = platform.system()
    if system == "Linux" and _distro:
        name = _distro.name(pretty=True)
        version = _distro.version(best=True)
        return f"{name} {version}".strip() if name else "Linux"
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0]}"
    if system == "Windows":
        return f"Windows {platform.release()}"
    return system


def _detect_invocation() -> str:
    if sys.argv:
        return " ".join(sys.argv[:2])
    return "unknown"


def build_headers(api_token: Optional[str] = None) -> dict:
    """Build the standard X-Ophix-* diagnostic headers."""
    headers: dict[str, str] = {
        "X-Ophix-Client-Version":  __version__,
        "X-Ophix-Python-Version":  (
            f"{sys.version_info.major}."
            f"{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "X-Ophix-OS-Type":         platform.system().lower(),
        "X-Ophix-OS":              _detect_os(),
        "X-Ophix-User":            getpass.getuser(),
        "X-Ophix-Invocation":      _detect_invocation(),
    }
    venv_path = in_venv()
    if venv_path:
        headers["X-Ophix-Venv-Name"] = venv_path.name
    if api_token:
        headers["Authorization"] = f"Token {api_token}"
    return headers


def extract_server_message(response) -> str:
    try:
        body = response.json()
        return body.get("detail") or body.get("error") or str(body)
    except Exception:
        return response.text.strip() or f"HTTP {response.status_code}"
