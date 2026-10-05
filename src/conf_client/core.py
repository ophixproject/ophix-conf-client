"""
conf_client.core
~~~~~~~~~~~~~~~~
Core library for the Ophix configuration client.

Provides functions for fetching, creating, updating, and deleting
configurations from an Ophix configuration server. Import from here
in Tier 2 clients:

    from conf_client import get_config
"""

import os
import sys
from typing import Any, Dict, Optional, Tuple

import requests
from dotenv import set_key

from client_core.core import (
    api_delete,
    api_get,
    api_post,
    api_put,
    build_client_headers,
    ensure_env_file,
    resolve_server_config,
    set_active_config,
)
from conf_client._config import CLIENT_CONFIG

ENV_FILE_NAME = ".conf.env"

RESERVED_KEY_NAMES = {
    "SERVER":    "CONFSERVER_URL",
    "API_TOKEN": "CONFSERVER_API_TOKEN",
    "CA_CERT":   "CONFSERVER_CA_CERT",
}

RESERVED_ENV_VARS = set(RESERVED_KEY_NAMES.values())


def set_env_variable(var, value, verbose=True):
    # type: (str, str, bool) -> None
    """Write var=value into .conf.env, creating the file if needed."""
    env_file = ensure_env_file(CLIENT_CONFIG)
    set_key(str(env_file), var, value)
    if verbose:
        print("Set {} in {}".format(var, ENV_FILE_NAME))


def fetch_config(
    name,             # type: str
    server_url=None,  # type: Optional[str]
    api_token=None,   # type: Optional[str]
    ca_cert=None,     # type: Optional[str]
):
    # type: (...) -> Tuple[str, str, str]
    """
    Fetch a named configuration from the server.

    Returns a tuple of (content, format_name, updated_at). The content is
    the raw configuration string exactly as stored on the server. The
    format_name (e.g. 'yaml', 'json') and updated_at timestamp are read
    from the response headers.

    Raises ValueError for an empty name, requests.HTTPError on failure.
    """
    if not name or str(name).strip() == "":
        raise ValueError("Configuration name must not be empty")

    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)

    response = api_get(url, headers=headers, verify=ca_cert or True)

    if response.status_code == 404:
        raise requests.HTTPError(f"Configuration '{name}' not found.", response=response)

    response.raise_for_status()

    content = response.text
    format_name = response.headers.get("X-Ophix-Config-Format", "")
    updated_at = response.headers.get("X-Ophix-Config-Updated", "")
    return content, format_name, updated_at


def create_config(
    name,              # type: str
    format,            # type: str
    content,           # type: str
    description=None,  # type: Optional[str]
    server_url=None,   # type: Optional[str]
    api_token=None,    # type: Optional[str]
    ca_cert=None,      # type: Optional[str]
):
    # type: (...) -> dict
    """
    Create a new configuration on the server.

    Returns the server response dict. Raises requests.HTTPError on failure.
    """
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)

    payload = {"format_name": format, "content": content}
    if description is not None:
        payload["description"] = description

    try:
        resp = api_post(url, headers=headers, json=payload, verify=ca_cert or True)
        resp.raise_for_status()
    except requests.HTTPError as e:
        try:
            err_json = resp.json()
            server_msg = err_json.get("detail") or err_json.get("error") or str(err_json)
        except Exception:
            server_msg = resp.text.strip() or str(e)
        raise requests.HTTPError(
            f"Failed to create configuration '{name}': {server_msg}",
            response=resp,
        ) from e

    return resp.json()


def update_config(
    name,              # type: str
    format,            # type: str
    content,           # type: str
    description=None,  # type: Optional[str]
    server_url=None,   # type: Optional[str]
    api_token=None,    # type: Optional[str]
    ca_cert=None,      # type: Optional[str]
):
    # type: (...) -> dict
    """
    Overwrite an existing configuration.

    Requires `can_update` on the ClientConfiguration join record.
    Returns the updated configuration dict. Raises requests.HTTPError on failure.
    """
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )

    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)

    payload = {"format_name": format, "content": content}
    if description is not None:
        payload["description"] = description

    try:
        resp = api_put(url, headers=headers, json=payload, verify=ca_cert or True)
        resp.raise_for_status()
    except requests.HTTPError as e:
        try:
            err_json = resp.json()
            server_msg = err_json.get("detail") or err_json.get("error") or str(err_json)
        except Exception:
            server_msg = resp.text.strip() or str(e)
        raise requests.HTTPError(
            f"Failed to update configuration '{name}': {server_msg}",
            response=resp,
        ) from e

    return resp.json()


def delete_config(
    name,             # type: str
    server_url=None,  # type: Optional[str]
    api_token=None,   # type: Optional[str]
    ca_cert=None,     # type: Optional[str]
):
    # type: (...) -> dict
    """
    Delete a configuration.

    Requires `can_delete` on the join record and `ENABLE_ARTIFACT_DELETE=true`
    on the server. Returns the server response dict. Raises requests.HTTPError
    on failure.
    """
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(
        CLIENT_CONFIG, server_url, api_token, ca_cert
    )
    url = f"{server_url.rstrip('/')}/api/configs/{name}/"
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)

    try:
        resp = api_delete(url, headers=headers, verify=ca_cert or True)
        resp.raise_for_status()
    except requests.HTTPError as e:
        try:
            err_json = resp.json()
            server_msg = err_json.get("detail") or err_json.get("error") or str(err_json)
        except Exception:
            server_msg = resp.text.strip() or str(e)
        raise requests.HTTPError(
            f"Failed to delete configuration '{name}': {server_msg}",
            response=resp,
        ) from e

    return resp.json()


def get_config(env_var_name):
    # type: (str) -> str
    """
    Tier 2 entry point — retrieve a configuration's raw content using an
    environment variable.

    Looks up the configuration name from the named env var, then fetches
    and returns its raw content string.

    Example::

        from conf_client import get_config
        nginx_conf = get_config("NGINX_CONFIG_NAME")

    Exits via sys.exit(1) on any failure so Tier 2 callers don't need to
    handle exceptions.
    """
    set_active_config(CLIENT_CONFIG)
    resolve_server_config(
        CLIENT_CONFIG,
        ignore_missing_keys=[
            CLIENT_CONFIG.server_url_key,
            CLIENT_CONFIG.api_token_key,
            CLIENT_CONFIG.ca_cert_key,
        ],
    )

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
