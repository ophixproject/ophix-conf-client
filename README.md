# ophix-conf-client

Python client for **Ophix Configuration Servers** (`ophix-conf`).

Provides a CLI for operators and a library API for automation scripts
and tier-2 clients.

---

## Installation

```bash
pip install ophix-conf-client
```

---

## Quick start

```bash
# Bootstrap in one step
conf-client quickstart https://confserver.internal my-client

# Fetch a configuration (raw content printed to stdout)
conf-client fetch nginx_upstream

# Fetch with format info header
conf-client fetch nginx_upstream --format-info

# Import a configuration file
conf-client import --input-file nginx.conf --name nginx_upstream --format raw

# Import with format inferred from extension
conf-client import --input-file app_config.yaml --name app_config

# Check all configurations in .conf.env
conf-client check --all

# Diagnose config and connectivity
conf-client doctor
```

---

## Configuration

Settings are stored in `.conf.env` in your project root (mode 600).

| Variable | Purpose |
|---|---|
| `CONFSERVER_URL` | Base URL of the configuration server |
| `CONFSERVER_API_TOKEN` | 64-char hex API token (set by `register`) |
| `CONFSERVER_CA_CERT` | Path to CA certificate (set by `download ca-cert`) |

Additional keys in `.conf.env` are treated as configuration name mappings
used by `check --all`.

---

## CLI reference

```
conf-client quickstart <server_url> <client_name> [--deployment-ref ...]
conf-client fetch <n> [--format-info]
conf-client register <n> [deployment_ref]
conf-client update [--deployment-ref ...]
conf-client set {server|ca-cert|token} <value>
conf-client download ca-cert
conf-client import --input-file <file> [--name <n>|--env <VAR>] [--format <fmt>] [--overwrite]
conf-client check {--all|--var <VAR>|--name <n>} [--verbose]
conf-client info
conf-client rotate-token
conf-client doctor
```

---

## Python API — tier-2 clients

```python
from ophix_conf_client import get_config

# Reads config name from env var, fetches from server,
# returns raw content string.  Calls sys.exit(1) on failure.
nginx_conf = get_config("NGINX_CONFIG_NAME")

# Write directly to file
with open("/etc/nginx/conf.d/upstream.conf", "w") as f:
    f.write(nginx_conf)
```

Full CRUD:

```python
from ophix_conf_client import (
    fetch_config,    # returns (content, format_name, updated_at)
    create_config,
    update_config,
    delete_config,
)
```

---

## Key difference from ophix-cred-client

`fetch_config` returns a `(content, format_name, updated_at)` tuple
rather than a dict, since the content is raw text rather than JSON.
The format name and timestamp come from response headers.

`get_config` returns the raw content string directly (not a dict).
