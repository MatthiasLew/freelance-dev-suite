from __future__ import annotations

import datetime
import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QuoteEstimate:
    """Full freelance job quote."""

    # Time breakdown
    implementation_hours: float
    testing_hours: float
    deployment_hours: float
    contingency_hours: float
    total_hours: float

    # Cost breakdown (PLN)
    human_work_pln: float
    ai_cost_pln: float
    infrastructure_pln: float
    risk_buffer_pln: float

    # Final prices
    minimum_technical_price_pln: float
    recommended_quote_min_pln: float
    recommended_quote_max_pln: float

    # Meta
    risk_level: str
    confidence_percent: int
    hourly_rate: float

    # Warnings and questions
    warnings: list[str]
    questions_for_client: list[str]

    timestamp: str = field(default_factory=lambda: datetime.datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert QuoteEstimate to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuoteEstimate:
        """Create a QuoteEstimate from a dictionary."""
        return cls(**data)

    def summary(self) -> str:
        """Return a formatted summary of the estimate."""
        summary_str = (
            f"ESTIMATE\n\n"
            f"Implementation:  {self.implementation_hours:.1f}h\n"
            f"Testing:         {self.testing_hours:.1f}h\n"
            f"Deployment:      {self.deployment_hours:.1f}h\n"
            f"Contingency:     {self.contingency_hours:.1f}h\n\n"
            f"AI:              {int(self.ai_cost_pln)} PLN\n"
            f"Infrastructure:  {int(self.infrastructure_pln)} PLN\n"
            f"Human work:      {int(self.human_work_pln)} PLN\n"
            f"Risk buffer:     {int(self.risk_buffer_pln)} PLN\n\n"
            f"Minimum technical price:  {int(self.minimum_technical_price_pln)} PLN\n"
            f"Recommended quote:        {int(self.recommended_quote_min_pln)}–"
            f"{int(self.recommended_quote_max_pln)} PLN\n"
            f"Confidence:               {self.confidence_percent}%\n\n"
            f"Warnings:\n"
        )

        if self.warnings:
            summary_str += "\n".join(f"  ⚠ {w}" for w in self.warnings) + "\n"
        else:
            summary_str += "  None\n"

        summary_str += "\nQuestions for client:\n"

        if self.questions_for_client:
            summary_str += "\n".join(f"  ? {q}" for q in self.questions_for_client) + "\n"
        else:
            summary_str += "  None\n"

        return summary_str

    def is_budget_sufficient(self, budget: float) -> bool:
        """Check if the provided budget is sufficient for the minimum technical price."""
        return budget >= self.minimum_technical_price_pln

    def effective_hourly_rate(self, actual_quote: float) -> float:
        """Calculate the effective hourly rate based on the final agreed quote."""
        if self.total_hours == 0:
            return 0.0
        return (actual_quote - self.ai_cost_pln - self.infrastructure_pln) / self.total_hours


def calculate_quote(
    estimated_hours_min: float,
    estimated_hours_max: float,
    ai_cost_pln: float,
    risk_level: str,  # LOW/MEDIUM/HIGH/VERY_HIGH
    hourly_rate: float = 70.0,
    infrastructure_pln: float = 0.0,
    client_budget_pln: float | None = None,
    deadline: str | None = None,
    minimum_job_price: float = 150.0,
    risk_buffer_percent: dict[str, int] | None = None,
) -> QuoteEstimate:
    """Calculate the full freelance job quote based on inputs."""
    # 1. Time breakdown
    average_hours = (estimated_hours_min + estimated_hours_max) / 2
    implementation_hours = average_hours * 0.65
    testing_hours = average_hours * 0.20
    deployment_hours = average_hours * 0.10
    contingency_hours = average_hours * 0.05
    total_hours = implementation_hours + testing_hours + deployment_hours + contingency_hours

    # 2. Cost calculation
    human_work_pln = total_hours * hourly_rate

    if risk_buffer_percent is None:
        risk_buffer_percent = {"LOW": 5, "MEDIUM": 15, "HIGH": 30, "VERY_HIGH": 50}

    buffer_percent = risk_buffer_percent.get(risk_level, 15)
    risk_buffer_pln = (human_work_pln + ai_cost_pln + infrastructure_pln) * buffer_percent / 100

    # 3. Final prices
    minimum_technical_price_pln = (
        human_work_pln + ai_cost_pln + infrastructure_pln + risk_buffer_pln
    )
    minimum_technical_price_pln = max(minimum_technical_price_pln, minimum_job_price)

    recommended_quote_min_pln = minimum_technical_price_pln * 1.15
    recommended_quote_max_pln = minimum_technical_price_pln * 1.40

    # Prices are floors: never round a minimum below the calculated cost.
    minimum_technical_price_pln = math.ceil(minimum_technical_price_pln / 10) * 10
    recommended_quote_min_pln = math.ceil(recommended_quote_min_pln / 10) * 10
    recommended_quote_max_pln = math.ceil(recommended_quote_max_pln / 10) * 10

    # 4. Warnings
    warnings = []
    if client_budget_pln is not None:
        if client_budget_pln < minimum_technical_price_pln:
            warnings.append(
                f"Client budget ({client_budget_pln} PLN) is below minimum technical price "
                f"({minimum_technical_price_pln} PLN)"
            )
        elif client_budget_pln < recommended_quote_min_pln:
            warnings.append("Client budget is below recommended quote range")

    if deadline is not None:
        try:
            deadline_date = datetime.date.fromisoformat(deadline)
            days_remaining = (deadline_date - datetime.date.today()).days
            if days_remaining < 0:
                warnings.append("Deadline has already passed")
            elif days_remaining * 6 < estimated_hours_max:
                warnings.append(
                    f"Deadline may be too tight: {days_remaining} day(s) remain for up to "
                    f"{estimated_hours_max:.1f}h of work"
                )
        except ValueError:
            warnings.append("Deadline is not a valid YYYY-MM-DD date")

    if risk_level in ("HIGH", "VERY_HIGH"):
        warnings.append("High risk project — consider raising the quote")

    # 5. Questions for client
    questions_for_client = ["What are the exact acceptance criteria?"]
    questions_for_client.append("Are there existing tests I should maintain?")
    questions_for_client.append("What is the deployment target?")
    if risk_level in ("HIGH", "VERY_HIGH"):
        questions_for_client.append("Is there documentation for the existing codebase?")

    # 6. Confidence
    confidence_mapping = {"LOW": 85, "MEDIUM": 72, "HIGH": 55, "VERY_HIGH": 40}
    confidence_percent = confidence_mapping.get(risk_level, 72)

    return QuoteEstimate(
        implementation_hours=implementation_hours,
        testing_hours=testing_hours,
        deployment_hours=deployment_hours,
        contingency_hours=contingency_hours,
        total_hours=total_hours,
        human_work_pln=human_work_pln,
        ai_cost_pln=ai_cost_pln,
        infrastructure_pln=infrastructure_pln,
        risk_buffer_pln=risk_buffer_pln,
        minimum_technical_price_pln=minimum_technical_price_pln,
        recommended_quote_min_pln=recommended_quote_min_pln,
        recommended_quote_max_pln=recommended_quote_max_pln,
        risk_level=risk_level,
        confidence_percent=confidence_percent,
        hourly_rate=hourly_rate,
        warnings=warnings,
        questions_for_client=questions_for_client,
    )
