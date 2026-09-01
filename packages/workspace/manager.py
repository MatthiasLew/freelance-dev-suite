"""Workspace manager — high-level operations on jobs."""

from __future__ import annotations

from pathlib import Path

from freelance_cli.config import Config, load_config, save_config
from freelance_cli.models.job import Job, JobSource, JobStatus
from packages.workspace.storage import (
    find_all_jobs,
    find_job_by_id,
    find_job_dir,
    save_job,
)


class WorkspaceManager:
    """Manages the freelance workspace: creating, listing, and updating jobs."""

    def __init__(self, config: Config | None = None, config_path: Path | None = None) -> None:
        self.config_path = config_path
        self.config = config or load_config(config_path)
        self._ensure_workspace()

    def _ensure_workspace(self) -> None:
        """Create workspace directories if they don't exist."""
        root = self.config.workspace_path
        for subdir in ["active", "finished", "templates", "config"]:
            (root / subdir).mkdir(parents=True, exist_ok=True)

    def create_job(
        self,
        client: str,
        description: str,
        source: str = JobSource.OTHER.value,
        budget_pln: float | None = None,
        deadline: str | None = None,
        repository: str | None = None,
        notes: str = "",
    ) -> Job:
        """Create a new job and save it to the workspace."""
        job_id = self.config.next_job_id()
        job = Job(
            id=job_id,
            client=client,
            description=description,
            source=source,
            status=JobStatus.LEAD.value,
            budget_pln=budget_pln,
            deadline=deadline,
            repository=repository,
            notes=notes,
        )
        save_job(job, self.config.workspace_path)
        save_config(self.config, self.config_path)
        return job

    def list_jobs(self, include_finished: bool = False) -> list[Job]:
        """List all active jobs, optionally including finished ones."""
        jobs = find_all_jobs(self.config.workspace_path)
        if not include_finished:
            finished_statuses = {JobStatus.CLOSED.value, JobStatus.REJECTED.value}
            jobs = [j for j in jobs if j.status not in finished_statuses]
        return jobs

    def get_job(self, job_id: str) -> Job | None:
        """Get a specific job by ID."""
        return find_job_by_id(job_id, self.config.workspace_path)

    def update_job_status(self, job_id: str, new_status: str, note: str = "") -> Job | None:
        """Update a job's status."""
        job = find_job_by_id(job_id, self.config.workspace_path)
        if job is None:
            return None
        job.change_status(new_status, note)
        save_job(job, self.config.workspace_path)
        return job

    def get_job_dir(self, job_id: str) -> Path | None:
        """Get the directory path for a job."""
        return find_job_dir(job_id, self.config.workspace_path)
