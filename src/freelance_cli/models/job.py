"""Job model — central data structure for tracking freelance jobs."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    """Lifecycle status of a freelance job."""

    LEAD = "LEAD"
    ANALYSIS = "ANALYSIS"
    WAITING_FOR_CLIENT = "WAITING_FOR_CLIENT"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    TESTING = "TESTING"
    READY_FOR_HANDOFF = "READY_FOR_HANDOFF"
    DELIVERED = "DELIVERED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"


class JobSource(str, Enum):
    """Where the job came from."""

    USEME = "Useme"
    UPWORK = "Upwork"
    FIVERR = "Fiverr"
    DIRECT = "Direct"
    OTHER = "Other"


@dataclass
class StatusChange:
    """Record of a status transition."""

    from_status: str
    to_status: str
    timestamp: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusChange:
        return cls(**data)


@dataclass
class Job:
    """A freelance job/commission."""

    id: str
    client: str
    description: str
    source: str = JobSource.OTHER.value
    status: str = JobStatus.LEAD.value
    budget_pln: float | None = None
    deadline: str | None = None
    repository: str | None = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    status_history: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def change_status(self, new_status: str, note: str = "") -> None:
        """Transition to a new status and record the change."""
        change = StatusChange(
            from_status=self.status,
            to_status=new_status,
            timestamp=datetime.datetime.now().isoformat(),
            note=note,
        )
        self.status_history.append(change.to_dict())
        self.status = new_status
        self.updated_at = datetime.datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        """Deserialize from a plain dict."""
        return cls(**data)

    def summary_line(self) -> str:
        """One-line summary for list display."""
        budget = f"{self.budget_pln:.0f} PLN" if self.budget_pln else "—"
        deadline = self.deadline or "—"
        return (
            f"{self.id:<12} {self.status:<22} {self.client:<16} "
            f"{budget:<12} {deadline:<12} {self.description[:40]}"
        )

    @staticmethod
    def summary_header() -> str:
        """Column header for list display."""
        return (
            f"{'ID':<12} {'STATUS':<22} {'CLIENT':<16} "
            f"{'BUDGET':<12} {'DEADLINE':<12} {'DESCRIPTION'}"
        )

    def detail_view(self) -> str:
        """Multi-line detail view for status command."""
        budget = f"{self.budget_pln:.0f} PLN" if self.budget_pln else "—"
        deadline = self.deadline or "—"
        repo = self.repository or "—"
        lines = [
            f"Job:         {self.id}",
            f"Client:      {self.client}",
            f"Source:      {self.source}",
            f"Status:      {self.status}",
            f"Description: {self.description}",
            f"Budget:      {budget}",
            f"Deadline:    {deadline}",
            f"Repository:  {repo}",
            f"Created:     {self.created_at}",
            f"Updated:     {self.updated_at}",
        ]
        if self.notes:
            lines.append(f"Notes:       {self.notes}")
        if self.status_history:
            lines.append("")
            lines.append("Status History:")
            for change in self.status_history:
                note_part = f" ({change['note']})" if change.get("note") else ""
                lines.append(
                    f"  {change['timestamp'][:19]}  "
                    f"{change['from_status']} → {change['to_status']}{note_part}"
                )
        return "\n".join(lines)
