"""Tests for safe mutation UX: --dry-run, --explain, and blocked quality gates."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main


def test_job_new_dry_run(cli_runner: CliRunner) -> None:
    res = cli_runner.invoke(
        main,
        [
            "job",
            "new",
            "--client",
            "DryClient",
            "--description",
            "Dry test",
            "--source",
            "Direct",
            "--dry-run",
        ],
    )
    assert res.exit_code == 0
    assert "[DRY-RUN]" in res.output
    assert "Would create" in res.output
    assert "DryClient" in res.output

    # Verify no jobs created in workspace
    jobs_res = cli_runner.invoke(main, ["jobs", "--json"])
    data = json.loads(jobs_res.output)["data"]
    assert len(data) == 0


def test_bootstrap_explain_and_dry_run(cli_runner: CliRunner, tmp_path: Path) -> None:
    dest = tmp_path / "dry_app"

    # Explain
    res_exp = cli_runner.invoke(
        main,
        ["bootstrap", "python-cli", "--path", str(dest), "--explain"],
    )
    assert res_exp.exit_code == 0
    assert "EXPLAIN BOOTSTRAP PLAN" in res_exp.output
    assert not dest.exists()

    # Dry-run
    res_dry = cli_runner.invoke(
        main,
        ["bootstrap", "python-cli", "--path", str(dest), "--dry-run"],
    )
    assert res_dry.exit_code == 0
    assert "DRY-RUN BOOTSTRAP" in res_dry.output
    assert not dest.exists()


def test_start_job_explain_and_dry_run(cli_runner: CliRunner) -> None:
    cli_runner.invoke(
        main,
        [
            "job",
            "new",
            "--client",
            "StartClient",
            "--description",
            "Start job testing",
            "--source",
            "Direct",
        ],
    )

    # Explain
    res_exp = cli_runner.invoke(main, ["start", "JOB-001", "--explain"])
    assert res_exp.exit_code == 0
    assert "EXPLAIN START PLAN" in res_exp.output

    # Dry-run
    res_dry = cli_runner.invoke(main, ["start", "JOB-001", "--dry-run", "--json"])
    assert res_dry.exit_code == 0
    payload = json.loads(res_dry.output)
    assert payload["mode"] == "dry-run"
    assert payload["target_status"] == "IN_PROGRESS"

    # Verify job status has NOT changed
    status_res = cli_runner.invoke(main, ["status", "JOB-001", "--json"])
    job_data = json.loads(status_res.output)
    assert job_data["data"]["status"] == "LEAD"


def test_finish_explain_and_dry_run(cli_runner: CliRunner) -> None:
    cli_runner.invoke(
        main,
        [
            "job",
            "new",
            "--client",
            "FinishClient",
            "--description",
            "Finish test",
            "--source",
            "Direct",
        ],
    )

    # Explain
    res_exp = cli_runner.invoke(main, ["finish", "JOB-001", "--explain"])
    assert res_exp.exit_code == 0
    assert "FINISH JOB EXECUTION PLAN" in res_exp.output

    # Dry-run with --force
    res_dry = cli_runner.invoke(main, ["finish", "JOB-001", "--dry-run", "--force"])
    assert res_dry.exit_code == 0
    assert "[DRY-RUN] Would finish JOB-001" in res_dry.output

    # Verify status is still LEAD
    status_res = cli_runner.invoke(main, ["status", "JOB-001", "--json"])
    assert json.loads(status_res.output)["data"]["status"] == "LEAD"


def test_finish_blocked_exit_code_3_without_force(cli_runner: CliRunner) -> None:
    cli_runner.invoke(
        main,
        [
            "job",
            "new",
            "--client",
            "BlockedClient",
            "--description",
            "Blocked finish test",
            "--source",
            "Direct",
        ],
    )
    # Generate requirements so that uncompleted items exist
    cli_runner.invoke(
        main,
        ["requirements", "JOB-001", "--from-text", "System must have secure auth and billing."],
    )
    # Finish without --force should be BLOCKED (exit code 3)
    res = cli_runner.invoke(main, ["finish", "JOB-001"])
    assert res.exit_code == 3  # Standard EXIT_BLOCKED
    assert "BLOCKED" in res.output
