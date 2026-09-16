"""Tests for freelance config CLI commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from freelance_cli.cli import main
from freelance_cli.config_commands import validate_config
from packages.workspace.manager import WorkspaceManager


def test_config_show_human_readable(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "EFFECTIVE FREELANCE CONFIGURATION" in result.output
    assert "Workspace Root:" in result.output
    assert "Hourly Rate:" in result.output
    assert "Currency:" in result.output


def test_config_show_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(main, ["config", "show", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "config show"
    assert "currency" in payload
    assert "pricing" in payload


def test_config_validate_valid(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(main, ["config", "validate"])
    assert result.exit_code == 0
    assert "Configuration is valid and consistent." in result.output


def test_config_validate_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(main, ["config", "validate", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "config validate"
    assert payload["valid"] is True
    assert payload["errors"] == []


def test_config_validate_invalid_hourly_rate() -> None:
    mgr = WorkspaceManager()
    mgr.config.pricing.hourly_rate = -10.0
    valid, errors = validate_config(mgr)
    assert valid is False
    assert any("Hourly rate must be positive" in e for e in errors)
