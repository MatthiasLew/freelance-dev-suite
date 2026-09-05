"""Tests for repository-backed development work sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from freelance_cli.cli import main
from freelance_cli.config import Config
from packages.tracking.profitability import ProfitabilityCalculator
from packages.work.manager import WorkManager
from packages.work.models import WorkStatus
from packages.workspace.manager import WorkspaceManager


class FakeAIDev:
    """Small deterministic implementation of the ai-dev JSON contract."""

    def __init__(self, validation_statuses: list[str] | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.validation_statuses = validation_statuses or ["success"]
        self.telemetry_calls = 0

    def __call__(self, _project: Path, *arguments: str) -> dict[str, Any]:
        self.calls.append(arguments)
        if arguments == ("telemetry", "status"):
            self.telemetry_calls += 1
            if self.telemetry_calls == 1:
                return {
                    "status": "success",
                    "summary": {
                        "input_tokens": 100,
                        "cached_input_tokens": 20,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 30,
                        "reasoning_tokens": 5,
                        "estimated_costs": {"USD": 0.5},
                    },
                }
            return {
                "status": "success",
                "summary": {
                    "input_tokens": 160,
                    "cached_input_tokens": 30,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 50,
                    "reasoning_tokens": 8,
                    "estimated_costs": {"USD": 0.75},
                },
            }
        if arguments and arguments[0] == "task":
            return {
                "status": "success",
                "summary": {"state": {"fingerprint": "state-123"}},
            }
        if arguments and arguments[0] == "check":
            status = self.validation_statuses.pop(0)
            failed = 0 if status == "success" else 1
            return {
                "status": status,
                "summary": {
                    "checks_total": 3,
                    "checks_failed": failed,
                    "tests_total": 10,
                    "tests_passed": 10 - failed,
                    "tests_failed": failed,
                },
                "artifacts": [{"path": ".ai/reports/check-changed-latest.json"}],
            }
        raise AssertionError(f"Unexpected ai-dev call: {arguments}")


def make_work_manager(tmp_path: Path, fake: FakeAIDev) -> WorkManager:
    workspace_root = tmp_path / "workspace"
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = WorkspaceManager(Config(workspace_root=str(workspace_root)))
    workspace.create_job(
        client="Acme",
        description="Build API",
        repository=str(repository),
    )
    return WorkManager(workspace, ai_dev_runner=fake)


def test_start_prepares_task_checks_scope_and_starts_timer(tmp_path: Path) -> None:
    fake = FakeAIDev()
    manager = make_work_manager(tmp_path, fake)

    session = manager.start(
        "JOB-001",
        "Implement CSV export",
        agent="codex",
        model="gpt-5.6-sol",
        related_requirements=["REQ-7"],
    )

    assert session.id == "WORK-0001"
    assert session.status == WorkStatus.ACTIVE.value
    assert session.timer_entry_ids == ["SESSION-001"]
    assert session.context_fingerprint == "state-123"
    assert session.related_requirements == ["REQ-7"]
    assert session.scope_classification == "OUT_OF_SCOPE"
    assert any(call and call[0] == "task" for call in fake.calls)


def test_finish_records_validation_time_tokens_and_cost(tmp_path: Path) -> None:
    fake = FakeAIDev()
    manager = make_work_manager(tmp_path, fake)
    started = manager.start("JOB-001", "Fix parser", agent="codex")

    finished = manager.finish(started.id)

    assert finished.status == WorkStatus.VERIFIED.value
    assert finished.validation_status == "success"
    assert finished.input_tokens == 60
    assert finished.cached_input_tokens == 10
    assert finished.output_tokens == 20
    assert finished.reasoning_tokens == 3
    assert finished.total_tokens == 80
    assert finished.ai_costs == {"USD": 0.25}
    assert finished.ai_cost_pln == 1.0
    assert finished.finished_at is not None

    stored = manager.get(started.id)
    assert stored.to_dict() == finished.to_dict()

    job_dir = manager.workspace.get_job_dir("JOB-001")
    assert job_dir is not None
    profitability = ProfitabilityCalculator().calculate("JOB-001", job_dir)
    assert profitability.ai_costs_pln == 1.0


def test_needs_fix_session_can_resume_with_acknowledged_context(tmp_path: Path) -> None:
    fake = FakeAIDev(validation_statuses=["failed", "success"])
    manager = make_work_manager(tmp_path, fake)
    started = manager.start("JOB-001", "Fix validation")
    failed = manager.finish(started.id)

    resumed = manager.resume(failed.id)

    assert failed.status == WorkStatus.NEEDS_FIX.value
    assert resumed.status == WorkStatus.ACTIVE.value
    assert resumed.finished_at is None
    assert resumed.timer_entry_ids == ["SESSION-001", "SESSION-002"]
    task_calls = [call for call in fake.calls if call and call[0] == "task"]
    assert "--ack-state" in task_calls[-1]
    assert "state-123" in task_calls[-1]

    verified = manager.finish(resumed.id)
    assert verified.status == WorkStatus.VERIFIED.value


def test_work_history_survives_missing_repository(tmp_path: Path) -> None:
    fake = FakeAIDev()
    manager = make_work_manager(tmp_path, fake)
    session = manager.start("JOB-001", "Document behavior")
    repository = Path(session.repository)
    repository.rmdir()

    history = manager.list_for_job("JOB-001")

    assert [item.id for item in history] == [session.id]


def test_work_cli_start_status_list_and_finish(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    fake = FakeAIDev()
    manager = make_work_manager(tmp_path, fake)
    monkeypatch.setattr(
        "freelance_cli.work_commands._work_manager",
        lambda: manager,
    )
    runner = CliRunner()

    started = runner.invoke(
        main,
        [
            "work",
            "start",
            "JOB-001",
            "--task",
            "Implement endpoint",
            "--agent",
            "codex",
            "--json",
        ],
    )
    status = runner.invoke(main, ["work", "status", "JOB-001", "--json"])
    listed = runner.invoke(main, ["work", "list", "JOB-001", "--json"])
    finished = runner.invoke(main, ["work", "finish", "WORK-0001", "--json"])

    assert started.exit_code == 0
    assert json.loads(started.output)["id"] == "WORK-0001"
    assert json.loads(status.output)["status"] == "ACTIVE"
    assert len(json.loads(listed.output)) == 1
    assert json.loads(finished.output)["status"] == "VERIFIED"
