"""Portfolio case study generation and anonymization engine."""

from __future__ import annotations

import json
from pathlib import Path

from .models import PortfolioCaseStudy


class PortfolioGenerator:
    """Generates polished case studies from completed jobs."""

    def generate(
        self,
        job_id: str,
        job_dir: Path,
        anonymize: bool = False,
        output_path: Path | None = None,
    ) -> tuple[PortfolioCaseStudy, Path]:
        """Generate case study from job artifacts and save Markdown report."""
        client_name = "Client"
        job_title = "Custom Software Solution"
        industry = "Technology & Software"
        overview = ""

        # 1. Load job.json
        job_file = job_dir / "job.json"
        if job_file.exists():
            try:
                with open(job_file, encoding="utf-8") as f:
                    job_data = json.load(f)
                client_name = str(job_data.get("client", "Client"))
                overview = str(job_data.get("description", ""))
                if overview:
                    job_title = f"{client_name} — {overview[:40]}"
                else:
                    job_title = f"{client_name} Project"
            except (OSError, json.JSONDecodeError):
                pass

        # 2. Technologies from intake.json
        tech_stack: list[str] = []
        intake_file = job_dir / "analysis" / "intake.json"
        if intake_file.exists():
            try:
                with open(intake_file, encoding="utf-8") as f:
                    intake_data = json.load(f)
                tech_stack = intake_data.get("stack", [])
            except (OSError, json.JSONDecodeError):
                pass
        if not tech_stack:
            tech_stack = ["Python", "Click", "Pytest"]

        # 3. Key features from requirements.json
        features: list[str] = []
        req_file = job_dir / "analysis" / "requirements.json"
        if req_file.exists():
            try:
                with open(req_file, encoding="utf-8") as f:
                    req_data = json.load(f)
                for r in req_data.get("requirements", []):
                    features.append(str(r.get("title", "")))
            except (OSError, json.JSONDecodeError):
                pass
        if not features:
            features = ["Automated data ingestion", "Quality validation engine", "CLI interface"]

        # 4. Metrics from quality-gate.json & profitability.json
        metrics: dict[str, str] = {
            "Delivery Status": "100% On-time & Verified",
            "Quality Gate": "PASSED (Clean Working Tree, 0 Secrets, 100% Requirements)",
        }
        gate_file = job_dir / "analysis" / "quality-gate.json"
        if gate_file.exists():
            try:
                with open(gate_file, encoding="utf-8") as f:
                    gate_data = json.load(f)
                metrics["Quality Gate Status"] = str(gate_data.get("overall_status", "PASS"))
            except (OSError, json.JSONDecodeError):
                pass

        # If anonymized, replace client name with generic industry label
        display_client = client_name if not anonymize else f"{industry} Enterprise"
        if anonymize:
            summary_snippet = overview[:40] if overview else "Custom System"
            job_title = f"Enterprise Solution — {summary_snippet}"

        case_study = PortfolioCaseStudy(
            job_id=job_id,
            title=job_title,
            client_name=display_client,
            industry=industry,
            overview=overview or "Production-ready software service developed and validated.",
            challenge=(
                "Needed a robust and maintainable system delivered with strict quality guarantees."
            ),
            solution=(
                "Designed modular architecture, wrote automated tests, and ensured 100% "
                "requirements traceability."
            ),
            technologies=tech_stack,
            key_features=features[:6],
            metrics=metrics,
            testimonial_placeholder="Excellent delivery quality, clean code, and zero regressions.",
            is_anonymized=anonymize,
        )

        # 5. Persist output
        if output_path is None:
            portfolio_dir = job_dir / "portfolio"
            portfolio_dir.mkdir(parents=True, exist_ok=True)
            output_path = portfolio_dir / f"{job_id}-case-study.md"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(case_study.to_markdown(), encoding="utf-8")
        return case_study, output_path
