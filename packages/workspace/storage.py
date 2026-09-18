"""JSON file storage for jobs.

Each job is stored as a `job.json` file inside its workspace directory:
    <workspace_root>/active/<JOB-ID>-<slug>/job.json
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from freelance_cli.models.job import Job
from packages.storage_utils import StateError, atomic_write_json, safe_read_json


def _slugify(text: str, max_len: int = 30) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def job_dir_name(job: Job) -> str:
    """Generate the directory name for a job: JOB-001-client-slug."""
    slug = _slugify(f"{job.client}-{job.description}")
    return f"{job.id}-{slug}"


STANDARD_JOB_SUBDIRS = (
    "client",
    "analysis",
    "work",
    "work/bugs",
    "work/scope",
    "handoff",
)


def _ensure_job_subdirs(job_dir: Path) -> None:
    """Ensure all standard job subdirectories exist (self-healing for legacy/imported jobs)."""
    for subdir in STANDARD_JOB_SUBDIRS:
        subpath = job_dir / subdir
        if not subpath.exists():
            subpath.mkdir(parents=True, exist_ok=True)


def save_job(job: Job, workspace_root: Path, job_dir: Path | None = None) -> Path:
    """Save a job to its workspace directory. Returns the job directory path."""
    # Preserve the current lifecycle location. Re-saving a job found under
    # ``finished`` must not silently create a second, active copy of it.
    if job_dir is None:
        job_dir = find_job_dir(job.id, workspace_root)
    is_new = job_dir is None
    if is_new:
        job_dir = workspace_root / "active" / job_dir_name(job)
        job_dir.mkdir(parents=True, exist_ok=True)
    else:
        assert job_dir is not None
        if not job_dir.exists():
            job_dir.mkdir(parents=True, exist_ok=True)

    # Self-healing: ensure standard subdirectories exist without redundant mkdir calls
    _ensure_job_subdirs(job_dir)

    # Write job metadata
    job_path = job_dir / "job.json"
    atomic_write_json(job_path, job.to_dict())

    return job_dir


def load_job(job_path: Path) -> Job:
    """Load a job from a job.json file."""
    data = safe_read_json(job_path)
    return Job.from_dict(data)


def _load_jobs_from(parent_dir: Path) -> list[Job]:
    jobs: list[Job] = []
    if not parent_dir.exists():
        return jobs
    try:
        with os.scandir(parent_dir) as entries:
            dir_entries = [e for e in entries if e.is_dir()]
    except OSError:
        return jobs

    dir_entries.sort(key=lambda e: e.name)
    for entry in dir_entries:
        job_file = Path(entry.path) / "job.json"
        if job_file.exists():
            try:
                jobs.append(load_job(job_file))
            except (StateError, TypeError, KeyError):
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


def find_job_dir(job_id: str, workspace_root: Path) -> Path | None:
    """Find the directory path of a job by its JOB-ID."""
    for parent in ("active", "finished"):
        parent_dir = workspace_root / parent
        if not parent_dir.exists():
            continue
        try:
            with os.scandir(parent_dir) as entries:
                for entry in entries:
                    if entry.is_dir() and _matches_job_id(entry.name, job_id):
                        return Path(entry.path)
        except OSError:
            continue
    return None


def find_job_entry(job_id: str, workspace_root: Path) -> tuple[Job, Path] | None:
    """Find a specific job and its directory in a single lookup."""
    job_dir = find_job_dir(job_id, workspace_root)
    if job_dir is None:
        return None
    job_file = job_dir / "job.json"
    if job_file.exists():
        try:
            return load_job(job_file), job_dir
        except (StateError, TypeError, KeyError):
            return None
    return None


def find_job_by_id(job_id: str, workspace_root: Path) -> Job | None:
    """Find a specific job by its JOB-ID."""
    entry = find_job_entry(job_id, workspace_root)
    return entry[0] if entry else None


def archive_job(job_id: str, workspace_root: Path) -> Path | None:
    """Move a job directory from active/ to finished/. Returns new directory path."""
    active_dir = workspace_root / "active"
    if not active_dir.exists():
        return None

    try:
        with os.scandir(active_dir) as entries:
            target_entry = next(
                (e for e in entries if e.is_dir() and _matches_job_id(e.name, job_id)),
                None,
            )
    except OSError:
        return None

    if target_entry is None:
        return None

    finished_dir = workspace_root / "finished"
    finished_dir.mkdir(parents=True, exist_ok=True)
    dest = finished_dir / target_entry.name
    Path(target_entry.path).rename(dest)
    return dest
