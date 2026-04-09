"""
ophix_conf_client.core.api
~~~~~~~~~~~~~~~~~~~~~~~~~~
Configuration and client self-management API calls.

Public functions
----------------
fetch_config(name, ...)           GET  /api/configs/<n>/
create_config(name, fmt, ...) POST /api/configs/<n>/
update_config(name, fmt, ...) PUT  /api/configs/<n>/
delete_config(name, ...)          DELETE /api/configs/<n>/
get_config(env_var_name)          convenience wrapper for tier-2 clients
fetch_client_info(...)            GET  /api/client/self/
update_client(...)                PATCH /api/client/self/update/
rotate_token(...)                 POST /api/client/self/rotate-token/
register_client(name, ...)        POST /api/register/
download_ca_cert(...)             GET  /api/server/ca-cert/
"""

import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Optional

import requests
import urllib3

from .env import (
    RESERVED_KEY_NAMES,
    ENV_FILE_NAME,
    resolve_server_config,
    in_venv,
    determine_deployment_ref,
    set_env_variable,
    find_project_root,
)
from .http import build_headers, extract_server_message


def _verify(ca_cert: str | None):
    return ca_cert if ca_cert else True


def _raise_for_status(resp: requests.Response, context: str) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        msg = extract_server_message(resp)
        raise requests.HTTPError(f"{context}: {msg}", response=resp) from exc


# ---------------------------------------------------------------------------
# Configuration CRUD
# ---------------------------------------------------------------------------

