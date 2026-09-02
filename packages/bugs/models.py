"""Data models for bug tracking, reproduction scripts, and client questions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class BugStatus(StrEnum):
    """Lifecycle status of a reported bug."""

    REPORTED = "REPORTED"
    NEEDS_INFO = "NEEDS_INFO"
    REPRODUCED = "REPRODUCED"
    FIX_IN_PROGRESS = "FIX_IN_PROGRESS"
    FIXED = "FIXED"
    REGRESSION_TESTED = "REGRESSION_TESTED"
    CLOSED = "CLOSED"


class BugSeverity(StrEnum):
    """Severity classification for bug impact."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class BugReport:
    """Structured bug report model."""

    id: str
    job_id: str
    title: str
    raw_description: str
    status: str = BugStatus.REPORTED.value
    severity: str = BugSeverity.MEDIUM.value
    steps_to_reproduce: list[str] = field(default_factory=list)
    expected_behavior: str = ""
    actual_behavior: str = ""
    environment: dict[str, str] = field(default_factory=dict)
    error_logs: str = ""
    questions_for_client: list[str] = field(default_factory=list)
    regression_test_file: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def change_status(self, new_status: str, note: str = "") -> None:
        """Update lifecycle status and refresh timestamp."""
        clean = new_status.strip().upper()
        valid = {s.value for s in BugStatus}
        if clean not in valid:
            valid_list = ", ".join(sorted(valid))
            raise ValueError(f"Invalid bug status '{new_status}'. Valid: {valid_list}")
        self.status = clean
        self.updated_at = datetime.now().astimezone().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BugReport:
        return cls(
            id=data["id"],
            job_id=data["job_id"],
            title=data.get("title", ""),
            raw_description=data.get("raw_description", ""),
            status=data.get("status", BugStatus.REPORTED.value),
            severity=data.get("severity", BugSeverity.MEDIUM.value),
            steps_to_reproduce=data.get("steps_to_reproduce", []),
            expected_behavior=data.get("expected_behavior", ""),
            actual_behavior=data.get("actual_behavior", ""),
            environment=data.get("environment", {}),
            error_logs=data.get("error_logs", ""),
            questions_for_client=data.get("questions_for_client", []),
            regression_test_file=data.get("regression_test_file"),
            created_at=data.get("created_at", datetime.now().astimezone().isoformat()),
            updated_at=data.get("updated_at", datetime.now().astimezone().isoformat()),
        )

    def to_markdown(self) -> str:
        """Render technical bug summary document."""
        lines = [
            f"# Bug Report: {self.id} — {self.title}",
            "",
            f"**Job:** `{self.job_id}`  ",
            f"**Status:** `{self.status}`  ",
            f"**Severity:** `{self.severity}`  ",
            f"**Created:** {self.created_at}  ",
            f"**Last Updated:** {self.updated_at}  ",
            "",
            "## Description from Client",
            f"> {self.raw_description.strip() or 'No description provided.'}",
            "",
            "## Steps to Reproduce",
        ]
        if self.steps_to_reproduce:
            for idx, step in enumerate(self.steps_to_reproduce, start=1):
                lines.append(f"{idx}. {step}")
        else:
            lines.append("*Steps not fully identified yet.*")

        lines.extend([
            "",
            "## Behavior",
            f"- **Expected:** {self.expected_behavior or 'Not specified'}",
            f"- **Actual:** {self.actual_behavior or 'Not specified'}",
        ])

        if self.environment:
            lines.extend(["", "## Environment"])
            for k, v in self.environment.items():
                lines.append(f"- **{k}:** {v}")

        if self.error_logs:
            lines.extend([
                "",
                "## Error Logs & Traceback",
                "```text",
                self.error_logs.strip(),
                "```",
            ])

        if self.regression_test_file:
            lines.extend([
                "",
                "## Regression Test",
                f"- Linked test: `{self.regression_test_file}`",
            ])

        lines.append("")
        return "\n".join(lines)

    def to_questions_markdown(self) -> str:
        """Render client-ready clarifying questions message."""
        if not self.questions_for_client:
            return f"# Clarifications for {self.id}\n\nNo outstanding questions for the client.\n"

        lines = [
            f"# Questions for Client — {self.id}: {self.title}",
            "",
            "Hi! To quickly investigate and fix the reported issue, "
            "please provide a few more details:",
            "",
        ]
        for q in self.questions_for_client:
            lines.append(f"- [ ] {q}")
        lines.extend([
            "",
            "Thank you! Once we have this information, "
            "we will reproduce and fix the issue immediately.",
            "",
        ])
        return "\n".join(lines)

    def to_repro_script(self, language: str = "python") -> str:
        """Generate standalone reproduction script skeleton."""
        if language.lower() in {"c#", "csharp"}:
            return f"""// Reproduction script for {self.id}: {self.title}
using System;

namespace BugReproduction
{{
    class Program
    {{
        static void Main(string[] args)
        {{
            Console.WriteLine("Reproducing {self.id}...");
            // TODO: Add reproduction code steps here
        }}
    }}
}}
"""

        # Python default
        return f'''"""Reproduction script for {self.id}: {self.title}"""

from __future__ import annotations

import sys


def reproduce() -> int:
    print("Executing reproduction for {self.id}...")
    # TODO: Add steps to trigger bug: {self.title}
    print("Expected: {self.expected_behavior or 'Success'}")
    print("Actual: {self.actual_behavior or 'Error'}")
    return 1  # Exit 1 if bug occurs


if __name__ == "__main__":
    sys.exit(reproduce())
'''

    def summary(self) -> str:
        lines = [
            f"{self.id} [{self.status}] ({self.severity}) — {self.title}",
            f"  Job: {self.job_id}",
            f"  Expected: {self.expected_behavior or 'N/A'}",
            f"  Actual:   {self.actual_behavior or 'N/A'}",
        ]
        if self.questions_for_client:
            lines.append(f"  Pending questions ({len(self.questions_for_client)}):")
            for q in self.questions_for_client[:3]:
                lines.append(f"    • {q}")
        return "\n".join(lines)
