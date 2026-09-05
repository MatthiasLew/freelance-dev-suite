"""Persistent models for development work sessions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class WorkStatus(StrEnum):
    """Lifecycle of a concrete development task."""

    ACTIVE = "ACTIVE"
    VERIFIED = "VERIFIED"
    NEEDS_FIX = "NEEDS_FIX"


@dataclass
class WorkSession:
    """One resumable unit of development work for a freelance job."""

    id: str
    job_id: str
    task: str
    repository: str
    agent: str = "generic"
    model: str = ""
    status: str = WorkStatus.ACTIVE.value
    related_requirements: list[str] = field(default_factory=list)
    scope_classification: str = ""
    scope_change_id: str | None = None
    timer_entry_ids: list[str] = field(default_factory=list)
    duration_minutes: float = 0.0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    ai_costs: dict[str, float] = field(default_factory=dict)
    ai_cost_pln: float = 0.0
    validation_status: str = "not_run"
    validation_summary: dict[str, Any] = field(default_factory=dict)
    context_fingerprint: str | None = None
    telemetry_baseline: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkSession:
        """Load a session while accepting files from earlier schema revisions."""
        return cls(
            id=str(data["id"]),
            job_id=str(data["job_id"]),
            task=str(data.get("task", "")),
            repository=str(data.get("repository", "")),
            agent=str(data.get("agent", "generic")),
            model=str(data.get("model", "")),
            status=str(data.get("status", WorkStatus.ACTIVE.value)),
            related_requirements=[str(item) for item in data.get("related_requirements", [])],
            scope_classification=str(data.get("scope_classification", "")),
            scope_change_id=data.get("scope_change_id"),
            timer_entry_ids=[str(item) for item in data.get("timer_entry_ids", [])],
            duration_minutes=float(data.get("duration_minutes", 0.0)),
            input_tokens=int(data.get("input_tokens", 0)),
            cached_input_tokens=int(data.get("cached_input_tokens", 0)),
            cache_write_input_tokens=int(data.get("cache_write_input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            reasoning_tokens=int(data.get("reasoning_tokens", 0)),
            total_tokens=int(data.get("total_tokens", 0)),
            ai_costs={
                str(key): float(value) for key, value in data.get("ai_costs", {}).items()
            },
            ai_cost_pln=float(data.get("ai_cost_pln", 0.0)),
            validation_status=str(data.get("validation_status", "not_run")),
            validation_summary=dict(data.get("validation_summary", {})),
            context_fingerprint=data.get("context_fingerprint"),
            telemetry_baseline=dict(data.get("telemetry_baseline", {})),
            started_at=str(data.get("started_at", "")),
            updated_at=str(data.get("updated_at", "")),
            finished_at=data.get("finished_at"),
        )
