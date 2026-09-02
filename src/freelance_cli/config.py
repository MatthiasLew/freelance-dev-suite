"""User configuration management.

Config file: ~/.freelance/config.yaml
Workspace root defaults to ~/freelance-workspace if not configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".freelance"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_WORKSPACE_ROOT = Path.home() / "freelance-workspace"


@dataclass
class PricingConfig:
    """Freelancer pricing configuration."""

    hourly_rate: float = 70.0
    minimum_job_price: float = 150.0
    risk_buffer_percent: dict[str, int] = field(
        default_factory=lambda: {"LOW": 5, "MEDIUM": 15, "HIGH": 30, "VERY_HIGH": 50}
    )


@dataclass
class Config:
    """Top-level application configuration."""

    currency: str = "PLN"
    pricing: PricingConfig = field(default_factory=PricingConfig)
    workspace_root: str = str(DEFAULT_WORKSPACE_ROOT)
    default_model: str = "claude-sonnet-4"
    model_pricing_path: str | None = None
    usd_to_pln_rate: float = 4.0
    job_counter: int = 0

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_root)

    @property
    def active_dir(self) -> Path:
        return self.workspace_path / "active"

    @property
    def finished_dir(self) -> Path:
        return self.workspace_path / "finished"

    @property
    def templates_dir(self) -> Path:
        return self.workspace_path / "templates"

    @property
    def config_dir(self) -> Path:
        return self.workspace_path / "config"

    def next_job_id(self) -> str:
        """Generate the next sequential JOB-ID."""
        self.job_counter += 1
        return f"JOB-{self.job_counter:03d}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "pricing": {
                "hourly_rate": self.pricing.hourly_rate,
                "minimum_job_price": self.pricing.minimum_job_price,
                "risk_buffer_percent": self.pricing.risk_buffer_percent,
            },
            "workspace": {"root": self.workspace_root},
            "models": {
                "default": self.default_model,
                "pricing_file": self.model_pricing_path,
            },
            "exchange_rates": {"usd_to_pln": self.usd_to_pln_rate},
            "internal": {"job_counter": self.job_counter},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        pricing_data = data.get("pricing", {})
        pricing = PricingConfig(
            hourly_rate=pricing_data.get("hourly_rate", 70.0),
            minimum_job_price=pricing_data.get("minimum_job_price", 150.0),
            risk_buffer_percent=pricing_data.get(
                "risk_buffer_percent", {"LOW": 5, "MEDIUM": 15, "HIGH": 30, "VERY_HIGH": 50}
            ),
        )
        workspace_data = data.get("workspace", {})
        models_data = data.get("models", {})
        exchange_data = data.get("exchange_rates", {})
        internal_data = data.get("internal", {})
        return cls(
            currency=data.get("currency", "PLN"),
            pricing=pricing,
            workspace_root=workspace_data.get("root", str(DEFAULT_WORKSPACE_ROOT)),
            default_model=models_data.get("default", "claude-sonnet-4"),
            model_pricing_path=models_data.get("pricing_file"),
            usd_to_pln_rate=float(exchange_data.get("usd_to_pln", 4.0)),
            job_counter=internal_data.get("job_counter", 0),
        )


def load_config(config_path: Path | None = None) -> Config:
    """Load config from YAML file, or return defaults."""
    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Config.from_dict(data)
    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save config to YAML file."""
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            config.to_dict(),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
