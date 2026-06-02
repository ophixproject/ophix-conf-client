"""
conf_client.core
~~~~~~~~~~~~~~~~
Core library for the Ophix configuration client.

Provides functions for fetching and managing configurations from an Ophix
configuration server. Import from here in Tier 2 clients:

    from conf_client.core import get_conf, fetch_config
"""

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import requests
from dotenv import find_dotenv, load_dotenv, set_key

from client_core.core import api_delete, api_get, api_post, api_put, build_client_headers, set_active_config
from conf_client._config import CLIENT_CONFIG

ENV_FILE_NAME = ".conf.env"

RESERVED_ENV_VARS = {
    "CONFSERVER_URL",
    "CONFSERVER_CA_CERT",
    "CONFSERVER_API_TOKEN",
}


def _find_project_root():
    # type: () -> Path
    cwd = Path.cwd()
    if hasattr(sys, "real_prefix") or sys.prefix != sys.base_prefix:
        return Path(sys.prefix).parent
    for parent in [cwd] + list(cwd.parents):
        if (parent / "requirements.txt").exists() or (parent / ".git").exists() or (parent / ".env").exists():
            return parent
    return cwd


def resolve_server_config(
    server_url=None,       # type: Optional[str]
    api_token=None,        # type: Optional[str]
    ca_cert=None,          # type: Optional[str]
    exit_on_error=True,    # type: bool
    return_env_path=False, # type: bool
):
    # type: (...) -> tuple
    """Resolve server config from arguments, .conf.env, or environment."""
    env_path_found = None
    project_root = _find_project_root()
    candidate = project_root / ENV_FILE_NAME
    if candidate.exists():
        load_dotenv(str(candidate))
        env_path_found = str(candidate)
    else:
        found = find_dotenv(filename=ENV_FILE_NAME, usecwd=True)
        if found:
            load_dotenv(found)
            env_path_found = found

    server_url = server_url or os.getenv("CONFSERVER_URL")
    api_token = api_token or os.getenv("CONFSERVER_API_TOKEN")
    ca_cert = ca_cert or os.getenv("CONFSERVER_CA_CERT")

    errors = []
    if not server_url:
        errors.append("Server URL not set (CONFSERVER_URL)")
    if not api_token or len(api_token) != 64:
        errors.append("API token missing or invalid (CONFSERVER_API_TOKEN — must be 64 hex chars)")
    if ca_cert:
        ca_path = Path(ca_cert)
        if not ca_path.exists():
            errors.append("CA cert file not found at {}".format(ca_cert))
        else:
            ca_cert = str(ca_path.resolve())

    if errors:
        if exit_on_error:
            print("Error resolving server config:\n{}".format("\n".join(errors)))
            sys.exit(1)
        else:
            raise ValueError("\n".join(errors))

    if return_env_path:
        return server_url, api_token, ca_cert, env_path_found
    return server_url, api_token, ca_cert


def set_env_variable(key, value):
    # type: (str, str) -> None
    """Write a key=value mapping into .conf.env."""
    project_root = _find_project_root()
    env_path = project_root / ENV_FILE_NAME
    if not env_path.exists():
        env_path.touch(mode=0o600)
    set_key(str(env_path), key, value)


def fetch_config(
    name,            # type: str
    server_url=None, # type: Optional[str]
    api_token=None,  # type: Optional[str]
    ca_cert=None,    # type: Optional[str]
):
    # type: (...) -> Tuple[str, str, str]
    """
    Fetch a configuration from the server.

    Returns (content, format_name, updated_at).
    Raises requests.HTTPError on failure.
    """
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(server_url, api_token, ca_cert)
    url = "{}/api/configs/{}/".format(server_url.rstrip("/"), name)
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)
    resp = api_get(url, headers=headers, verify=ca_cert or True)
    resp.raise_for_status()
    fmt = resp.headers.get("X-Ophix-Config-Format", "")
    updated = resp.headers.get("X-Ophix-Config-Updated", "")
    return resp.text, fmt, updated


def create_config(
    name,             # type: str
    fmt,              # type: str
    content,          # type: str
    description=None, # type: Optional[str]
    server_url=None,  # type: Optional[str]
    api_token=None,   # type: Optional[str]
    ca_cert=None,     # type: Optional[str]
):
    # type: (...) -> None
    """Create a new configuration on the server. Raises requests.HTTPError on failure."""
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(server_url, api_token, ca_cert)
    url = "{}/api/configs/{}/".format(server_url.rstrip("/"), name)
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)
    payload = {"format": fmt, "content": content}
    if description:
        payload["description"] = description
    resp = api_post(url, headers=headers, json=payload, verify=ca_cert or True)
    resp.raise_for_status()


def update_config(
    name,             # type: str
    fmt,              # type: str
    content,          # type: str
    description=None, # type: Optional[str]
    server_url=None,  # type: Optional[str]
    api_token=None,   # type: Optional[str]
    ca_cert=None,     # type: Optional[str]
):
    # type: (...) -> None
    """Update an existing configuration on the server. Raises requests.HTTPError on failure."""
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(server_url, api_token, ca_cert)
    url = "{}/api/configs/{}/".format(server_url.rstrip("/"), name)
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)
    payload = {"format": fmt, "content": content}
    if description:
        payload["description"] = description
    resp = api_put(url, headers=headers, json=payload, verify=ca_cert or True)
    resp.raise_for_status()


def delete_config(
    name,            # type: str
    server_url=None, # type: Optional[str]
    api_token=None,  # type: Optional[str]
    ca_cert=None,    # type: Optional[str]
):
    # type: (...) -> None
    """Delete a configuration from the server. Raises requests.HTTPError on failure."""
    set_active_config(CLIENT_CONFIG)
    server_url, api_token, ca_cert = resolve_server_config(server_url, api_token, ca_cert)
    url = "{}/api/configs/{}/".format(server_url.rstrip("/"), name)
    headers = build_client_headers(CLIENT_CONFIG, api_token=api_token)
    resp = api_delete(url, headers=headers, verify=ca_cert or True)
    resp.raise_for_status()


def get_conf(env_var_name):
    # type: (str) -> str
    """
    Tier 2 entry point — retrieve configuration content using an environment variable.

    Looks up the configuration name from the named env var, fetches the content
    from the server, and returns it as a string.

    Example::

        from conf_client.core import get_conf
        nginx_conf = get_conf("MY_NGINX_CONFIG")
    """
    resolve_server_config()  # triggers .conf.env load

    conf_name = os.getenv(env_var_name)
    if not conf_name:
        print("Environment variable {} not set. Aborting.".format(env_var_name))
        sys.exit(1)

    try:
        content, _, _ = fetch_config(conf_name)
        return content
    except Exception as e:
        print("Failed to fetch configuration '{}' from configuration server: {}".format(conf_name, e))
        sys.exit(1)
