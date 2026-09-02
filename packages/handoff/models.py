"""Data models for Quality Gate checks, validation reports, and handoff packages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class CheckStatus(StrEnum):
    """Status of an individual quality check."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class GateStatus(StrEnum):
    """Overall status of the Final Quality Gate."""

    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    BLOCKED = "BLOCKED"


@dataclass
class QualityCheckResult:
    """Outcome of a single quality gate check."""

    category: str
    name: str
    status: str = CheckStatus.PASS.value
    details: str = ""
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QualityGateReport:
    """Aggregated final quality gate validation report."""

    job_id: str
    project_path: str
    overall_status: str = GateStatus.PASS.value
    checks: list[QualityCheckResult] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    @property
    def can_deliver(self) -> bool:
        """Return True if project is not BLOCKED."""
        return self.overall_status != GateStatus.BLOCKED.value

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_path": self.project_path,
            "overall_status": self.overall_status,
            "can_deliver": self.can_deliver,
            "checks": [c.to_dict() for c in self.checks],
            "timestamp": self.timestamp,
        }

    def summary(self) -> str:
        """Render human-friendly console output."""
        lines: list[str] = [
            f"FINAL QUALITY GATE REPORT — {self.job_id}",
            f"Project:  {self.project_path}",
            f"Time:     {self.timestamp}",
            "",
            f"{'CHECK':<28} {'STATUS':<10} {'DETAILS'}",
            "─" * 75,
        ]
        for c in self.checks:
            lines.append(f"{c.name:<28} {c.status:<10} {c.details}")

        lines.append("─" * 75)
        lines.append(f"OVERALL QUALITY GATE STATUS: {self.overall_status}")

        # List problems if any
        all_issues = [
            (c.name, issue) for c in self.checks for issue in c.issues
        ]
        all_warnings = [
            (c.name, warn) for c in self.checks for warn in c.warnings
        ]

        if all_issues:
            lines.append("")
            lines.append("Critical Blockers (must fix before handoff):")
            for name, issue in all_issues:
                lines.append(f"  ✗ [{name}] {issue}")

        if all_warnings:
            lines.append("")
            lines.append("Warnings (review recommended):")
            for name, warn in all_warnings:
                lines.append(f"  ⚠ [{name}] {warn}")

        return "\n".join(lines)


@dataclass
class HandoffPackage:
    """Artifacts created in the handoff delivery package."""

    job_id: str
    output_dir: str
    created_files: list[str] = field(default_factory=list)
    archive_path: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"HANDOFF PACKAGE — {self.job_id}",
            f"Directory: {self.output_dir}",
            f"Files created ({len(self.created_files)}):",
        ]
        for f in self.created_files:
            lines.append(f"  • {f}")
        if self.archive_path:
            lines.append(f"Release Archive: {self.archive_path}")
        return "\n".join(lines)
