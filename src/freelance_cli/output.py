"""Unified CLI contract and structured output formatting."""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from packages.security.secrets import mask_text
from packages.storage_utils import CURRENT_STATE_SCHEMA_VERSION

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 3


def format_json_envelope(
    data: Any,
    command: str = "",
    status: str = "success",
    exit_code: int = EXIT_SUCCESS,
    errors: list[str] | None = None,
    schema_version: str = CURRENT_STATE_SCHEMA_VERSION,
) -> str:
    """Format structured CLI output conforming to the global JSON contract."""
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "command": command,
        "status": status,
        "exit_code": exit_code,
        "data": data,
        "errors": errors or [],
    }
    if isinstance(data, dict):
        for k, v in data.items():
            if k not in payload:
                payload[k] = v
    dumped = json.dumps(payload, indent=2, ensure_ascii=False)
    return mask_text(dumped)


def emit_json(
    data: Any,
    command: str = "",
    status: str = "success",
    exit_code: int = EXIT_SUCCESS,
    errors: list[str] | None = None,
) -> None:
    """Print structured JSON envelope to stdout."""
    envelope = format_json_envelope(
        data=data,
        command=command,
        status=status,
        exit_code=exit_code,
        errors=errors,
    )
    click.echo(envelope)


def exit_with_error(
    message: str,
    command: str = "",
    json_mode: bool = False,
    exit_code: int = EXIT_ERROR,
    errors: list[str] | None = None,
) -> None:
    """Handle expected failure gracefully without uncaught stack traces."""
    all_errors = [message]
    if errors:
        all_errors.extend(errors)

    if json_mode:
        emit_json(
            data=None,
            command=command,
            status="error",
            exit_code=exit_code,
            errors=all_errors,
        )
    else:
        click.secho(f"✗ {message}", fg="red", err=True)
    sys.exit(exit_code)
