"""Append-only business event log for freelance jobs."""

from __future__ import annotations

import json
import re
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


_EVT_ID_PATTERN = re.compile(r"^EVT-(\d+)$")


def _get_last_event_number(history_path: Path) -> int:
    """Extract the highest event number from history file.

    Fast path: reads the tail chunk of the file (8KB) and parses the last non-empty line.
    Fallback: scans the full file if the tail is corrupted, unparseable, or empty.
    Never reuses existing event IDs even across gaps or corrupted trailing entries.
    """
    if not history_path.exists():
        return 0
    try:
        size = history_path.stat().st_size
        if size == 0:
            return 0
        read_size = min(size, 8192)
        with open(history_path, "rb") as f:
            f.seek(size - read_size)
            chunk = f.read(read_size)
        lines = chunk.decode("utf-8", errors="replace").splitlines()
        non_empty = [line.strip() for line in lines if line.strip()]
        if non_empty:
            last_line = non_empty[-1]
            try:
                data = json.loads(last_line)
                if isinstance(data, dict) and "event_id" in data:
                    m = _EVT_ID_PATTERN.match(str(data["event_id"]))
                    if m:
                        return int(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        # Fallback if tail chunk did not have full event or was corrupted: scan lines
        max_seen = 0
        line_count = 0
        with open(history_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                clean = line.strip()
                if clean:
                    line_count += 1
                    try:
                        data = json.loads(clean)
                        if isinstance(data, dict) and "event_id" in data:
                            m = _EVT_ID_PATTERN.match(str(data["event_id"]))
                            if m:
                                max_seen = max(max_seen, int(m.group(1)))
                    except Exception:
                        pass
        return max_seen if max_seen > 0 else line_count
    except OSError:
        return 0


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
            next_num = _get_last_event_number(history_path) + 1
            event_id = f"EVT-{next_num:04d}"
            event = BusinessEvent(
                event_id=event_id,
                job_id=job_id,
                event_type=event_type,
                related_id=related_id,
                status=status,
                metadata=metadata or {},
            )
            event_data = mask_text(json.dumps(event.to_dict(), ensure_ascii=False)) + "\n"

            # Prepend newline if existing history file lacked trailing newline
            prefix = ""
            if history_path.exists() and history_path.stat().st_size > 0:
                with open(history_path, "rb") as f:
                    f.seek(history_path.stat().st_size - 1)
                    if f.read(1) not in (b"\n", b"\r"):
                        prefix = "\n"

            with open(history_path, "a", encoding="utf-8") as f:
                f.write(prefix + event_data)

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
