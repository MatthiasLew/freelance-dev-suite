"""Time tracking operations, active sessions, and persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import TimeEntry, TimeLog


class TimeTracker:
    """Manages recording work sessions and time logs."""

    def get_time_log(self, job_dir: Path, job_id: str) -> TimeLog:
        """Load or initialize TimeLog for a job."""
        log_path = job_dir / "work" / "time-log.json"
        if not log_path.exists():
            return TimeLog(job_id=job_id)

        try:
            with open(log_path, encoding="utf-8") as f:
                data = json.load(f)
            return TimeLog.from_dict(data)
        except (OSError, json.JSONDecodeError):
            return TimeLog(job_id=job_id)

    def save_time_log(self, time_log: TimeLog, job_dir: Path) -> Path:
        """Persist TimeLog to job work directory."""
        work_dir = job_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        log_path = work_dir / "time-log.json"
        log_path.write_text(
            json.dumps(time_log.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return log_path

    def start_timer(
        self,
        job_dir: Path,
        job_id: str,
        activity: str = "development",
    ) -> TimeEntry:
        """Start a new active timer session for a job."""
        time_log = self.get_time_log(job_dir, job_id)

        if time_log.active_entry:
            # If already running, return existing active entry
            return time_log.active_entry

        entry_id = f"SESSION-{len(time_log.entries) + 1:03d}"
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
