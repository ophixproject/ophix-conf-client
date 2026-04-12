"""
conf_client.cli
~~~~~~~~~~~~~~~~~~~~~
Command-line interface for the Ophix configuration client.

Commands
--------
quickstart    Bootstrap: set server, download CA cert, register
fetch         Fetch a configuration by name and print content
register      Register this client with the server
update        Update venv/deployment info on the server
set           Set CONFSERVER_URL / CONFSERVER_CA_CERT / CONFSERVER_API_TOKEN
download      Download the server CA certificate
import        Create or update a configuration from a file
check         Verify configuration retrieval (all / by env var / by name)
info          Show this client's record from the server
rotate-token  Rotate API token
doctor        Diagnose local config and server connectivity
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple
import argparse

import requests
from dotenv import dotenv_values

from conf_client._version import __version__
from conf_client.core import (
    ENV_FILE_NAME,
    RESERVED_KEY_NAMES,
    RESERVED_ENV_VARS,
    resolve_server_config,
    set_env_variable,
    in_venv,
    find_project_root,
    build_headers,
    fetch_config,
    create_config,
    update_config,
    register_client as _register_client,
    update_client as _update_client,
    rotate_token as _rotate_token,
    fetch_client_info,
    download_ca_cert as _download_ca_cert,
)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _table(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(str(col).ljust(widths[i]) for i, col in enumerate(row))
        for row in rows
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def cmd_quickstart(args) -> None:
    print("conf-client quickstart\n")

    print("→ Setting server URL...")
    set_env_variable(RESERVED_KEY_NAMES["SERVER"], args.server_url)

    print("→ Downloading CA certificate...")
    try:
        cert_path = _download_ca_cert(server_url=args.server_url)
        print(f"  CA certificate saved to: {cert_path}")
    except FileExistsError as exc:
        print(f"  ⚠ {exc}")

    print("→ Registering client...")
    _do_register(args.client_name, args.deployment_ref)

    print("\n✓ Quickstart completed successfully")


def cmd_fetch(args) -> None:
    try:
        content, fmt, updated = fetch_config(args.name)
        if args.format_info:
            print(f"# Format: {fmt}  Updated: {updated}")
        print(content)
    except requests.HTTPError as exc:
        print(f"Failed to fetch '{args.name}': {exc}")
        if exc.response is not None:
            print(exc.response.text)
        sys.exit(1)
    except Exception as exc:
        print(f"Unexpected error: {exc}")
        sys.exit(1)


def _do_register(name: str, deployment_ref: Optional[str]) -> None:
    _, token, _, dotenv_path = resolve_server_config(
        return_env_path=True,
        ignore_missing=[RESERVED_KEY_NAMES["API_TOKEN"]],
    )

    if token and len(token) == 64:
        print(
            f"Error: {RESERVED_KEY_NAMES['API_TOKEN']} already present in "
            f"{ENV_FILE_NAME}. Registration should only happen once."
        )
        print(f"  Env file: {dotenv_path}")
        sys.exit(1)

    try:
        data = _register_client(name=name, deployment_ref=deployment_ref)
    except requests.HTTPError as exc:
        print(f"\nFAILED TO REGISTER CLIENT\n  {exc}")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"\nFAILED TO REGISTER CLIENT — network error\n  {exc}")
        sys.exit(1)

    print("Client registered successfully!")
    print(f"  Host:            {data['host']}")
    print(f"  Name:            {data['name']}")
    print(f"  Deployment ref:  {data['deployment_ref']}")
    print(f"  Venv:            {data['venv_name']} ({data['venv_path']})")

    set_env_variable(RESERVED_KEY_NAMES["API_TOKEN"], data["api_token"], verbose=False)
    print(f"  Token saved to {ENV_FILE_NAME}")


def cmd_register(args) -> None:
    _do_register(args.name, args.deployment_ref)


def cmd_update(args) -> None:
    if not in_venv():
        print("Error: Cannot detect virtual environment.")
        sys.exit(1)
    try:
        data = _update_client(deployment_ref=args.deployment_ref)
    except requests.HTTPError as exc:
        print(f"Failed to update client: {exc}")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"Network error: {exc}")
        sys.exit(1)

    print("Client updated successfully!")
    print(f"  Venv: {data.get('venv_name')} ({data.get('venv_path')})")
    if args.deployment_ref:
        print(f"  Deployment ref: {data.get('deployment_ref')}")


def cmd_set(args) -> None:
    var_map = {
        "server":  RESERVED_KEY_NAMES["SERVER"],
        "ca-cert": RESERVED_KEY_NAMES["CA_CERT"],
        "token":   RESERVED_KEY_NAMES["API_TOKEN"],
    }
    set_env_variable(var_map[args.variable], args.value)


def cmd_download(args) -> None:
    try:
        cert_path = _download_ca_cert()
        print(f"CA certificate saved to: {cert_path}")
        print(f"{ENV_FILE_NAME} updated with {RESERVED_KEY_NAMES['CA_CERT']}")
    except FileExistsError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"Failed to download CA certificate: {exc}")
        sys.exit(1)


def cmd_import(args) -> None:
    _, token, ca_cert, dotenv_path = resolve_server_config(return_env_path=True)

    name = args.name
    if args.env_key:
        env_vars = dotenv_values(dotenv_path)
        name = env_vars.get(args.env_key)

    if not name:
        print("Configuration name not specified (use --name or --env)")
        sys.exit(1)

    # Determine format
    fmt = args.format
    if not fmt and args.input_file:
        # Infer from file extension if not specified
        ext_map = {
            ".yaml": "yaml", ".yml": "yaml",
            ".json": "json",
            ".xml": "xml",
            ".ini": "ini", ".cfg": "ini",
            ".toml": "toml",
            ".env": "env",
        }
        suffix = Path(args.input_file).suffix.lower()
        fmt = ext_map.get(suffix, "raw")
        print(f"Format inferred from file extension: {fmt}")

    if not fmt:
        print("--format is required when format cannot be inferred from file extension")
        sys.exit(1)

    try:
        if args.input_file == "-":
            content = sys.stdin.read()
        else:
            content = Path(args.input_file).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Failed to read input file: {exc}")
        sys.exit(1)

    try:
        if args.overwrite:
            update_config(name, fmt, content, description=args.description)
            print(f"Configuration '{name}' updated successfully")
        else:
            create_config(name, fmt, content, description=args.description)
            print(f"Configuration '{name}' created successfully")
    except requests.HTTPError as exc:
        print(f"Error: {exc}")
        if exc.response is not None:
            print(exc.response.text)
        sys.exit(1)


def _check_one(config_name: str) -> Tuple[bool, str]:
    try:
        fetch_config(config_name)
        return True, "OK"
    except requests.HTTPError as exc:
        try:
            body = exc.response.json()
            msg = body.get("detail") or body.get("error") or str(body)
        except Exception:
            msg = exc.response.text.strip() if exc.response else str(exc)
        return False, msg
    except Exception as exc:
        return False, str(exc)


def cmd_check(args) -> None:
    if args.all:
        _, _, _, dotenv_path = resolve_server_config(return_env_path=True)
        env_vars = dotenv_values(dotenv_path)
        keys = sorted(k for k in env_vars if k not in RESERVED_ENV_VARS)
        if not keys:
            print(f"No configuration variables found in {dotenv_path}")
            sys.exit(1)

        header = ["ENV KEY", "CONFIG NAME", "RESULT"]
        if args.verbose:
            header.append("DETAIL")
        rows = [header]
        for key in keys:
            config_name = env_vars[key]
            ok, msg = _check_one(config_name)
            row = [key, config_name, "OK" if ok else "ERROR"]
            if args.verbose:
                row.append("" if ok else msg)
            rows.append(row)
        print(_table(rows))

    elif args.var:
        _, _, _, dotenv_path = resolve_server_config(return_env_path=True)
        env_vars = dotenv_values(dotenv_path)
        if args.var not in env_vars:
            print(f"Key '{args.var}' not found in {dotenv_path}")
            sys.exit(1)
        ok, msg = _check_one(env_vars[args.var])
        print("OK" if ok else (msg if args.verbose else "ERROR"))
        if not ok:
            sys.exit(1)

    else:
        ok, msg = _check_one(args.name)
        print("OK" if ok else (msg if args.verbose else "ERROR"))
        if not ok:
            sys.exit(1)


def cmd_info(args) -> None:
    try:
        data = fetch_client_info()
    except requests.HTTPError as exc:
        print(f"Failed to fetch client info: {exc}")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"Network error: {exc}")
        sys.exit(1)

    print(f"Name:                {data.get('name')}")
    print(f"Client version:      {__version__}")
    print(f"Deployment ref:      {data.get('deployment_ref')}")
    print(f"Venv:                {data.get('venv_name')} ({data.get('venv_path')})")
    print(f"Last token rotation: {data.get('last_token_rotation')}")


def cmd_rotate_token(args) -> None:
    _, _, _, dotenv_path = resolve_server_config(return_env_path=True)
    try:
        new_token = _rotate_token()
    except requests.HTTPError as exc:
        print(f"Failed to rotate token: {exc}")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"Network error: {exc}")
        sys.exit(1)

    set_env_variable(RESERVED_KEY_NAMES["API_TOKEN"], new_token, verbose=False)
    print(f"API token rotated successfully")
    print(f"  {ENV_FILE_NAME} updated at {dotenv_path}")


def cmd_doctor(args) -> None:
    print("conf-client doctor\n")

    server_url, api_token, ca_cert, dotenv_path = resolve_server_config(
        return_env_path=True,
        ignore_missing=[
            RESERVED_KEY_NAMES["SERVER"],
            RESERVED_KEY_NAMES["API_TOKEN"],
        ],
    )

    if dotenv_path:
        print(f"✓ Env file:    {dotenv_path}")
        try:
            mode = Path(dotenv_path).stat().st_mode & 0o777
            if mode == 0o600:
                print("✓ Permissions: 600 (secure)")
            else:
                print(f"⚠ Permissions: {oct(mode)} — recommended 0o600")
        except Exception as exc:
            print(f"⚠ Could not check permissions: {exc}")
    else:
        print(f"✗ No {ENV_FILE_NAME} found")
        return

    if server_url:
        print(f"✓ {RESERVED_KEY_NAMES['SERVER']} = {server_url}")
    else:
        print(f"✗ {RESERVED_KEY_NAMES['SERVER']} not set")
        return

    if api_token and len(api_token) == 64:
        print(f"✓ {RESERVED_KEY_NAMES['API_TOKEN']} present (64 chars)")
    else:
        print(f"✗ {RESERVED_KEY_NAMES['API_TOKEN']} missing or invalid")
        return

    if ca_cert:
        if Path(ca_cert).exists():
            print(f"✓ {RESERVED_KEY_NAMES['CA_CERT']} = {ca_cert}")
        else:
            print(f"✗ {RESERVED_KEY_NAMES['CA_CERT']} set but file missing: {ca_cert}")
            return
    else:
        print(f"⚠ {RESERVED_KEY_NAMES['CA_CERT']} not set (using system trust store)")

    import platform
    print(f"\n  Client version: {__version__}")
    print(f"  Python version: {sys.version.split()[0]}")
    print(f"  OS:             {platform.platform()}")

    venv_path = in_venv()
    if venv_path:
        print(f"✓ Virtualenv:   {venv_path.name} ({venv_path})")
    else:
        print("⚠ Not running inside a virtualenv")

    print("\nChecking server connectivity...")
    try:
        data = fetch_client_info(
            server_url=server_url, api_token=api_token, ca_cert=ca_cert
        )
    except requests.exceptions.SSLError as exc:
        print(f"✗ TLS error: {exc}")
        return
    except requests.exceptions.ConnectionError as exc:
        print(f"✗ Cannot connect to server: {exc}")
        return
    except requests.HTTPError as exc:
        print(f"✗ Server error: {exc}")
        return

    print("✓ Authenticated successfully")
    print(f"\n  Client identity:")
    print(f"    Name:            {data.get('name')}")
    print(f"    Deployment ref:  {data.get('deployment_ref')}")
    print(f"    Venv name:       {data.get('venv_name')}")
    print(f"    Venv path:       {data.get('venv_path')}")
    print(f"    Last rotation:   {data.get('last_token_rotation')}")
    print("\n✓ Doctor checks completed successfully")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser(
    *,
    prog: str,
    version: str,
    commands: Mapping[str, dict],
    description: Optional[str] = None,
) -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument("-v", "--version", action="version", version=version)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, spec in commands.items():
        help_text = spec.get("help") if not spec.get("hidden") else None
        sub = subparsers.add_parser(
            name,
            help=help_text if help_text is not None else argparse.SUPPRESS,
        )
        for arg in spec.get("arguments", []):
            arg = arg.copy()
            sub.add_argument(arg.pop("name"), **arg)
        for group_spec in spec.get("mutually_exclusive_groups", []):
            grp = sub.add_mutually_exclusive_group(
                required=group_spec.get("required", False)
            )
            for arg in group_spec["arguments"]:
                arg = arg.copy()
                grp.add_argument(arg.pop("name"), **arg)
        sub.set_defaults(func=spec["handler"])

    return parser


COMMANDS: Dict[str, dict] = {
    "quickstart": {
        "help": "Bootstrap a new client (set server, download CA cert, register)",
        "arguments": [
            {"name": "server_url", "help": "Configuration server base URL"},
            {"name": "client_name", "help": "Client name to register"},
            {
                "name": "--deployment-ref",
                "dest": "deployment_ref",
                "help": "Deployment reference (optional; defaults to venv parent dir)",
                "required": False,
            },
        ],
        "handler": cmd_quickstart,
    },

    "fetch": {
        "help": "Fetch a named configuration and print content",
        "arguments": [
            {"name": "name", "help": "Configuration name"},
            {
                "name": "--format-info",
                "action": "store_true",
                "help": "Print format and updated timestamp as a comment before content",
            },
        ],
        "handler": cmd_fetch,
    },

    "register": {
        "help": "Register this client with the server",
        "arguments": [
            {"name": "name", "help": "Client name"},
            {
                "name": "deployment_ref",
                "nargs": "?",
                "help": "Deployment reference (optional; defaults to venv parent dir)",
            },
        ],
        "handler": cmd_register,
    },

    "update": {
        "help": "Update venv/deployment info on the server",
        "arguments": [
            {
                "name": "--deployment-ref",
                "dest": "deployment_ref",
                "help": "New deployment reference (optional)",
            },
        ],
        "handler": cmd_update,
    },

    "set": {
        "help": f"Set a config variable in {ENV_FILE_NAME}",
        "arguments": [
            {
                "name": "variable",
                "choices": ["server", "ca-cert", "token"],
                "help": "Which variable to set",
            },
            {"name": "value", "help": "Value to store"},
        ],
        "handler": cmd_set,
    },

    "download": {
        "help": "Download the server CA certificate",
        "arguments": [
            {
                "name": "resource",
                "choices": ["ca-cert"],
                "help": "Resource to download",
            },
        ],
        "handler": cmd_download,
    },

    "import": {
        "help": "Create or update a configuration from a file",
        "arguments": [
            {"name": "--name", "help": "Configuration name"},
            {"name": "--env", "dest": "env_key", "help": "Env var holding configuration name"},
            {
                "name": "--input-file",
                "required": True,
                "help": "File containing configuration content (use - for stdin)",
            },
            {
                "name": "--format",
                "help": "Format name (yaml/json/xml/ini/toml/env/raw). "
                        "Inferred from file extension if not specified.",
            },
            {"name": "--description", "help": "Optional description"},
            {"name": "--overwrite", "action": "store_true", "help": "Update if already exists"},
        ],
        "handler": cmd_import,
    },

    "check": {
        "help": "Verify configuration retrieval",
        "mutually_exclusive_groups": [
            {
                "required": True,
                "arguments": [
                    {"name": "--all", "action": "store_true", "help": "Check all configs in env file"},
                    {"name": "--var", "metavar": "ENV_VAR", "help": "Check config named by this env var"},
                    {"name": "--name", "metavar": "CONFIG_NAME", "help": "Check config by name"},
                ],
            }
        ],
        "arguments": [
            {"name": "--verbose", "action": "store_true", "help": "Show error detail"},
        ],
        "handler": cmd_check,
    },

    "info": {
        "help": "Show this client's record from the server",
        "arguments": [],
        "handler": cmd_info,
    },

    "rotate-token": {
        "help": "Rotate API token (new token generated and saved automatically)",
        "arguments": [],
        "handler": cmd_rotate_token,
    },

    "doctor": {
        "help": "Diagnose local config and server connectivity",
        "arguments": [],
        "handler": cmd_doctor,
    },
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser(
        prog="conf-client",
        version=__version__,
        description="Ophix configuration client",
        commands=COMMANDS,
    )
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
