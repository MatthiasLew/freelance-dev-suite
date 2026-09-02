"""JSON file storage for jobs.

Each job is stored as a `job.json` file inside its workspace directory:
    <workspace_root>/active/<JOB-ID>-<slug>/job.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from freelance_cli.models.job import Job


def _slugify(text: str, max_len: int = 30) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def job_dir_name(job: Job) -> str:
    """Generate the directory name for a job: JOB-001-client-slug."""
    slug = _slugify(f"{job.client}-{job.description}")
    return f"{job.id}-{slug}"


def save_job(job: Job, workspace_root: Path) -> Path:
    """Save a job to its workspace directory. Returns the job directory path."""
    active_dir = workspace_root / "active"
    job_dir = active_dir / job_dir_name(job)
    job_dir.mkdir(parents=True, exist_ok=True)

    # Create standard subdirectories
    for subdir in ["client", "analysis", "work", "work/bugs", "work/scope", "handoff"]:
        (job_dir / subdir).mkdir(parents=True, exist_ok=True)

    # Write job metadata
    job_path = job_dir / "job.json"
    with open(job_path, "w", encoding="utf-8") as f:
        json.dump(job.to_dict(), f, indent=2, ensure_ascii=False)

    return job_dir


def load_job(job_path: Path) -> Job:
    """Load a job from a job.json file."""
    with open(job_path, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return Job.from_dict(data)


def _load_jobs_from(parent_dir: Path) -> list[Job]:
    jobs: list[Job] = []
    if not parent_dir.exists():
        return jobs
    for job_dir in sorted(parent_dir.iterdir()):
        job_file = job_dir / "job.json"
        if job_file.exists():
            try:
                jobs.append(load_job(job_file))
            except (json.JSONDecodeError, TypeError, KeyError):
                # Skip corrupted job files
                continue
    return jobs


def find_all_jobs(workspace_root: Path, include_finished: bool = False) -> list[Job]:
    """Find jobs in active and, when requested, finished storage."""
    jobs = _load_jobs_from(workspace_root / "active")
    if include_finished:
        jobs.extend(_load_jobs_from(workspace_root / "finished"))
    return jobs


def _matches_job_id(directory_name: str, job_id: str) -> bool:
    return directory_name == job_id or directory_name.startswith(f"{job_id}-")


def find_job_by_id(job_id: str, workspace_root: Path) -> Job | None:
    """Find a specific job by its JOB-ID."""
    active_dir = workspace_root / "active"
    if not active_dir.exists():
        return None

    # JOB-ID is the prefix of the directory name
    for job_dir in active_dir.iterdir():
        if _matches_job_id(job_dir.name, job_id):
            job_file = job_dir / "job.json"
            if job_file.exists():
                return load_job(job_file)

    # Also check finished
    finished_dir = workspace_root / "finished"
    if finished_dir.exists():
        for job_dir in finished_dir.iterdir():
            if _matches_job_id(job_dir.name, job_id):
                job_file = job_dir / "job.json"
                if job_file.exists():
                    return load_job(job_file)

    return None


def find_job_dir(job_id: str, workspace_root: Path) -> Path | None:
    """Find the directory path of a job by its JOB-ID."""
    for parent in ["active", "finished"]:
        parent_dir = workspace_root / parent
        if not parent_dir.exists():
            continue
        for job_dir in parent_dir.iterdir():
            if _matches_job_id(job_dir.name, job_id):
                return job_dir
    return None


def archive_job(job_id: str, workspace_root: Path) -> Path | None:
    """Move a job directory from active/ to finished/. Returns new directory path."""
    active_dir = workspace_root / "active"
    finished_dir = workspace_root / "finished"
    finished_dir.mkdir(parents=True, exist_ok=True)

    if not active_dir.exists():
        return None

    for job_dir in active_dir.iterdir():
        if _matches_job_id(job_dir.name, job_id):
            dest = finished_dir / job_dir.name
            job_dir.rename(dest)
            return dest
    return None

