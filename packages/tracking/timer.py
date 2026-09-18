"""Time tracking operations, active sessions, and persistence."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from packages.storage_utils import (
    StateError,
    atomic_write_json,
    safe_read_json,
    storage_lock,
)

from .models import TimeEntry, TimeLog

_SESSION_ID_PATTERN = re.compile(r"^SESSION-(\d+)$")


class TimeTracker:
    """Manages recording work sessions and time logs."""

    def get_time_log(self, job_dir: Path, job_id: str) -> TimeLog:
        """Load or initialize TimeLog for a job."""
        log_path = job_dir / "work" / "time-log.json"
        if not log_path.exists():
            return TimeLog(job_id=job_id)

        try:
            data = safe_read_json(log_path)
            return TimeLog.from_dict(data)
        except (OSError, StateError, ValueError, TypeError):
            return TimeLog(job_id=job_id)

    def save_time_log(self, time_log: TimeLog, job_dir: Path) -> Path:
        """Persist TimeLog to job work directory."""
        work_dir = job_dir / "work"
        if not work_dir.exists():
            work_dir.mkdir(parents=True, exist_ok=True)

        log_path = work_dir / "time-log.json"
        atomic_write_json(log_path, time_log.to_dict())
        return log_path

    def start_timer(
        self,
        job_dir: Path,
        job_id: str,
        activity: str = "development",
    ) -> TimeEntry:
        """Start a new active timer session for a job."""
        with storage_lock(job_dir / "work" / ".time-log.lock"):
            time_log = self.get_time_log(job_dir, job_id)
            if time_log.active_entry:
                return time_log.active_entry

            highest = 0
            if time_log.entries:
                last_m = _SESSION_ID_PATTERN.match(time_log.entries[-1].id)
                if last_m:
                    highest = int(last_m.group(1))
                else:
                    for e in time_log.entries:
                        m = _SESSION_ID_PATTERN.match(e.id)
                        if m:
                            highest = max(highest, int(m.group(1)))

            entry_id = f"SESSION-{max(highest, len(time_log.entries)) + 1:03d}"
            entry = TimeEntry(
                id=entry_id,
                job_id=job_id,
                activity=activity,
                start_time=datetime.now().astimezone().isoformat(),
            )
            time_log.active_entry = entry
            self.save_time_log(time_log, job_dir)
        return entry

    def stop_timer(
        self,
        job_dir: Path,
        job_id: str,
        note: str = "",
    ) -> TimeEntry:
        """Stop current active work session and record elapsed duration."""
        with storage_lock(job_dir / "work" / ".time-log.lock"):
            time_log = self.get_time_log(job_dir, job_id)

            if not time_log.active_entry:
                raise ValueError(f"No active timer running for job {job_id}.")

            entry = time_log.active_entry
            end_dt = datetime.now().astimezone()
            entry.end_time = end_dt.isoformat()

            try:
                start_dt = datetime.fromisoformat(entry.start_time)
                duration_secs = max(0.0, (end_dt - start_dt).total_seconds())
                entry.duration_minutes = round(duration_secs / 60.0, 2)
            except (ValueError, TypeError):
                entry.duration_minutes = 0.0

            if note:
                entry.note = note

            time_log.entries.append(entry)
            time_log.active_entry = None
            self.save_time_log(time_log, job_dir)
        return entry


WorkTimer = TimeTracker