def fetch_config(
    name: str,
    server_url: str | None = None,
    api_token: str | None = None,
    ca_cert: str | None = None,
) -> tuple[str, str, str]:
    """
    Fetch a named configuration from the server.

    Returns a tuple of (content, format_name, updated_at).

    The content is the raw configuration string exactly as stored on
    the server.  The format_name (e.g. 'yaml', 'json') and updated_at
    timestamp are read from the response headers.

    Raises
    ------
    ValueError
        If *name* is empty.
    requests.HTTPError
        On 4xx/5xx responses.
    """
    if not name or not str(name).strip():
        raise ValueError("Configuration name must not be empty")

    server_url, api_token, ca_cert = resolve_server_config(
        server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    resp = requests.get(url, headers=build_headers(api_token), verify=_verify(ca_cert))

    if resp.status_code == 404:
        raise requests.HTTPError(
            f"Configuration '{name}' not found.", response=resp
        )

    _raise_for_status(resp, f"Failed to fetch configuration '{name}'")

    content = resp.text
    format_name = resp.headers.get("X-Ophix-Config-Format", "")
    updated_at = resp.headers.get("X-Ophix-Config-Updated", "")

    return content, format_name, updated_at


def create_config(
    name: str,
    format: str,
    content: str,
    description: str | None = None,
    server_url: str | None = None,
    api_token: str | None = None,
    ca_cert: str | None = None,
) -> dict:
    """
    Create a new configuration on the server.

    Parameters
    ----------
    name
        Unique name for this configuration.
    format
        Format name as registered on the server (e.g. 'yaml', 'json').
    content
        Raw configuration content. Validated server-side before storing.
    description
        Optional human-readable description.
    """
    server_url, api_token, ca_cert = resolve_server_config(
        server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    payload: dict[str, Any] = {
        "format": format,
        "content": content,
    }
    if description is not None:
        payload["description"] = description

    resp = requests.post(
        url,
        headers=build_headers(api_token),
        json=payload,
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, f"Failed to create configuration '{name}'")
    return resp.json()


def update_config(
    name: str,
    format: str,
    content: str,
    description: str | None = None,
    server_url: str | None = None,
    api_token: str | None = None,
    ca_cert: str | None = None,
) -> dict:
    """
    Overwrite an existing configuration.

    Requires ``can_update`` on the ClientConfiguration join record.
    """
    server_url, api_token, ca_cert = resolve_server_config(
        server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    payload: dict[str, Any] = {
        "format": format,
        "content": content,
    }
    if description is not None:
        payload["description"] = description

    resp = requests.put(
        url,
        headers=build_headers(api_token),
        json=payload,
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, f"Failed to update configuration '{name}'")
    return resp.json()


def delete_config(
    name: str,
    server_url: str | None = None,
    api_token: str | None = None,
    ca_cert: str | None = None,
) -> dict:
    """
    Delete a configuration.

    Requires ``can_delete`` on the join record **and**
    ``ENABLE_ARTIFACT_DELETE=true`` on the server.
    """
    server_url, api_token, ca_cert = resolve_server_config(
        server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    resp = requests.delete(
        url,
        headers=build_headers(api_token),
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, f"Failed to delete configuration '{name}'")
    return resp.json()


# ---------------------------------------------------------------------------
# Convenience wrapper for tier-2 clients
# ---------------------------------------------------------------------------

def get_config(env_var_name: str) -> str:
    """
    Fetch the raw content of a configuration whose name is stored in
    an environment variable.

    This is the primary entry point for tier-2 clients::

        from ophix_conf_client import get_config

        nginx_conf = get_config("NGINX_CONFIG_NAME")
        # nginx_conf is the raw config string

    Parameters
    ----------
    env_var_name
        Name of the environment variable that holds the configuration
        name (not the configuration content itself).

    Returns
    -------
    str
        The raw configuration content string.

    Exits
    -----
    Calls sys.exit(1) on any failure so tier-2 callers don't need to
    handle exceptions.
    """
    from dotenv import find_dotenv, load_dotenv
    conf_env = find_dotenv(filename=ENV_FILE_NAME, usecwd=True)
    if conf_env:
        load_dotenv(conf_env)

    config_name = os.getenv(env_var_name)
    if not config_name:
        print(f"Environment variable '{env_var_name}' is not set. Aborting.")
        sys.exit(1)

    try:
        content, _, _ = fetch_config(config_name)
        return content
    except Exception as exc:
        print(f"Failed to fetch configuration '{config_name}': {exc}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Client self-management
# (identical pattern to cred-client — standard base API)
# ---------------------------------------------------------------------------

def fetch_client_info(
    server_url: str | None = None,
    api_token: str | None = None,
    ca_cert: str | None = None,
) -> dict:
    server_url, api_token, ca_cert = resolve_server_config(
        server_url, api_token, ca_cert
    )
    url = f"{server_url.rstrip('/')}/api/client/self/"
    resp = requests.get(url, headers=build_headers(api_token), verify=_verify(ca_cert))
    _raise_for_status(resp, "Failed to fetch client info")
    return resp.json()


def update_client(
    deployment_ref: str | None = None,
    server_url: str | None = None,
    api_token: str | None = None,
    ca_cert: str | None = None,
) -> dict:
    server_url, api_token, ca_cert = resolve_server_config(
        server_url, api_token, ca_cert
    )
    venv_path = in_venv()
    if not venv_path:
        raise RuntimeError("Cannot detect virtual environment.")

    payload: dict[str, Any] = {
        "venv_name": venv_path.name,
        "venv_path": str(venv_path.resolve()),
    }
    if deployment_ref:
        payload["deployment_ref"] = deployment_ref

    url = f"{server_url.rstrip('/')}/api/client/self/update/"
    resp = requests.patch(
        url,
        headers=build_headers(api_token),
        json=payload,
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, "Failed to update client")
    return resp.json()


def rotate_token(
    server_url: str | None = None,
    api_token: str | None = None,
    ca_cert: str | None = None,
) -> str:
    server_url, api_token, ca_cert = resolve_server_config(
        server_url, api_token, ca_cert
    )
    new_token = secrets.token_hex(32)
    url = f"{server_url.rstrip('/')}/api/client/self/rotate-token/"
    resp = requests.post(
        url,
        headers=build_headers(api_token),
        json={"new_token": new_token},
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, "Failed to rotate token")
    return new_token


def register_client(
    name: str,
    deployment_ref: str | None = None,
    server_url: str | None = None,
    ca_cert: str | None = None,
) -> dict:
    server_url, _token, ca_cert = resolve_server_config(
        server_url,
        ignore_missing=[RESERVED_KEY_NAMES["API_TOKEN"]],
    )
    venv_path = in_venv()
    if not venv_path:
        raise RuntimeError("Cannot detect virtual environment.")
    if not deployment_ref:
        deployment_ref = determine_deployment_ref()

    payload = {
        "name": name,
        "deployment_ref": deployment_ref,
        "venv_name": venv_path.name,
        "venv_path": str(venv_path.resolve()),
    }
    resp = requests.post(
        f"{server_url.rstrip('/')}/api/register/",
        headers=build_headers(),
        json=payload,
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, "Registration failed")
    return resp.json()


def download_ca_cert(
    server_url: str | None = None,
    dest_dir: Path | None = None,
) -> Path:
    server_url, _token, current_ca_cert = resolve_server_config(
        server_url,
        ignore_missing=[
            RESERVED_KEY_NAMES["API_TOKEN"],
            RESERVED_KEY_NAMES["CA_CERT"],
        ],
    )
    if current_ca_cert and Path(current_ca_cert).exists():
        raise FileExistsError(
            f"CA cert already exists at {current_ca_cert}. "
            f"Remove or update {RESERVED_KEY_NAMES['CA_CERT']} in {ENV_FILE_NAME} first."
        )

    url = f"{server_url.rstrip('/')}/api/server/ca-cert/"
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    resp = requests.get(url, headers=build_headers(), verify=False)
    _raise_for_status(resp, "Failed to download CA certificate")

    filename = "ca-cert.pem"
    cd = resp.headers.get("Content-Disposition", "")
    if cd:
        m = re.search(r'filename="?([^"]+)"?', cd)
        if m:
            filename = m.group(1)

    save_dir = dest_dir or (find_project_root() / ".conf")
    save_dir.mkdir(exist_ok=True)
    cert_path = save_dir / filename
    cert_path.write_bytes(resp.content)

    set_env_variable(RESERVED_KEY_NAMES["CA_CERT"], str(cert_path), verbose=False)
    return cert_path
