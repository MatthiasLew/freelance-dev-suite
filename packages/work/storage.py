"""Atomic local persistence for work sessions."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .models import WorkSession, WorkStatus

_WORK_ID_PATTERN = re.compile(r"^WORK-(\d+)$")


def sessions_dir(job_dir: Path) -> Path:
    return job_dir / "work" / "sessions"


def save_work_session(session: WorkSession, job_dir: Path) -> Path:
    """Atomically persist a session in its owning job directory."""
    directory = sessions_dir(job_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session.id}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def load_work_session(path: Path) -> WorkSession:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid work session file: {path}")
    return WorkSession.from_dict(data)


def list_work_sessions(job_dir: Path) -> list[WorkSession]:
    directory = sessions_dir(job_dir)
    if not directory.exists():
        return []
    sessions: list[WorkSession] = []
    for path in sorted(directory.glob("WORK-*.json")):
        try:
            sessions.append(load_work_session(path))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
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
    """Generate a workspace-wide sequential ID."""
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
