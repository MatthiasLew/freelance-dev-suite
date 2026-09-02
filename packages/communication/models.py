"""Data models and templates for client communications."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class MessageStage(StrEnum):
    """Lifecycle stages for client messages."""

    INTAKE = "intake"
    QUOTE = "quote"
    UPDATE = "update"
    DEMO = "demo"
    DELIVERY = "delivery"
    REMINDER = "reminder"
    SCOPE_NOTICE = "scope-notice"


@dataclass
class ClientMessage:
    """Structured communication message for a client."""

    job_id: str
    client_name: str
    stage: str
    subject: str
    body: str
    language: str = "pl"
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClientMessage:
        return cls(
            job_id=str(data["job_id"]),
            client_name=str(data.get("client_name", "")),
            stage=str(data.get("stage", MessageStage.UPDATE.value)),
            subject=str(data.get("subject", "")),
            body=str(data.get("body", "")),
            language=str(data.get("language", "pl")),
            created_at=str(data.get("created_at", datetime.now().astimezone().isoformat())),
        )

    def to_markdown(self) -> str:
        """Render complete email/message formatted for sending."""
        if self.language == "pl":
            subj_label = f"**Temat:** {self.subject}"
            to_label = f"**Do:** {self.client_name}"
            proj_label = f"**Projekt:** `{self.job_id}`"
        else:
            subj_label = f"**Subject:** {self.subject}"
            to_label = f"**To:** {self.client_name}"
            proj_label = f"**Project:** `{self.job_id}`"
        lines = [
            subj_label,
            to_label,
            proj_label,
            "",
            "---",
            "",
            self.body,
        ]
        return "\n".join(lines)
