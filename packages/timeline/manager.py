"""Append-only business event log for freelance jobs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from packages.security.secrets import mask_text
from packages.storage_utils import storage_lock


@dataclass(slots=True)
class BusinessEvent:
    """An immutable business audit event for a freelance job."""

    event_id: str
    job_id: str
    event_type: str
    timestamp: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    related_id: str | None = None
    status: str = "SUCCESS"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BusinessEvent:
        return cls(
            event_id=str(data["event_id"]),
            job_id=str(data["job_id"]),
            event_type=str(data["event_type"]),
            timestamp=str(data.get("timestamp", "")),
            related_id=data.get("related_id"),
            status=str(data.get("status", "SUCCESS")),
            metadata=dict(data.get("metadata", {})),
        )


class TimelineManager:
    """Manages append-only JSONL event history for jobs."""

    def history_file(self, job_dir: Path) -> Path:
        return job_dir / "history" / "events.jsonl"

    def record_event(
        self,
        job_dir: Path,
        job_id: str,
        event_type: str,
        related_id: str | None = None,
        status: str = "SUCCESS",
        metadata: dict[str, Any] | None = None,
    ) -> BusinessEvent:
        """Atomically append an event to the job's business timeline."""
        history_path = self.history_file(job_dir)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = history_path.parent / ".timeline.lock"

        with storage_lock(lock_path):
            existing = self.list_events(job_dir)
            event_id = f"EVT-{len(existing) + 1:04d}"
            event = BusinessEvent(
                event_id=event_id,
                job_id=job_id,
                event_type=event_type,
                related_id=related_id,
                status=status,
                metadata=metadata or {},
            )
            line = mask_text(json.dumps(event.to_dict(), ensure_ascii=False)) + "\n"
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(line)

        return event

    def list_events(self, job_dir: Path) -> list[BusinessEvent]:
        """Read and parse all events from the history file in chronological order."""
        history_path = self.history_file(job_dir)
        if not history_path.exists():
            return []

        events: list[BusinessEvent] = []
        try:
            with open(history_path, encoding="utf-8") as f:
                for line in f:
                    line_clean = line.strip()
                    if not line_clean:
                        continue
                    try:
                        data = json.loads(line_clean)
                        if isinstance(data, dict):
                            events.append(BusinessEvent.from_dict(data))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except OSError:
            return []

        return events
