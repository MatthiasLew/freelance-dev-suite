"""Tests for model pricing updates and CLI."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.ai_cost.pricing import (
    ModelPricing,
    load_model_pricing,
    save_model_pricing,
)


class TestPricingUpdates:
    """Test loading, saving, and CLI pricing commands."""

    def test_save_and_reload_pricing(self, tmp_path: Path) -> None:
        file_path = tmp_path / "custom-pricing.yaml"
        models = {
            "custom-model": ModelPricing(
                name="custom-model",
                input_per_million=1.5,
                output_per_million=6.0,
                cached_input_per_million=0.5,
                reasoning_per_million=2.0,
            )
        }

        save_model_pricing(models, file_path)
        assert file_path.exists()

        reloaded = load_model_pricing(file_path)
        assert "custom-model" in reloaded
        assert reloaded["custom-model"].input_per_million == 1.5
        assert reloaded["custom-model"].reasoning_per_million == 2.0

    def test_pricing_cli(self, cli_runner: CliRunner) -> None:
        res = cli_runner.invoke(main, ["pricing"])
        assert res.exit_code == 0
        assert "CONFIGURED AI MODEL PRICING" in res.output
        assert "claude-sonnet-4" in res.output

        res_json = cli_runner.invoke(main, ["pricing", "--json"])
        assert res_json.exit_code == 0
        data = json.loads(res_json.output)
        assert "claude-sonnet-4" in data
