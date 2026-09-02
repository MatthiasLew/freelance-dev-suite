"""Data models for portfolio case studies and project showcases."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PortfolioCaseStudy:
    """Structured case study for client projects and public portfolio."""

    job_id: str
    title: str
    client_name: str
    industry: str
    overview: str
    challenge: str
    solution: str
    technologies: list[str] = field(default_factory=list)
    key_features: list[str] = field(default_factory=list)
    metrics: dict[str, str] = field(default_factory=dict)
    testimonial_placeholder: str = ""
    is_anonymized: bool = False
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PortfolioCaseStudy:
        return cls(
            job_id=str(data["job_id"]),
            title=str(data.get("title", "")),
            client_name=str(data.get("client_name", "")),
            industry=str(data.get("industry", "Technology")),
            overview=str(data.get("overview", "")),
            challenge=str(data.get("challenge", "")),
            solution=str(data.get("solution", "")),
            technologies=list(data.get("technologies", [])),
            key_features=list(data.get("key_features", [])),
            metrics=dict(data.get("metrics", {})),
            testimonial_placeholder=str(data.get("testimonial_placeholder", "")),
            is_anonymized=bool(data.get("is_anonymized", False)),
            created_at=str(data.get("created_at", datetime.now().astimezone().isoformat())),
        )

    def to_markdown(self) -> str:
        """Render case study in professional Markdown format."""
        if not self.is_anonymized:
            client_label = self.client_name
        else:
            client_label = f"Confidential Client ({self.industry})"
        lines = [
            f"# Case Study: {self.title}",
            "",
            f"**Client:** {client_label}  ",
            f"**Industry:** {self.industry}  ",
            f"**Project ID:** `{self.job_id}`  ",
            f"**Date:** {self.created_at[:10]}  ",
            "",
            "## 1. Project Overview",
            self.overview or "Custom software development solution tailored for client needs.",
            "",
            "## 2. Business Challenge & Requirements",
            self.challenge or (
                "The client required a robust, maintainable solution to streamline workflows."
            ),
            "",
            "## 3. Solution & Architecture",
            self.solution or (
                "Engineered a high-performance system adhering to modern development practices."
            ),
            "",
        ]

        if self.technologies:
            lines.extend([
                "## 4. Tech Stack",
                ", ".join(f"`{t}`" for t in self.technologies),
                "",
            ])

        if self.key_features:
            lines.extend([
                "## 5. Key Delivered Features",
                *[f"- **{f}**" for f in self.key_features],
                "",
            ])

        if self.metrics:
            lines.extend([
                "## 6. Key Metrics & Outcomes",
                *[f"- **{k}:** {v}" for k, v in self.metrics.items()],
                "",
            ])

        if self.testimonial_placeholder:
            lines.extend([
                "## 7. Client Feedback",
                f'> "{self.testimonial_placeholder}"',
                "",
            ])

        return "\n".join(lines)
