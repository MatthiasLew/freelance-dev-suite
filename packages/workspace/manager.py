"""Workspace manager — high-level operations on jobs."""

from __future__ import annotations

import os
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


def _scan_highest_job_id(workspace_path: Path) -> int:
    """Find the highest existing numeric job suffix across active/ and finished/ directories."""
    highest = 0
    for parent_dir_name in ("active", "finished"):
        parent_dir = workspace_path / parent_dir_name
        if not parent_dir.exists():
            continue
        try:
            with os.scandir(parent_dir) as entries:
                for entry in entries:
                    if entry.is_dir() and entry.name.startswith("JOB-"):
                        num_part = entry.name[4:].split("-", 1)[0]
                        if num_part.isdigit():
                            val = int(num_part)
                            if val > highest:
                                highest = val
        except OSError:
            pass
    return highest


class WorkspaceManager:
    """Manages the freelance workspace: creating, listing, and updating jobs."""

    def __init__(self, config: Config | None = None, config_path: Path | None = None) -> None:
        self.config_path = config_path
        # A caller-supplied Config may be an in-memory or temporary configuration.
        # Without an explicit destination, persisting it to the user's default
        # ~/.freelance/config.yaml would be an unexpected global side effect.
        self._persist_config = config is None or config_path is not None
        self.config = config or load_config(config_path)
        self._high_watermark: int | None = None
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

            # Lazy synchronization on first job creation or if external config increased counter
            if self._high_watermark is None:
                self._high_watermark = max(
                    self.config.job_counter,
                    _scan_highest_job_id(self.config.workspace_path),
                )
            elif self.config.job_counter > self._high_watermark:
                self._high_watermark = self.config.job_counter

            candidate = self._high_watermark + 1
            candidate_id = f"JOB-{candidate:03d}"
            conflict_dir = find_job_dir(candidate_id, self.config.workspace_path)
            if conflict_dir is not None:
                # Unexpected external modification / unmanifested directory
                self._high_watermark = max(
                    candidate,
                    _scan_highest_job_id(self.config.workspace_path),
                )
                candidate = self._high_watermark + 1
                candidate_id = f"JOB-{candidate:03d}"

            self._high_watermark = candidate
            self.config.job_counter = candidate
            job_id = candidate_id

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
