"""Workspace manager — high-level operations on jobs."""

from __future__ import annotations

import os
import re
from pathlib import Path

from freelance_cli.config import Config, load_config, save_config
from freelance_cli.models.job import Job, JobSource, JobStatus
from packages.storage_utils import storage_lock
from packages.timeline.manager import TimelineManager
from packages.workspace.storage import (
    archive_job,
    find_all_jobs,
    find_job_by_id,
    find_job_dir,
    find_job_entry,
    save_job,
)


class WorkspaceManager:
    """Manages the freelance workspace: creating, listing, and updating jobs."""

    def __init__(self, config: Config | None = None, config_path: Path | None = None) -> None:
        self.config_path = config_path
        # A caller-supplied Config may be an in-memory or temporary configuration.
        # Without an explicit destination, persisting it to the user's default
        # ~/.freelance/config.yaml would be an unexpected global side effect.
        self._persist_config = config is None or config_path is not None
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
        lock_path = self.config.workspace_path / ".locks" / "jobs.lock"
        with storage_lock(lock_path):
            if self.config_path and self.config_path.exists():
                self.config = load_config(self.config_path)

            candidate = self.config.job_counter + 1
            candidate_id = f"JOB-{candidate:03d}"
            conflict_dir = find_job_dir(candidate_id, self.config.workspace_path)
            if conflict_dir is None:
                self.config.job_counter = candidate
                job_id = candidate_id
            else:
                highest = self.config.job_counter
                for parent_dir in (
                    self.config.workspace_path / "active",
                    self.config.workspace_path / "finished",
                ):
                    if parent_dir.exists():
                        try:
                            with os.scandir(parent_dir) as entries:
                                for p in entries:
                                    if p.is_dir():
                                        match = re.match(r"^JOB-(\d+)", p.name)
                                        if match:
                                            highest = max(highest, int(match.group(1)))
                        except OSError:
                            pass
                self.config.job_counter = highest + 1
                job_id = f"JOB-{self.config.job_counter:03d}"

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
            job_dir = save_job(job, self.config.workspace_path)
            TimelineManager().record_event(
                job_dir,
                job_id,
                "job_created",
                metadata={"client": client, "source": source},
            )
            if self._persist_config:
                save_config(self.config, self.config_path)
        return job

    def list_jobs(self, include_finished: bool = False) -> list[Job]:
        """List all active jobs, optionally including finished ones."""
        jobs = find_all_jobs(self.config.workspace_path, include_finished=include_finished)
        if not include_finished:
            finished_statuses = {JobStatus.CLOSED.value, JobStatus.REJECTED.value}
            jobs = [j for j in jobs if j.status not in finished_statuses]
        return jobs

    def get_job(self, job_id: str) -> Job | None:
        """Get a specific job by ID."""
        return find_job_by_id(job_id, self.config.workspace_path)

    def update_job_status(self, job_id: str, new_status: str, note: str = "") -> Job | None:
        """Update a job's status."""
        entry = find_job_entry(job_id, self.config.workspace_path)
        if entry is None:
            return None
        job, job_dir = entry
        job.change_status(new_status, note)
        save_job(job, self.config.workspace_path, job_dir=job_dir)
        return job

    def get_job_dir(self, job_id: str) -> Path | None:
        """Get the directory path for a job."""
        return find_job_dir(job_id, self.config.workspace_path)

    def archive_job(self, job_id: str) -> Path | None:
        """Move a job to the finished directory."""
        return archive_job(job_id, self.config.workspace_path)
