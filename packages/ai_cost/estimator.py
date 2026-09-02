"""AI usage estimator with explicit, serializable assumptions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from .pricing import ModelPricing, calculate_cost, get_model, usd_to_pln


@dataclass
class AICostEstimate:
    context_tokens: int
    expected_turns: int
    avg_input_tokens: int
    avg_output_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    model_name: str
    usd_to_pln_rate: float
    cost_usd_expected: float
    cost_usd_min: float
    cost_usd_max: float
    cost_pln_expected: float
    cost_pln_min: float
    cost_pln_max: float
    confidence_percent: int
    cost_drivers: list[str]
    assumptions: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AICostEstimate:
        compatible = dict(data)
        compatible.setdefault("cached_input_tokens", 0)
        compatible.setdefault("reasoning_tokens", 0)
        compatible.setdefault("usd_to_pln_rate", 4.0)
        compatible.setdefault("assumptions", [])
        return cls(**compatible)

    def summary(self) -> str:
        drivers = "\n".join(f"  - {driver}" for driver in self.cost_drivers)
        assumptions = "\n".join(f"  - {item}" for item in self.assumptions)
        return (
            f"AI Cost Estimate ({self.model_name}):\n"
            f"  Confidence: {self.confidence_percent}%\n"
            f"  Expected Turns: {self.expected_turns}\n"
            f"  Tokens: {self.total_input_tokens} in / {self.total_output_tokens} out\n"
            f"  Expected Cost: ${self.cost_usd_expected:.2f} "
            f"({self.cost_pln_expected:.2f} PLN)\n"
            f"  Cost Range: {self.cost_pln_min:.2f}-{self.cost_pln_max:.2f} PLN\n"
            f"  Cost Drivers:\n{drivers}\n"
            f"  Assumptions:\n{assumptions}"
        )


def estimate_ai_cost(
    loc: int,
    source_files: int,
    complexity: str,
    task_description: str = "",
    model_name: str = "claude-sonnet-4",
    context_tokens: int | None = None,
    models: dict[str, ModelPricing] | None = None,
    exchange_rate: float = 4.0,
) -> AICostEstimate:
    """Estimate a realistic range while recording every material assumption."""
    if loc < 0 or source_files < 0:
        raise ValueError("LOC and source file counts cannot be negative")
    complexity = complexity.upper()
    profiles = {
        "LOW": (3, 1_500, 85),
        "MEDIUM": (6, 3_000, 72),
        "HIGH": (12, 5_000, 55),
        "VERY_HIGH": (20, 8_000, 40),
    }
    expected_turns, avg_output_tokens, confidence = profiles.get(complexity, profiles["MEDIUM"])
    if context_tokens is not None and context_tokens > 0:
        measured_context = True
        effective_context = context_tokens
    else:
        measured_context = False
        effective_context = max(1_000, loc * 4)
    avg_input_tokens = max(1_000, int(effective_context * 0.7) + 500)
    total_input_tokens = expected_turns * avg_input_tokens
    total_output_tokens = expected_turns * avg_output_tokens
    cached_input_tokens = int(total_input_tokens * 0.25)
    reasoning_tokens = int(total_output_tokens * 0.15) if complexity in {"HIGH", "VERY_HIGH"} else 0

    model = get_model(model_name, models)
    expected_usd = calculate_cost(
        model,
        total_input_tokens,
        total_output_tokens,
        cached_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
    )
    minimum_usd = expected_usd * 0.6
    maximum_usd = expected_usd * 1.8
    if not measured_context:
        confidence = max(20, confidence - 15)

    drivers: list[str] = []
    if effective_context > 30_000:
        drivers.append("Large repository context")
    if expected_turns >= 12:
        drivers.append("Many implementation iterations")
    if source_files > 250:
        drivers.append("Many source files may require broader retrieval")
    if len(task_description) > 1_000:
        drivers.append("Large task specification")
    if not drivers:
        drivers.append("Standard project scale and complexity")

    assumptions = [
        f"{expected_turns} implementation and test/fix turns",
        "25% of repeated input is billed at the configured cached-input rate",
        "cost range is 60%-180% of the expected usage",
        f"USD/PLN conversion rate is {exchange_rate:.4f}",
    ]
    assumptions.append(
        "context size measured by ai-dev context build"
        if measured_context
        else "context size estimated from LOC because measured context was unavailable"
    )

    return AICostEstimate(
        context_tokens=effective_context,
        expected_turns=expected_turns,
        avg_input_tokens=avg_input_tokens,
        avg_output_tokens=avg_output_tokens,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        model_name=model_name,
        usd_to_pln_rate=exchange_rate,
        cost_usd_expected=expected_usd,
        cost_usd_min=minimum_usd,
        cost_usd_max=maximum_usd,
        cost_pln_expected=usd_to_pln(expected_usd, exchange_rate),
        cost_pln_min=usd_to_pln(minimum_usd, exchange_rate),
        cost_pln_max=usd_to_pln(maximum_usd, exchange_rate),
        confidence_percent=confidence,
        cost_drivers=drivers,
        assumptions=assumptions,
    )
