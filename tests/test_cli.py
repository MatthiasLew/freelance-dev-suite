"""Test for CLI commands using Click's test runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from freelance_cli.cli import main
from packages.intake.analyzer import IntakeResult


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
            [
                "job",
                "new",
                "--client",
                "TestCo",
                "--description",
                "Fix bug",
                "--source",
                "Useme",
                "--budget",
                "500",
                "--deadline",
                "2026-09-15",
            ],
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
        for cmd in ["start", "handoff", "finish"]:
            result = cli_runner.invoke(main, [cmd, "JOB-001"])
            assert result.exit_code == 0
            assert "not yet implemented" in result.output.lower()

    def test_analyze_then_estimate_json(
        self,
        cli_runner: CliRunner,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repository = tmp_path / "client-repo"
        repository.mkdir()
        created = cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Client",
                "--description",
                "Fix parser",
                "--source",
                "Direct",
                "--repository",
                str(repository),
            ],
        )
        assert created.exit_code == 0

        intake = IntakeResult(
            project_path=str(repository),
            languages=["python"],
            frameworks=[],
            package_managers=["pip/pyproject"],
            has_tests=True,
            has_lint=True,
            has_typecheck=True,
            has_docker=False,
            has_ci=True,
            total_files=10,
            source_files=4,
            loc=500,
            dependency_count=3,
            repo_size_bytes=1_000,
            risk_level="LOW",
            risk_factors=[],
            complexity="LOW",
            estimated_hours_min=1.0,
            estimated_hours_max=3.0,
            workspace_count=1,
            scan_data={},
            timestamp="2026-09-02T00:00:00+02:00",
            validation_status="success",
            tests_total=5,
            tests_passed=5,
            lint_status="passed",
            typecheck_status="passed",
            context_tokens=2_000,
        )
        monkeypatch.setattr(
            "packages.intake.analyzer.analyze_project",
            lambda *args, **kwargs: intake,
        )

        analyzed = cli_runner.invoke(main, ["analyze", "JOB-001", "--json"])
        assert analyzed.exit_code == 0, analyzed.output
        assert json.loads(analyzed.output)["intake"]["tests_passed"] == 5

        estimated = cli_runner.invoke(main, ["estimate", "JOB-001", "--json"])
        assert estimated.exit_code == 0, estimated.output
        assert json.loads(estimated.output)["minimum_technical_price_pln"] > 0
