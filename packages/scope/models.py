"""Data models for scope change detection, cost estimation, and client proposals."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ScopeClassification(StrEnum):
    """Classification of a requested feature or change against baseline scope."""

    IN_SCOPE = "IN_SCOPE"
    MINOR_EXTENSION = "MINOR_EXTENSION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    BREAKING_CHANGE = "BREAKING_CHANGE"


@dataclass
class ScopeChangeItem:
    """Analysis result for a scope change request."""

    id: str
    job_id: str
    requested_text: str
    classification: str = ScopeClassification.OUT_OF_SCOPE.value
    matched_existing_requirements: list[str] = field(default_factory=list)
    new_functionalities: list[str] = field(default_factory=list)
    estimated_additional_hours: float = 0.0
    estimated_ai_cost_pln: float = 0.0
    suggested_extra_price_pln: float = 0.0
    impact_assessment: str = ""
    client_proposal_message: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopeChangeItem:
        return cls(
            id=data["id"],
            job_id=data["job_id"],
            requested_text=data.get("requested_text", ""),
            classification=data.get("classification", ScopeClassification.OUT_OF_SCOPE.value),
            matched_existing_requirements=data.get("matched_existing_requirements", []),
            new_functionalities=data.get("new_functionalities", []),
            estimated_additional_hours=float(data.get("estimated_additional_hours", 0.0)),
            estimated_ai_cost_pln=float(data.get("estimated_ai_cost_pln", 0.0)),
            suggested_extra_price_pln=float(data.get("suggested_extra_price_pln", 0.0)),
            impact_assessment=data.get("impact_assessment", ""),
            client_proposal_message=data.get("client_proposal_message", ""),
            created_at=data.get("created_at", datetime.now().astimezone().isoformat()),
        )

    def to_markdown(self) -> str:
        """Render detailed technical scope analysis."""
        lines = [
            f"# Scope Change Analysis: {self.id}",
            "",
            f"**Job:** `{self.job_id}`  ",
            f"**Classification:** `{self.classification}`  ",
            f"**Estimated Additional Hours:** `{self.estimated_additional_hours:.1f}h`  ",
            f"**Estimated AI Cost:** `{self.estimated_ai_cost_pln:.2f} PLN`  ",
            f"**Suggested Surcharge:** `{self.suggested_extra_price_pln:.0f} PLN`  ",
            f"**Date:** {self.created_at}  ",
            "",
            "## Client Request",
            f"> {self.requested_text.strip()}",
            "",
            "## Impact Assessment",
            self.impact_assessment or "No impact notes recorded.",
            "",
        ]

        if self.matched_existing_requirements:
            lines.extend([
                "## Matched Existing Scope",
                *[f"- {m}" for m in self.matched_existing_requirements],
                "",
            ])

        if self.new_functionalities:
            lines.extend([
                "## Identified New Functionalities (Out of Scope)",
                *[f"- {f}" for f in self.new_functionalities],
                "",
            ])

        return "\n".join(lines)

    def to_proposal_markdown(self) -> str:
        """Render client-ready price proposal / change order message."""
        return self.client_proposal_message

    def summary(self) -> str:
        lines = [
            f"SCOPE ANALYSIS — {self.id}",
            f"Classification:     {self.classification}",
            f"Additional Hours:   {self.estimated_additional_hours:.1f}h",
            f"Estimated AI Cost:  ~{self.estimated_ai_cost_pln:.2f} PLN",
            f"Suggested Surcharge: {self.suggested_extra_price_pln:.0f} PLN",
        ]
        if self.new_functionalities:
            lines.append(f"New features ({len(self.new_functionalities)}):")
            for f in self.new_functionalities[:3]:
                lines.append(f"  • {f}")
        return "\n".join(lines)
