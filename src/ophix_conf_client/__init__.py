"""
ophix_conf_client
~~~~~~~~~~~~~~~~~
Ophix configuration client.

Tier-2 clients typically only need::

    from ophix_conf_client import get_config, fetch_config, \
        create_config, delete_config
"""

from ophix_conf_client.core import (
    get_config,
    fetch_config,
    create_config,
    update_config,
    delete_config,
)

__all__ = [
    "get_config",
    "fetch_config",
    "create_config",
    "update_config",
    "delete_config",
]
