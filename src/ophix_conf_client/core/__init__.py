"""
ophix_conf_client.core
~~~~~~~~~~~~~~~~~~~~~~
Public API surface of the core subpackage.
"""

from .env import (
    ENV_FILE_NAME,
    RESERVED_KEY_NAMES,
    RESERVED_ENV_VARS,
    resolve_server_config,
    in_venv,
    ensure_env_file,
    set_env_variable,
    find_project_root,
    determine_deployment_ref,
)

from .http import build_headers

from .api import (
    fetch_config,
    create_config,
    update_config,
    delete_config,
    get_config,
    fetch_client_info,
    update_client,
    rotate_token,
    register_client,
    download_ca_cert,
)

__all__ = [
    "ENV_FILE_NAME", "RESERVED_KEY_NAMES", "RESERVED_ENV_VARS",
    "resolve_server_config", "in_venv", "ensure_env_file",
    "set_env_variable", "find_project_root", "determine_deployment_ref",
    "build_headers",
    "fetch_config", "create_config", "update_config",
    "delete_config", "get_config", "fetch_client_info",
    "update_client", "rotate_token", "register_client", "download_ca_cert",
]
