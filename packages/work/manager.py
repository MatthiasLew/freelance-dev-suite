"""Business orchestration for development work sessions."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from freelance_cli.config import Config
from packages.intake.analyzer import _run_ai_dev
from packages.requirements.models import RequirementsSpec
from packages.scope.detector import ScopeChangeDetector
from packages.tracking.timer import TimeTracker
from packages.workspace.manager import WorkspaceManager

from .models import WorkSession, WorkStatus
from .storage import (
    active_work_session,
    find_work_session,
    list_work_sessions,
    next_work_id,
    save_work_session,
)

AIDevRunner = Callable[..., dict[str, Any]]
_TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_tokens",
)


class WorkManager:
    """Connect client/job state with repository-aware technical work."""

    def __init__(
        self,
        workspace: WorkspaceManager,
        ai_dev_runner: AIDevRunner = _run_ai_dev,
    ) -> None:
        self.workspace = workspace
        self.ai_dev_runner = ai_dev_runner
        self.timer = TimeTracker()
        self.scope = ScopeChangeDetector()

    def start(
        self,
        job_id: str,
        task: str,
        *,
        agent: str = "generic",
        model: str | None = None,
        related_requirements: list[str] | None = None,
    ) -> WorkSession:
        """Prepare repository context and start a tracked work session."""
        clean_job_id = job_id.upper()
        job, job_dir, repository = self._job_context(clean_job_id)
        if not task.strip():
            raise ValueError("Work task cannot be empty.")
        existing = active_work_session(job_dir)
        if existing:
            raise ValueError(
                f"{job.id} already has active session {existing.id}; finish it first."
            )

        time_log = self.timer.get_time_log(job_dir, job.id)
        if time_log.active_entry:
            raise ValueError(
                f"{job.id} already has active timer {time_log.active_entry.id}; stop it first."
            )

        specification = self._load_requirements(job_dir)
        change_id = self.scope.next_change_id(job_dir)
        scope_item = self.scope.analyze_request(
            job_id=job.id,
            change_id=change_id,
            requested_text=task,
            requirements_spec=specification,
            hourly_rate_pln=self.workspace.config.pricing.hourly_rate,
        )
        self.scope.save_change(scope_item, job_dir)

        baseline = self._telemetry_snapshot(repository)
        client = agent if agent in {"codex", "claude", "cursor", "generic"} else "generic"
        prepared = self.ai_dev_runner(
            repository,
            "task",
            "--task",
            task.strip(),
            "--mode",
            "changed",
            "--profile",
            "implement",
            "--client",
            client,
        )
        if prepared.get("status") not in {"success", "partial"}:
            raise RuntimeError("ai-dev could not prepare the work task.")

        timer_entry = self.timer.start_timer(job_dir, job.id, activity=f"work: {task.strip()}")
        matched = [str(item) for item in scope_item.matched_existing_requirements]
        requirements = list(dict.fromkeys([*(related_requirements or []), *matched]))
        state = prepared.get("summary", {}).get("state", {})
        fingerprint = state.get("fingerprint") if isinstance(state, dict) else None
        now = datetime.now().astimezone().isoformat()
        session = WorkSession(
            id=next_work_id(self.workspace.config.workspace_path),
            job_id=job.id,
            task=task.strip(),
            repository=str(repository),
            agent=agent,
            model=model or self.workspace.config.default_model,
            related_requirements=requirements,
            scope_classification=scope_item.classification,
            scope_change_id=scope_item.id,
            timer_entry_ids=[timer_entry.id],
            context_fingerprint=str(fingerprint) if fingerprint else None,
            telemetry_baseline=baseline,
            started_at=now,
            updated_at=now,
        )
        save_work_session(session, job_dir)
        return session

    def finish(self, work_id: str) -> WorkSession:
        """Validate the repository, stop time tracking, and finalize a session."""
        session, job_dir, repository = self._session_context(work_id)
        if session.status != WorkStatus.ACTIVE.value:
            raise ValueError(f"{session.id} is not active; current status is {session.status}.")

        try:
            validation = self.ai_dev_runner(
                repository, "check", "--mode", "changed", "--no-cache"
            )
        except (OSError, RuntimeError, ValueError) as exc:
            validation = {
                "status": "failed",
                "summary": {"first_failure": {"message": str(exc)}},
                "artifacts": [],
            }

        stopped = self._stop_owned_timer(session, job_dir)
        session.duration_minutes = round(session.duration_minutes + stopped.duration_minutes, 2)
        usage = self._usage_delta(
            session.telemetry_baseline,
            self._telemetry_snapshot(repository),
            self.workspace.config,
            session.model,
        )
        for field in _TOKEN_FIELDS:
            setattr(session, field, int(usage[field]))
        session.total_tokens = session.input_tokens + session.output_tokens
        session.ai_costs = dict(usage["estimated_costs"])
        session.ai_cost_pln = float(usage["ai_cost_pln"])
        session.validation_status = str(validation.get("status", "failed"))
        session.validation_summary = self._compact_validation(validation)
        session.status = (
            WorkStatus.VERIFIED.value
            if session.validation_status == "success"
            else WorkStatus.NEEDS_FIX.value
        )
        now = datetime.now().astimezone().isoformat()
        session.updated_at = now
        session.finished_at = now
        save_work_session(session, job_dir)
        return session

    def resume(self, work_id: str) -> WorkSession:
        """Resume a failed session using its acknowledged incremental context."""
        session, job_dir, repository = self._session_context(work_id)
        if session.status == WorkStatus.VERIFIED.value:
            raise ValueError(f"{session.id} is already verified and cannot be resumed.")
        if session.status == WorkStatus.ACTIVE.value:
            return session
        if self.timer.get_time_log(job_dir, session.job_id).active_entry:
            raise ValueError(f"{session.job_id} already has an active timer.")

        client = (
            session.agent
            if session.agent in {"codex", "claude", "cursor", "generic"}
            else "generic"
        )
        arguments = [
            "task",
            "--task",
            session.task,
            "--mode",
            "changed",
            "--profile",
            "implement",
            "--client",
            client,
        ]
        if session.context_fingerprint:
            arguments.extend(["--ack-state", session.context_fingerprint])
        prepared = self.ai_dev_runner(repository, *arguments)
        if prepared.get("status") not in {"success", "partial"}:
            raise RuntimeError("ai-dev could not resume the work task.")

        state = prepared.get("summary", {}).get("state", {})
        fingerprint = state.get("fingerprint") if isinstance(state, dict) else None
        if fingerprint:
            session.context_fingerprint = str(fingerprint)
        timer_entry = self.timer.start_timer(
            job_dir, session.job_id, activity=f"work: {session.task}"
        )
        session.timer_entry_ids.append(timer_entry.id)
        session.status = WorkStatus.ACTIVE.value
        session.validation_status = "not_run"
        session.validation_summary = {}
        session.finished_at = None
        session.updated_at = datetime.now().astimezone().isoformat()
        save_work_session(session, job_dir)
        return session

    def get(self, work_id: str) -> WorkSession:
        found = find_work_session(self.workspace.config.workspace_path, work_id)
        if found is None:
            raise ValueError(f"Work session not found: {work_id.upper()}")
        return found[0]

    def list_for_job(self, job_id: str) -> list[WorkSession]:
        _job, job_dir = self._job_directory(job_id.upper())
        return list_work_sessions(job_dir)

    def current_for_job(self, job_id: str) -> WorkSession | None:
        sessions = self.list_for_job(job_id)
        active = [item for item in sessions if item.status == WorkStatus.ACTIVE.value]
        return active[-1] if active else sessions[-1] if sessions else None

    def elapsed_minutes(self, session: WorkSession) -> float:
        """Return persisted time plus the currently running segment."""
        found = find_work_session(self.workspace.config.workspace_path, session.id)
        if found is None:
            return session.duration_minutes
        _, job_dir = found
        active = self.timer.get_time_log(job_dir, session.job_id).active_entry
        if not active or active.id not in session.timer_entry_ids:
            return session.duration_minutes
        try:
            started = datetime.fromisoformat(active.start_time)
            running = max(0.0, (datetime.now().astimezone() - started).total_seconds() / 60.0)
        except (TypeError, ValueError):
            running = 0.0
        return round(session.duration_minutes + running, 2)

    def _job_context(self, job_id: str) -> tuple[Any, Path, Path]:
        job, job_dir = self._job_directory(job_id)
        if not job.repository:
            raise ValueError(f"{job_id} has no repository path configured.")
        repository = Path(job.repository).expanduser().resolve()
        if not repository.is_dir():
            raise ValueError(f"Repository directory does not exist: {repository}")
        return job, job_dir, repository

    def _job_directory(self, job_id: str) -> tuple[Any, Path]:
        job = self.workspace.get_job(job_id)
        job_dir = self.workspace.get_job_dir(job_id)
        if job is None or job_dir is None:
            raise ValueError(f"Job not found: {job_id}")
        return job, job_dir

    def _session_context(self, work_id: str) -> tuple[WorkSession, Path, Path]:
        found = find_work_session(self.workspace.config.workspace_path, work_id)
        if found is None:
            raise ValueError(f"Work session not found: {work_id.upper()}")
        session, job_dir = found
        repository = Path(session.repository).expanduser().resolve()
        if not repository.is_dir():
            raise ValueError(f"Repository directory does not exist: {repository}")
        return session, job_dir, repository

    def _load_requirements(self, job_dir: Path) -> RequirementsSpec | None:
        path = job_dir / "analysis" / "requirements.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RequirementsSpec.from_dict(data) if isinstance(data, dict) else None
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _telemetry_snapshot(self, repository: Path) -> dict[str, Any]:
        try:
            report = self.ai_dev_runner(repository, "telemetry", "status")
            summary = report.get("summary", {})
            return dict(summary) if isinstance(summary, dict) else {}
        except (OSError, RuntimeError, ValueError):
            return {}

    def _stop_owned_timer(self, session: WorkSession, job_dir: Path) -> Any:
        active = self.timer.get_time_log(job_dir, session.job_id).active_entry
        if active is None:
            raise ValueError(f"No active timer found for {session.id}.")
        if active.id not in session.timer_entry_ids:
            raise ValueError(f"Active timer {active.id} does not belong to {session.id}.")
        return self.timer.stop_timer(job_dir, session.job_id, note=f"Work session {session.id}")

    @staticmethod
    def _compact_validation(report: dict[str, Any]) -> dict[str, Any]:
        summary = report.get("summary", {})
        data = summary if isinstance(summary, dict) else {}
        artifacts = report.get("artifacts", [])
        paths = [
            str(item.get("path"))
            for item in artifacts
            if isinstance(item, dict) and item.get("path")
        ]
        return {
            "checks_total": data.get("checks_total", 0),
            "checks_failed": data.get("checks_failed", 0),
            "tests_total": data.get("tests_total", 0),
            "tests_passed": data.get("tests_passed", 0),
            "tests_failed": data.get("tests_failed", 0),
            "first_failure": data.get("first_failure"),
            "artifacts": paths,
        }

    @staticmethod
    def _usage_delta(
        baseline: dict[str, Any],
        current: dict[str, Any],
        config: Config,
        model_name: str,
    ) -> dict[str, Any]:
        delta: dict[str, Any] = {}
        for field in _TOKEN_FIELDS:
            before = baseline.get(field, 0)
            after = current.get(field, 0)
            before_value = before if isinstance(before, int) and not isinstance(before, bool) else 0
            after_value = after if isinstance(after, int) and not isinstance(after, bool) else 0
            delta[field] = max(0, after_value - before_value)

        before_costs = baseline.get("estimated_costs", {})
        after_costs = current.get("estimated_costs", {})
        before_dict = before_costs if isinstance(before_costs, dict) else {}
        after_dict = after_costs if isinstance(after_costs, dict) else {}
        costs = {
            str(currency): round(
                max(0.0, float(amount) - float(before_dict.get(currency, 0.0))), 8
            )
            for currency, amount in after_dict.items()
            if isinstance(amount, int | float) and not isinstance(amount, bool)
        }

        ai_cost_pln = float(costs.get("PLN", 0.0))
        ai_cost_pln += float(costs.get("USD", 0.0)) * config.usd_to_pln_rate
        if not costs and (delta["input_tokens"] or delta["output_tokens"]):
            from packages.ai_cost.pricing import calculate_cost, get_model, load_model_pricing

            pricing_path = Path(config.model_pricing_path) if config.model_pricing_path else None
            try:
                pricing = load_model_pricing(pricing_path)
                model = get_model(model_name, pricing)
                usd = calculate_cost(
                    model,
                    input_tokens=delta["input_tokens"],
                    output_tokens=delta["output_tokens"],
                    cached_tokens=delta["cached_input_tokens"],
                    reasoning_tokens=delta["reasoning_tokens"],
                )
                costs = {"USD": round(usd, 8)}
                ai_cost_pln = usd * config.usd_to_pln_rate
            except ValueError:
                pass
        delta["estimated_costs"] = costs
        delta["ai_cost_pln"] = round(ai_cost_pln, 4)
        return delta
