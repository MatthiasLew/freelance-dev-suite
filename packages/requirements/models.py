"""Data models for requirements and acceptance checklist specifications."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class RequirementApprovalState(StrEnum):
    """Approval lifecycle states of job requirements."""

    DRAFT = "DRAFT"
    CLIENT_CONFIRMED = "CLIENT_CONFIRMED"
    CHANGED = "CHANGED"


@dataclass
class RequirementItem:
    """A specific functional or technical requirement item."""

    id: str
    title: str
    section: str = "General"
    completed: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequirementItem:
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            section=str(data.get("section", "General")),
            completed=bool(data.get("completed", False)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class AcceptanceCriterion:
    """An acceptance criterion verifiable at delivery."""

    id: str
    criterion: str
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceCriterion:
        return cls(
            id=str(data.get("id", "")),
            criterion=str(data.get("criterion", "")),
            completed=bool(data.get("completed", False)),
        )


@dataclass
class RequirementsSpec:
    """Full requirements and checklist specification for a freelance job."""

    job_id: str
    title: str
    approval_state: str = RequirementApprovalState.DRAFT.value
    requirements: list[RequirementItem] = field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    unresolved_decisions: list[str] = field(default_factory=list)
    confirmed_at: str | None = None
    confirmed_by: str | None = None
    version: int = 1
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert specification to structured dictionary."""
        return {
            "job_id": self.job_id,
            "title": self.title,
            "approval_state": self.approval_state,
            "requirements": [r.to_dict() for r in self.requirements],
            "acceptance_criteria": [ac.to_dict() for ac in self.acceptance_criteria],
            "assumptions": list(self.assumptions),
            "out_of_scope": list(self.out_of_scope),
            "questions": list(self.questions),
            "unresolved_decisions": list(self.unresolved_decisions),
            "confirmed_at": self.confirmed_at,
            "confirmed_by": self.confirmed_by,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequirementsSpec:
        """Construct specification from dictionary."""
        requirements = [
            RequirementItem.from_dict(item) if isinstance(item, dict) else item
            for item in data.get("requirements", [])
        ]
        acceptance_criteria = [
            AcceptanceCriterion.from_dict(item) if isinstance(item, dict) else item
            for item in data.get("acceptance_criteria", [])
        ]
        return cls(
            job_id=str(data.get("job_id", "")),
            title=str(data.get("title", "")),
            approval_state=str(
                data.get("approval_state", RequirementApprovalState.DRAFT.value)
            ),
            requirements=requirements,
            acceptance_criteria=acceptance_criteria,
            assumptions=[str(x) for x in data.get("assumptions", [])],
            out_of_scope=[str(x) for x in data.get("out_of_scope", [])],
            questions=[str(x) for x in data.get("questions", [])],
            unresolved_decisions=[str(x) for x in data.get("unresolved_decisions", [])],
            confirmed_at=data.get("confirmed_at"),
            confirmed_by=data.get("confirmed_by"),
            version=int(data.get("version", 1)),
            created_at=str(
                data.get("created_at") or datetime.now().astimezone().isoformat()
            ),
            updated_at=str(
                data.get("updated_at") or datetime.now().astimezone().isoformat()
            ),
        )

    def confirm(self, confirmed_by: str = "client") -> None:
        """Mark requirements as confirmed by client."""
        self.approval_state = RequirementApprovalState.CLIENT_CONFIRMED.value
        self.confirmed_at = datetime.now().astimezone().isoformat()
        self.confirmed_by = confirmed_by
        self.updated_at = datetime.now().astimezone().isoformat()

    def mark_changed(self, note: str = "") -> None:
        """Mark requirements as changed after initial confirmation or draft update."""
        self.approval_state = RequirementApprovalState.CHANGED.value
        self.version += 1
        self.updated_at = datetime.now().astimezone().isoformat()
        if note:
            self.unresolved_decisions.append(f"Change (v{self.version}): {note}")

    @property
    def progress(self) -> tuple[int, int, float]:
        """Return (completed_items, total_items, percentage_completed)."""
        all_items = [r.completed for r in self.requirements] + [
            ac.completed for ac in self.acceptance_criteria
        ]
        if not all_items:
            return 0, 0, 0.0
        completed = sum(1 for done in all_items if done)
        total = len(all_items)
        percent = (completed / total) * 100.0
        return completed, total, round(percent, 1)

    def toggle_item(self, target_id: str, completed: bool | None = None) -> bool:
        """Find requirement or acceptance criterion by id or index and update completed status.

        Returns True if an item was found and updated, False otherwise.
        """
        clean_target = target_id.strip().lower()

        # Try matching requirement by id
        for item in self.requirements:
            if item.id.lower() == clean_target:
                item.completed = not item.completed if completed is None else completed
                self.updated_at = datetime.now().astimezone().isoformat()
                return True

        # Try matching acceptance criterion by id
        for ac in self.acceptance_criteria:
            if ac.id.lower() == clean_target:
                ac.completed = not ac.completed if completed is None else completed
                self.updated_at = datetime.now().astimezone().isoformat()
                return True

        # Try numeric index (1-based across combined items)
        if clean_target.isdigit():
            idx = int(clean_target) - 1
            if 0 <= idx < len(self.requirements):
                target_req = self.requirements[idx]
                target_req.completed = (
                    not target_req.completed if completed is None else completed
                )
                self.updated_at = datetime.now().astimezone().isoformat()
                return True
            ac_idx = idx - len(self.requirements)
            if 0 <= ac_idx < len(self.acceptance_criteria):
                target_ac = self.acceptance_criteria[ac_idx]
                target_ac.completed = (
                    not target_ac.completed if completed is None else completed
                )
                self.updated_at = datetime.now().astimezone().isoformat()
                return True

        return False

    def sections(self) -> dict[str, list[RequirementItem]]:
        """Group requirements by section name."""
        grouped: dict[str, list[RequirementItem]] = {}
        for item in self.requirements:
            grouped.setdefault(item.section, []).append(item)
        return grouped

    def to_markdown(self) -> str:
        """Render full requirements document in markdown."""
        lines: list[str] = [
            f"# Requirements — {self.job_id}: {self.title}",
            "",
            f"**Status:** `{self.approval_state}`",
            f"**Version:** {self.version}",
            f"**Created:** {self.created_at}",
            f"**Last Updated:** {self.updated_at}",
        ]
        if self.confirmed_at:
            lines.append(f"**Confirmed:** {self.confirmed_at} by {self.confirmed_by or 'client'}")
        lines.append("")

        done, total, pct = self.progress
        lines.append(f"**Checklist Progress:** {done}/{total} items completed ({pct:.1f}%)")
        lines.append("")

        lines.append("## Requirements")
        grouped = self.sections()
        if not grouped:
            lines.append("_No requirements defined yet._")
            lines.append("")
        else:
            for section, items in grouped.items():
                lines.append(f"### {section}")
                for req in items:
                    box = "[x]" if req.completed else "[ ]"
                    note_suffix = f" _({req.notes})_" if req.notes else ""
                    lines.append(f"- {box} `{req.id}`: {req.title}{note_suffix}")
                lines.append("")

        lines.append("## Acceptance Criteria")
        if not self.acceptance_criteria:
            lines.append("_No acceptance criteria defined._")
            lines.append("")
        else:
            for ac in self.acceptance_criteria:
                box = "[x]" if ac.completed else "[ ]"
                lines.append(f"- {box} `{ac.id}`: {ac.criterion}")
            lines.append("")

        if self.assumptions:
            lines.append("## Assumptions")
            for item in self.assumptions:
                lines.append(f"- {item}")
            lines.append("")

        if self.out_of_scope:
            lines.append("## Out of Scope")
            for item in self.out_of_scope:
                lines.append(f"- {item}")
            lines.append("")

        if self.questions:
            lines.append("## Questions for Client")
            for item in self.questions:
                lines.append(f"- [ ] {item}")
            lines.append("")

        if self.unresolved_decisions:
            lines.append("## Unresolved Decisions")
            for item in self.unresolved_decisions:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines).strip() + "\n"

    def to_checklist_markdown(self) -> str:
        """Render actionable working checklist for developer work tracking."""
        done, total, pct = self.progress
        lines: list[str] = [
            f"# Work Checklist — {self.job_id}: {self.title}",
            "",
            f"**Status:** `{self.approval_state}` | **Progress:** {done}/{total} ({pct:.1f}%)",
            "",
            "## Implementation Tasks",
        ]
        grouped = self.sections()
        if not grouped:
            lines.append("- [ ] Initial implementation setup")
        else:
            for section, items in grouped.items():
                lines.append(f"### {section}")
                for req in items:
                    box = "[x]" if req.completed else "[ ]"
                    lines.append(f"- {box} [{req.id}] {req.title}")
                lines.append("")

        lines.append("## Acceptance Verification")
        if not self.acceptance_criteria:
            lines.append("- [ ] Verify all requirements against client expectations")
        else:
            for ac in self.acceptance_criteria:
                box = "[x]" if ac.completed else "[ ]"
                lines.append(f"- {box} [{ac.id}] {ac.criterion}")

        lines.append("")
        return "\n".join(lines).strip() + "\n"

    def summary(self) -> str:
        """Render human-friendly console summary."""
        done, total, pct = self.progress
        conf_str = (
            f"Confirmed: {self.confirmed_at} ({self.confirmed_by})"
            if self.confirmed_at
            else "Not confirmed by client"
        )
        lines: list[str] = [
            f"Job ID:          {self.job_id}",
            f"Title:           {self.title}",
            f"Approval State:  {self.approval_state}",
            f"Version:         v{self.version}",
            f"Progress:        {done}/{total} ({pct:.1f}%)",
            f"Confirmation:    {conf_str}",
            "",
            f"Requirements:    {len(self.requirements)} items",
        ]
        for section, items in self.sections().items():
            done_sec = sum(1 for i in items if i.completed)
            lines.append(f"  • {section}: {done_sec}/{len(items)} done")

        lines.append(f"Acceptance:      {len(self.acceptance_criteria)} criteria")
        if self.assumptions:
            lines.append(f"Assumptions:     {len(self.assumptions)} listed")
        if self.out_of_scope:
            lines.append(f"Out of Scope:    {len(self.out_of_scope)} items")
        if self.questions:
            lines.append(f"Client Questions:{len(self.questions)} pending")
        if self.unresolved_decisions:
            lines.append(f"Decisions:       {len(self.unresolved_decisions)} open")

        return "\n".join(lines)
