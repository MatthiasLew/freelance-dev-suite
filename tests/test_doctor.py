"""Tests for freelance doctor command and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from freelance_cli.cli import main
from freelance_cli.doctor_commands import _parse_version, check_environment
from packages.workspace.manager import WorkspaceManager


def test_parse_version() -> None:
    assert _parse_version("ai-dev 1.3.0") == (1, 3, 0)
    assert _parse_version("v2.0.1") == (2, 0, 1)
    assert _parse_version("3.14.0") == (3, 14, 0)


def test_doctor_command_human_readable(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "FREELANCE DEV SUITE DOCTOR" in result.output
    assert "Python Environment" in result.output
    assert "Workspace Directory" in result.output
    assert "Overall Status:" in result.output


def test_doctor_command_json(cli_runner: CliRunner) -> None:
    result = cli_runner.invoke(main, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "doctor"
    assert "overall_status" in payload
    assert "checks" in payload
    assert isinstance(payload["checks"], list)
    names = {c["name"] for c in payload["checks"]}
    assert "Python Environment" in names
    assert "Workspace Directory" in names
    assert "Git Executable" in names
    assert "ai-dev Technical Engine" in names
    assert "Persistent State Schema" in names


def test_doctor_corrupted_state_detection(tmp_path: Path) -> None:
    mgr = WorkspaceManager()
    mgr.config.workspace_root = str(tmp_path)
    active_dir = tmp_path / "active" / "JOB-001"
    active_dir.mkdir(parents=True, exist_ok=True)
    # Corrupt job.json
    (active_dir / "job.json").write_text("{ corrupt json: ", encoding="utf-8")

    diag = check_environment(mgr)
    state_check = next(c for c in diag["checks"] if c["name"] == "Persistent State Schema")
    assert state_check["status"] == "FAIL"
    assert diag["overall_status"] == "UNHEALTHY"
    assert len(diag["issues"]) > 0


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize(
    "error", [PermissionError("workspace not writable"), OSError("disk unavailable")]
)
def test_doctor_workspace_initialization_failure(
    monkeypatch: pytest.MonkeyPatch, json_output: bool, error: OSError
) -> None:
    def unavailable_manager() -> WorkspaceManager:
        raise error

    monkeypatch.setattr("freelance_cli.cli._get_manager", unavailable_manager)
    monkeypatch.setattr("freelance_cli.doctor_commands.shutil.which", lambda _: None)
    result = CliRunner().invoke(main, ["doctor", *(["--json"] if json_output else [])])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert str(error) in result.output
    assert "permissions" in result.output
    assert "Traceback" not in result.output
    if json_output:
        payload = json.loads(result.output)
        assert payload["status"] == "error"
        assert payload["exit_code"] == result.exit_code
        assert payload["overall_status"] == "UNHEALTHY"
        checks = {c["name"]: c for c in payload["checks"]}
        assert checks["Workspace Directory"]["status"] == "FAIL"
        assert checks["Python Environment"]["status"] == "PASS"
        assert "Git Executable" in checks
        assert "ai-dev Technical Engine" in checks
        assert checks["Persistent State Schema"]["status"] == "WARN"
        assert "incomplete" in checks["Persistent State Schema"]["details"]
        assert payload["errors"]


def test_doctor_unhealthy_json_process_exit_code(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("freelance_cli.doctor_commands.os.access", lambda *_: False)
    monkeypatch.setattr("freelance_cli.doctor_commands.shutil.which", lambda _: None)
    result = cli_runner.invoke(main, ["doctor", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == payload["exit_code"] == 1
    assert payload["overall_status"] == "UNHEALTHY"


def test_doctor_state_directory_access_failure(
    cli_runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied_iterdir(path: Path) -> object:
        raise PermissionError(f"Cannot list {path}")

    monkeypatch.setattr(Path, "iterdir", denied_iterdir)
    monkeypatch.setattr("freelance_cli.doctor_commands.shutil.which", lambda _: None)
    result = cli_runner.invoke(main, ["doctor", "--json"])
    payload = json.loads(result.output)
    assert result.exit_code == payload["exit_code"] == 1
    assert payload["overall_status"] == "UNHEALTHY"
    state_check = next(c for c in payload["checks"] if c["name"] == "Persistent State Schema")
    assert state_check["status"] == "WARN"
    assert "incomplete" in state_check["details"]
