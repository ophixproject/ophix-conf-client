"""
conf_client.core.api
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
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from client_core.core import api_delete, api_get, api_patch, api_post, api_put, resolve_server_config, set_active_config
from conf_client._config import CLIENT_CONFIG
from .env import (
    RESERVED_KEY_NAMES,
    ENV_FILE_NAME,
    in_venv,
    determine_deployment_ref,
)
from .http import build_headers, extract_server_message


def _verify(ca_cert: Optional[str]):
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
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> Tuple[str, str, str]:
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

    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    resp = api_get(url, headers=build_headers(api_token), verify=_verify(ca_cert))

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
    description: Optional[str] = None,
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
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
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    payload: Dict[str, Any] = {
        "format_name": format,
        "content": content,
    }
    if description is not None:
        payload["description"] = description

    resp = api_post(
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
    description: Optional[str] = None,
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> dict:
    """
    Overwrite an existing configuration.

    Requires ``can_update`` on the ClientConfiguration join record.
    """
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    payload: Dict[str, Any] = {
        "format_name": format,
        "content": content,
    }
    if description is not None:
        payload["description"] = description

    resp = api_put(
        url,
        headers=build_headers(api_token),
        json=payload,
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, f"Failed to update configuration '{name}'")
    return resp.json()


def delete_config(
    name: str,
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> dict:
    """
    Delete a configuration.

    Requires ``can_delete`` on the join record **and**
    ``ENABLE_ARTIFACT_DELETE=true`` on the server.
    """
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    resp = api_delete(
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

        from conf_client import get_config

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
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> dict:
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )
    url = f"{server_url.rstrip('/')}/api/client/self/"
    resp = api_get(url, headers=build_headers(api_token), verify=_verify(ca_cert))
    _raise_for_status(resp, "Failed to fetch client info")
    return resp.json()


def update_client(
    deployment_ref: Optional[str] = None,
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> dict:
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )
    venv_path = in_venv()
    if not venv_path:
        raise RuntimeError("Cannot detect virtual environment.")

    payload: Dict[str, Any] = {
        "venv_name": venv_path.name,
        "venv_path": str(venv_path.resolve()),
    }
    if deployment_ref:
        payload["deployment_ref"] = deployment_ref

    url = f"{server_url.rstrip('/')}/api/client/self/update/"
    resp = api_patch(
        url,
        headers=build_headers(api_token),
        json=payload,
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, "Failed to update client")
    return resp.json()


def rotate_token(
    server_url: Optional[str] = None,
    api_token: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> str:
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )
    new_token = secrets.token_hex(32)
    url = f"{server_url.rstrip('/')}/api/client/self/rotate-token/"
    resp = api_post(
        url,
        headers=build_headers(api_token),
        json={"new_token": new_token},
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, "Failed to rotate token")
    return new_token


def register_client(
    name: str,
    deployment_ref: Optional[str] = None,
    server_url: Optional[str] = None,
    ca_cert: Optional[str] = None,
) -> dict:
    server_url, _token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url,
        ignore_missing_keys=[RESERVED_KEY_NAMES["API_TOKEN"]],
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
    resp = api_post(
        f"{server_url.rstrip('/')}/api/register/",
        headers=build_headers(),
        json=payload,
        verify=_verify(ca_cert),
    )
    _raise_for_status(resp, "Registration failed")
    return resp.json()


