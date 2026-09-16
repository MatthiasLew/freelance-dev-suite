"""Atomic local persistence for work sessions."""

from __future__ import annotations

import re
from pathlib import Path

from packages.storage_utils import (
    StateError,
    atomic_write_json,
    safe_read_json,
    storage_lock,
)

from .models import WorkSession, WorkStatus

_WORK_ID_PATTERN = re.compile(r"^WORK-(\d+)$")


def sessions_dir(job_dir: Path) -> Path:
    return job_dir / "work" / "sessions"


def save_work_session(session: WorkSession, job_dir: Path) -> Path:
    """Atomically persist a session in its owning job directory."""
    directory = sessions_dir(job_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session.id}.json"
    atomic_write_json(path, session.to_dict())
    return path


def load_work_session(path: Path) -> WorkSession:
    data = safe_read_json(path)
    return WorkSession.from_dict(data)


def list_work_sessions(job_dir: Path) -> list[WorkSession]:
    directory = sessions_dir(job_dir)
    if not directory.exists():
        return []
    sessions: list[WorkSession] = []
    for path in sorted(directory.glob("WORK-*.json")):
        try:
            sessions.append(load_work_session(path))
        except (OSError, StateError, ValueError, TypeError):
            continue
    return sorted(sessions, key=lambda item: item.started_at)


def active_work_session(job_dir: Path) -> WorkSession | None:
    active = [
        session
        for session in list_work_sessions(job_dir)
        if session.status == WorkStatus.ACTIVE.value
    ]
    if len(active) > 1:
        raise ValueError(f"Multiple active work sessions found in {job_dir}")
    return active[0] if active else None


def find_work_session(workspace_root: Path, work_id: str) -> tuple[WorkSession, Path] | None:
    clean_id = work_id.upper()
    matches: list[tuple[WorkSession, Path]] = []
    for lifecycle in ("active", "finished"):
        parent = workspace_root / lifecycle
        if not parent.exists():
            continue
        for job_dir in parent.iterdir():
            path = sessions_dir(job_dir) / f"{clean_id}.json"
            if path.is_file():
                matches.append((load_work_session(path), job_dir))
    if len(matches) > 1:
        raise ValueError(f"Work session ID is ambiguous: {clean_id}")
    return matches[0] if matches else None


def next_work_id(workspace_root: Path) -> str:
    """Generate a workspace-wide sequential ID under lock."""
    lock_path = workspace_root / ".locks" / "work.lock"
    with storage_lock(lock_path):
        highest = 0
        for lifecycle in ("active", "finished"):
            parent = workspace_root / lifecycle
            if not parent.exists():
                continue
            for path in parent.glob("*/work/sessions/WORK-*.json"):
                match = _WORK_ID_PATTERN.match(path.stem)
                if match:
                    highest = max(highest, int(match.group(1)))
        return f"WORK-{highest + 1:04d}"
