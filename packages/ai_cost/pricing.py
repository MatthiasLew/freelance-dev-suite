"""Configurable model pricing and currency conversion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PRICING_PATH = Path(__file__).with_name("default-pricing.yaml")


@dataclass(frozen=True)
class ModelPricing:
    name: str
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float = 0.0
    reasoning_per_million: float = 0.0


def load_model_pricing(config_path: Path | None = None) -> dict[str, ModelPricing]:
    """Load pricing from YAML; values are never embedded in calculation code."""
    path = config_path or DEFAULT_PRICING_PATH
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot load model pricing from {path}: {exc}") from exc
    model_data = raw.get("models", raw)
    if not isinstance(model_data, dict) or not model_data:
        raise ValueError(f"No model pricing configured in {path}")
    models: dict[str, ModelPricing] = {}
    for name, values in model_data.items():
        if not isinstance(values, dict):
            raise ValueError(f"Invalid pricing entry for model {name}")
        models[str(name)] = ModelPricing(name=str(name), **values)
    return models


DEFAULT_MODELS = load_model_pricing()


def get_model(
    name: str,
    models: dict[str, ModelPricing] | None = None,
) -> ModelPricing:
    available = models or DEFAULT_MODELS
    try:
        return available[name]
    except KeyError as exc:
        choices = ", ".join(sorted(available))
        raise ValueError(f"Model {name!r} not found. Configured models: {choices}") from exc


def calculate_cost(
    model: ModelPricing,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    """Return USD cost, treating cached tokens as a subset of input tokens."""
    if min(input_tokens, output_tokens, cached_tokens, reasoning_tokens) < 0:
        raise ValueError("Token counts cannot be negative")
    uncached_input = max(0, input_tokens - cached_tokens)
    input_cost = (uncached_input / 1_000_000) * model.input_per_million
    output_cost = (output_tokens / 1_000_000) * model.output_per_million
    cached_cost = (cached_tokens / 1_000_000) * model.cached_input_per_million
    reasoning_cost = (reasoning_tokens / 1_000_000) * model.reasoning_per_million
    return input_cost + output_cost + cached_cost + reasoning_cost


def usd_to_pln(usd: float, rate: float) -> float:
    if rate <= 0:
        raise ValueError("USD/PLN exchange rate must be positive")
    return usd * rate
