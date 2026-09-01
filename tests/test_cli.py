"""Test for CLI commands using Click's test runner."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from freelance_cli.cli import main
from freelance_cli.config import Config, save_config


@pytest.fixture
def cli_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    """CLI runner with a temporary workspace."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    config = Config(workspace_root=str(ws))
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    # Monkey-patch the config loading in cli.py
    import freelance_cli.cli as cli_module

    original_get_manager = cli_module._get_manager

    def patched_get_manager() -> cli_module.WorkspaceManager:
        return cli_module.WorkspaceManager(config_path=config_path)

    monkeypatch.setattr(cli_module, "_get_manager", patched_get_manager)
    return CliRunner()


class TestCLI:
    def test_version(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "freelance" in result.output.lower() or "job" in result.output.lower()

    def test_job_new(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(
            main,
            ["job", "new", "--client", "TestCo", "--description", "Fix bug",
             "--source", "Useme", "--budget", "500", "--deadline", "2026-09-15"],
        )
        assert result.exit_code == 0
        assert "JOB-001" in result.output
        assert "TestCo" in result.output

    def test_jobs_empty(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["jobs"])
        assert result.exit_code == 0
        assert "No active jobs" in result.output

    def test_jobs_after_create(self, cli_runner: CliRunner) -> None:
        cli_runner.invoke(
            main,
            ["job", "new", "--client", "A", "--description", "Task A", "--source", "Other"],
        )
        result = cli_runner.invoke(main, ["jobs"])
        assert result.exit_code == 0
        assert "JOB-001" in result.output

    def test_status(self, cli_runner: CliRunner) -> None:
        cli_runner.invoke(
            main,
            ["job", "new", "--client", "TestCo", "--description", "API fix", "--source", "Direct"],
        )
        result = cli_runner.invoke(main, ["status", "JOB-001"])
        assert result.exit_code == 0
        assert "JOB-001" in result.output
        assert "TestCo" in result.output

    def test_status_not_found(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["status", "JOB-999"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_job_update(self, cli_runner: CliRunner) -> None:
        cli_runner.invoke(
            main,
            ["job", "new", "--client", "X", "--description", "Y", "--source", "Other"],
        )
        result = cli_runner.invoke(
            main,
            ["job", "update", "JOB-001", "--status", "ANALYSIS", "--note", "Starting"],
        )
        assert result.exit_code == 0
        assert "ANALYSIS" in result.output

    def test_placeholder_commands(self, cli_runner: CliRunner) -> None:
        """Placeholder commands should print a warning but not crash."""
        for cmd in ["analyze", "estimate", "requirements", "start", "handoff", "finish"]:
            result = cli_runner.invoke(main, [cmd, "JOB-001"])
            assert result.exit_code == 0
            assert "not yet implemented" in result.output.lower()
