# ophix-conf-client

Python client for [ophix-confs](https://github.com/ophixproject/ophix-confs) configuration servers.

Provides a CLI for operators and an importable library for automation scripts
and Tier 2 clients. Fetches named configuration snippets (YAML, JSON, XML, INI,
TOML, .env, raw) verbatim from the server.

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

# Check all configurations mapped in .conf.env
conf-client check --all

# Diagnose config and connectivity
conf-client doctor
```

---

## Configuration

Settings are stored in `.conf.env` (mode 600).

| Variable | Purpose |
| --- | --- |
| `CONFSERVER_URL` | Base URL of the configuration server |
| `CONFSERVER_API_TOKEN` | 64-char hex API token (set by `register`) |
| `CONFSERVER_CA_CERT` | Path to CA certificate (set by `download ca-cert`) |

Additional keys in `.conf.env` are treated as configuration name mappings used by
`check --all` — each key maps an environment variable name to a configuration name
on the server.

---

## CLI reference

```text
conf-client quickstart <server_url> <client_name> [--deployment-ref ...]
conf-client fetch <name> [--format-info]
conf-client register <name> [deployment_ref]
conf-client update [--deployment-ref ...]
conf-client set {server|ca-cert|token} <value>
conf-client download ca-cert
conf-client import --input-file <file> [--name <n>] [--env <VAR>] [--format <fmt>] [--overwrite]
conf-client check {--all|--var <VAR>|--name <name>} [--verbose]
conf-client info
conf-client rotate-token
conf-client doctor
```

### import

| Usage | What happens |
| --- | --- |
| `--name <n>` only | Imports configuration named `<n>`. No `.conf.env` changes. |
| `--env <VAR>` only | Reads the configuration name from `<VAR>` in `.conf.env`. Fails if not set. |
| `--name <n> --env <VAR>` | Imports `<n>` and writes `<VAR>=<n>` to `.conf.env`. Fails if `<VAR>` is already mapped to a different name. |

Add `--overwrite` to update an existing configuration.

---

## Python API — Tier 2 clients

```python
from conf_client.core import get_config

# Reads config name from the named env var, fetches from server,
# returns raw content string. Calls sys.exit(1) on failure.
nginx_conf = get_config("NGINX_CONFIG_NAME")

# Write directly to file
with open("/etc/nginx/conf.d/upstream.conf", "w") as f:
    f.write(nginx_conf)
```

Full CRUD:

```python
from conf_client.core import (
    fetch_config,    # returns (content, format_name, updated_at)
    create_config,
    update_config,
    delete_config,
)
```

`fetch_config` returns a `(content, format_name, updated_at)` tuple rather than a dict,
since the content is raw text. The format name and timestamp come from response headers.
`get_config` returns the raw content string directly.

---

## Server

This client connects to [ophix-confs](https://github.com/ophixproject/ophix-confs).
