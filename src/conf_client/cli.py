"""
conf_client.cli
~~~~~~~~~~~~~~~
Command-line interface for the Ophix configuration client.

Entry point: conf-client (registered in pyproject.toml).
"""

import sys
from pathlib import Path
from typing import List, Tuple

import requests
from dotenv import dotenv_values

from client_core.commands import build_commands
from client_core.parser import make_main

from conf_client._config import CLIENT_CONFIG
from conf_client.core import (
    ENV_FILE_NAME,
    RESERVED_ENV_VARS,
    resolve_server_config,
    set_env_variable,
    fetch_config,
    create_config,
    update_config,
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _table(rows):
    # type: (List[List[str]]) -> str
    if not rows:
        return ""
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(str(col).ljust(widths[i]) for i, col in enumerate(row))
        for row in rows
    )


# ---------------------------------------------------------------------------
# Domain command handlers
# ---------------------------------------------------------------------------

def cmd_fetch(args):
    # type: (object) -> None
    name = args.name
    if args.var:
        _, _, _, dotenv_path = resolve_server_config(return_env_path=True)
        name = dotenv_values(dotenv_path).get(args.var)
        if not name:
            print("Error: {} is not set in {}".format(args.var, ENV_FILE_NAME))
            sys.exit(1)
    try:
        content, fmt, updated = fetch_config(name)
    except requests.HTTPError as exc:
        print("Failed to fetch '{}': {}".format(name, exc))
        if exc.response is not None:
            print(exc.response.text)
        sys.exit(1)
    except Exception as exc:
        print("Unexpected error: {}".format(exc))
        sys.exit(1)

    output_file = getattr(args, "output_file", None)

    if output_file and output_file != "-":
        path = Path(output_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            print("Error: could not write to {}: {}".format(path, exc.strerror))
            sys.exit(1)
        if args.format_info:
            print("Format: {}  Updated: {}".format(fmt, updated))
        print("Saved to {}".format(path))
    else:
        if args.format_info:
            print("# Format: {}  Updated: {}".format(fmt, updated))
        print(content)


def cmd_import(args):
    # type: (object) -> None
    _, token, ca_cert, dotenv_path = resolve_server_config(return_env_path=True)

    name = args.name
    if args.name and args.var:
        env_vars = dotenv_values(dotenv_path)
        existing = env_vars.get(args.var)
        if existing is not None and existing != args.name:
            print(
                "Error: {} is already mapped to '{}' in {}. "
                "Use --name {} to match, or edit {} manually.".format(
                    args.var, existing, ENV_FILE_NAME, existing, ENV_FILE_NAME
                )
            )
            sys.exit(1)
        if existing is None:
            set_env_variable(args.var, args.name)
            print("Mapped {}={} in {}".format(args.var, args.name, ENV_FILE_NAME))
    elif args.var:
        env_vars = dotenv_values(dotenv_path)
        name = env_vars.get(args.var)

    if not name:
        print("Configuration name not specified (use --name or --var)")
        sys.exit(1)

    fmt = args.format
    if not fmt and args.input_file:
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
        print("Format inferred from file extension: {}".format(fmt))

    if not fmt:
        print("--format is required when format cannot be inferred from file extension")
        sys.exit(1)

    try:
        if args.input_file == "-":
            content = sys.stdin.read()
        else:
            content = Path(args.input_file).read_text(encoding="utf-8")
    except Exception as exc:
        print("Failed to read input file: {}".format(exc))
        sys.exit(1)

    try:
        if args.overwrite:
            update_config(name, fmt, content, description=args.description)
            print("Configuration '{}' updated successfully".format(name))
        else:
            create_config(name, fmt, content, description=args.description)
            print("Configuration '{}' created successfully".format(name))
    except requests.HTTPError as exc:
        print("Error: {}".format(exc))
        if exc.response is not None:
            print(exc.response.text)
        sys.exit(1)


def _check_one(config_name):
    # type: (str) -> Tuple[bool, str]
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


def cmd_check(args):
    # type: (object) -> None
    if args.all:
        _, _, _, dotenv_path = resolve_server_config(return_env_path=True)
        env_vars = dotenv_values(dotenv_path)
        keys = sorted(k for k in env_vars if k not in RESERVED_ENV_VARS)
        if not keys:
            print("No configuration variables found in {}".format(dotenv_path))
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
            print("Key '{}' not found in {}".format(args.var, dotenv_path))
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


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

COMMANDS = build_commands(CLIENT_CONFIG)

COMMANDS["fetch"] = {
    "help": "Fetch a named configuration and print or save content",
    "mutually_exclusive_groups": [
        {
            "required": True,
            "arguments": [
                {"name": "--name", "metavar": "NAME", "help": "Configuration name"},
                {"name": "--var", "metavar": "ENV_VAR",
                 "help": "Env var in .conf.env holding the configuration name"},
            ],
        }
    ],
    "arguments": [
        {
            "name": "--output-file",
            "dest": "output_file",
            "metavar": "PATH",
            "help": "Write content to this file instead of stdout (use - for explicit stdout)",
            "required": False,
        },
        {
            "name": "--format-info",
            "action": "store_true",
            "help": "Print format and updated timestamp",
        },
    ],
    "handler": cmd_fetch,
}

COMMANDS["import"] = {
    "help": "Create or update a configuration from a file",
    "arguments": [
        {"name": "--name", "metavar": "NAME", "help": "Configuration name"},
        {"name": "--var", "metavar": "ENV_VAR",
         "help": "Env var in .conf.env holding the configuration name"},
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
}

COMMANDS["check"] = {
    "help": "Verify configuration retrieval",
    "mutually_exclusive_groups": [
        {
            "required": True,
            "arguments": [
                {"name": "--all", "action": "store_true",
                 "help": "Check all configs in env file"},
                {"name": "--var", "metavar": "ENV_VAR",
                 "help": "Check config named by this env var"},
                {"name": "--name", "metavar": "NAME", "help": "Check config by name"},
            ],
        }
    ],
    "arguments": [
        {"name": "--verbose", "action": "store_true", "help": "Show error detail"},
    ],
    "handler": cmd_check,
}


main = make_main(CLIENT_CONFIG, COMMANDS)


if __name__ == "__main__":
    main()
