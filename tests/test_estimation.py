"""Tests for the intake analyzer, AI cost estimator, and quote calculator."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.ai_cost.estimator import AICostEstimate, estimate_ai_cost
from packages.ai_cost.pricing import (
    DEFAULT_MODELS,
    ModelPricing,
    calculate_cost,
    get_model,
    usd_to_pln,
)
from packages.estimator.calculator import QuoteEstimate, calculate_quote
from packages.intake.analyzer import analyze_project, parse_dependencies
from packages.intake.complexity import classify_complexity, estimate_work_hours
from packages.intake.risk import assess_risk

# ──────────────────── Risk scoring ──────────────────────────────────


class TestRiskScoring:
    def test_low_risk(self) -> None:
        level, factors = assess_risk(
            has_tests=True,
            has_lint=True,
            has_typecheck=True,
            has_docker=True,
            has_ci=True,
            total_files=50,
            dependency_count=10,
            config_warnings=[],
        )
        assert level == "LOW"
        assert factors == []

    def test_medium_risk_no_tests_no_lint(self) -> None:
        level, factors = assess_risk(
            has_tests=False,
            has_lint=False,
            has_typecheck=True,
            has_docker=True,
            has_ci=True,
            total_files=50,
            dependency_count=10,
            config_warnings=[],
        )
        assert level == "MEDIUM"
        assert "No tests detected" in factors
        assert "No linter detected" in factors

    def test_high_risk_many_issues(self) -> None:
        level, factors = assess_risk(
            has_tests=False,
            has_lint=False,
            has_typecheck=False,
            has_docker=False,
            has_ci=False,
            total_files=100,
            dependency_count=10,
            config_warnings=[],
        )
        assert level == "HIGH"

    def test_very_high_risk_huge_project(self) -> None:
        level, factors = assess_risk(
            has_tests=False,
            has_lint=False,
            has_typecheck=False,
            has_docker=False,
            has_ci=False,
            total_files=3000,
            dependency_count=50,
            config_warnings=["warn1", "warn2"],
        )
        assert level == "VERY_HIGH"

    def test_large_project_risk(self) -> None:
        level, factors = assess_risk(
            has_tests=True,
            has_lint=True,
            has_typecheck=True,
            has_docker=True,
            has_ci=True,
            total_files=600,
            dependency_count=10,
            config_warnings=[],
        )
        assert any("Large project" in f for f in factors)

    def test_many_deps_risk(self) -> None:
        level, factors = assess_risk(
            has_tests=True,
            has_lint=True,
            has_typecheck=True,
            has_docker=True,
            has_ci=True,
            total_files=50,
            dependency_count=40,
            config_warnings=[],
        )
        assert any("dependencies" in f for f in factors)


# ──────────────────── Complexity ────────────────────────────────────


class TestComplexity:
    def test_low(self) -> None:
        assert classify_complexity(1, 0, 500, 20, 1) == "LOW"

    def test_medium(self) -> None:
        assert classify_complexity(2, 1, 5000, 100, 1) == "MEDIUM"

    def test_high(self) -> None:
        assert classify_complexity(3, 2, 20000, 300, 1) == "HIGH"

    def test_very_high(self) -> None:
        assert classify_complexity(4, 3, 50000, 600, 1) == "VERY_HIGH"

    def test_monorepo_bumps(self) -> None:
        # Monorepo with 300 files should be HIGH, not MEDIUM
        assert classify_complexity(2, 1, 5000, 300, 3) == "HIGH"

    def test_work_hours_low(self) -> None:
        min_h, max_h = estimate_work_hours("LOW")
        assert min_h == 1.0
        assert max_h == 3.0

    def test_work_hours_medium(self) -> None:
        min_h, max_h = estimate_work_hours("MEDIUM")
        assert min_h == 3.0
        assert max_h == 8.0


# ──────────────────── Model pricing ─────────────────────────────────


class TestPricing:
    def test_default_models_exist(self) -> None:
        assert "claude-sonnet-4" in DEFAULT_MODELS
        assert "gpt-4.1" in DEFAULT_MODELS
        assert "gemini-2.5-pro" in DEFAULT_MODELS

    def test_get_model(self) -> None:
        model = get_model("claude-sonnet-4")
        assert model.input_per_million == 3.0
        assert model.output_per_million == 15.0

    def test_get_model_unknown_raises(self) -> None:
        with pytest.raises(ValueError):
            get_model("nonexistent-model")

    def test_calculate_cost(self) -> None:
        model = ModelPricing("test", input_per_million=2.0, output_per_million=8.0)
        cost = calculate_cost(model, input_tokens=1_000_000, output_tokens=100_000)
        assert cost == pytest.approx(2.0 + 0.8)

    def test_calculate_cost_with_cache(self) -> None:
        model = ModelPricing("test", 2.0, 8.0, cached_input_per_million=0.5)
        cost = calculate_cost(model, 500_000, 100_000, cached_tokens=500_000)
        assert cost == pytest.approx(0.8 + 0.25)

    def test_usd_to_pln(self) -> None:
        with pytest.raises(TypeError):
            usd_to_pln(10.0)  # type: ignore[call-arg]
        assert usd_to_pln(10.0, rate=3.5) == 35.0


# ──────────────────── AI cost estimate ──────────────────────────────


class TestAICostEstimate:
    def test_low_complexity(self) -> None:
        est = estimate_ai_cost(500, 10, "LOW")
        assert est.expected_turns == 3
        assert est.confidence_percent == 70
        assert est.cost_pln_expected > 0

    def test_medium_complexity(self) -> None:
        est = estimate_ai_cost(5000, 50, "MEDIUM")
        assert est.expected_turns == 6
        assert est.confidence_percent == 57

    def test_high_complexity(self) -> None:
        est = estimate_ai_cost(20000, 200, "HIGH")
        assert est.expected_turns == 12
        assert est.confidence_percent == 40

    def test_measured_context_preserves_confidence(self) -> None:
        est = estimate_ai_cost(500, 10, "LOW", context_tokens=2_500)
        assert est.confidence_percent == 85
        assert "measured by ai-dev" in est.assumptions[-1]

    def test_cost_ranges(self) -> None:
        est = estimate_ai_cost(5000, 50, "MEDIUM")
        assert est.cost_usd_min < est.cost_usd_expected < est.cost_usd_max
        assert est.cost_pln_min < est.cost_pln_expected < est.cost_pln_max

    def test_serialization(self) -> None:
        est = estimate_ai_cost(1000, 10, "LOW")
        data = est.to_dict()
        restored = AICostEstimate.from_dict(data)
        assert restored.model_name == est.model_name
        assert restored.cost_pln_expected == est.cost_pln_expected

    def test_summary_output(self) -> None:
        est = estimate_ai_cost(1000, 10, "LOW")
        summary = est.summary()
        assert "AI Cost Estimate" in summary
        assert "PLN" in summary

    def test_large_repo_cost_driver(self) -> None:
        est = estimate_ai_cost(10000, 100, "HIGH")
        assert any("Large" in d for d in est.cost_drivers)


# ──────────────────── Quote calculator ──────────────────────────────


class TestQuoteCalculator:
    def test_basic_quote(self) -> None:
        quote = calculate_quote(
            estimated_hours_min=3.0,
            estimated_hours_max=8.0,
            ai_cost_pln=50.0,
            risk_level="MEDIUM",
        )
        assert quote.total_hours > 0
        assert quote.minimum_technical_price_pln > 0
        assert quote.recommended_quote_min_pln < quote.recommended_quote_max_pln

    def test_time_breakdown(self) -> None:
        quote = calculate_quote(4.0, 6.0, 0.0, "LOW")
        total = (
            quote.implementation_hours
            + quote.testing_hours
            + quote.deployment_hours
            + quote.contingency_hours
        )
        assert total == pytest.approx(quote.total_hours)

    def test_minimum_price_floor(self) -> None:
        quote = calculate_quote(0.1, 0.2, 0.0, "LOW", minimum_job_price=150.0)
        assert quote.minimum_technical_price_pln >= 150.0

    def test_budget_warning_below_minimum(self) -> None:
        quote = calculate_quote(5.0, 10.0, 50.0, "MEDIUM", client_budget_pln=100.0)
        assert any("below minimum" in w for w in quote.warnings)

    def test_high_risk_warning(self) -> None:
        quote = calculate_quote(5.0, 10.0, 50.0, "HIGH")
        assert any("High risk" in w for w in quote.warnings)

    def test_questions_always_include_acceptance(self) -> None:
        quote = calculate_quote(3.0, 5.0, 30.0, "LOW")
        assert any("acceptance criteria" in q for q in quote.questions_for_client)

    def test_high_risk_asks_about_docs(self) -> None:
        quote = calculate_quote(5.0, 10.0, 50.0, "HIGH")
        assert any("documentation" in q for q in quote.questions_for_client)

    def test_confidence_varies_by_risk(self) -> None:
        low = calculate_quote(3.0, 5.0, 30.0, "LOW")
        high = calculate_quote(3.0, 5.0, 30.0, "HIGH")
        assert low.confidence_percent > high.confidence_percent

    def test_is_budget_sufficient(self) -> None:
        quote = calculate_quote(3.0, 5.0, 30.0, "LOW")
        assert quote.is_budget_sufficient(10000.0)
        assert not quote.is_budget_sufficient(10.0)

    def test_effective_hourly_rate(self) -> None:
        quote = calculate_quote(3.0, 5.0, 30.0, "LOW")
        rate = quote.effective_hourly_rate(500.0)
        assert rate > 0

    def test_serialization(self) -> None:
        quote = calculate_quote(3.0, 5.0, 30.0, "MEDIUM")
        data = quote.to_dict()
        restored = QuoteEstimate.from_dict(data)
        assert restored.risk_level == "MEDIUM"
        assert restored.minimum_technical_price_pln == quote.minimum_technical_price_pln

    def test_summary_output(self) -> None:
        quote = calculate_quote(3.0, 5.0, 30.0, "MEDIUM")
        summary = quote.summary()
        assert "ESTIMATE" in summary
        assert "PLN" in summary
        assert "Recommended quote" in summary

    def test_rounded_to_10(self) -> None:
        quote = calculate_quote(3.0, 5.0, 30.0, "MEDIUM")
        assert quote.minimum_technical_price_pln % 10 == 0
        assert quote.recommended_quote_min_pln % 10 == 0
        assert quote.recommended_quote_max_pln % 10 == 0

    def test_minimum_price_is_never_rounded_down(self) -> None:
        quote = calculate_quote(
            1.0,
            1.0,
            3.0,
            "LOW",
            hourly_rate=151.0,
            minimum_job_price=0.0,
        )
        raw_cost = quote.human_work_pln + quote.ai_cost_pln + quote.risk_buffer_pln
        assert quote.minimum_technical_price_pln >= raw_cost


def test_parse_pep621_dependencies(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["click>=8", "PyYAML>=6"]\n'
        '[project.optional-dependencies]\ndev = ["pytest>=8"]\n',
        encoding="utf-8",
    )
    assert parse_dependencies(str(tmp_path), ["pip/pyproject"]) == 3


def test_parse_dependencies_deduplicates_version_constraints(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["requests>=2", "requests<3", "my_pkg[cli]~=1.2"]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "requests==2.32\nmy-pkg!=1.3\n",
        encoding="utf-8",
    )

    assert parse_dependencies(str(tmp_path), ["pip/pyproject"]) == 2


def test_analyze_project_uses_current_ai_dev_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")

    def fake_run(_project: Path, *arguments: str) -> dict[str, object]:
        if arguments == ("scan",):
            return {
                "status": "success",
                "summary": {
                    "languages": ["python"],
                    "frameworks": [],
                    "package_managers": ["pip/pyproject"],
                    "docker": False,
                    "ci": ["github-actions"],
                    "workspace_count": 1,
                    "config_warnings": [],
                },
            }
        if arguments == ("map",):
            return {"status": "success", "summary": {"file_count_scanned": 7}}
        if arguments[:2] == ("check", "--mode"):
            return {
                "status": "success",
                "summary": {
                    "plan": [
                        {"category": "lint"},
                        {"category": "typecheck"},
                        {"category": "unit_tests"},
                    ],
                    "results": [
                        {"category": "lint", "status": "passed"},
                        {"category": "typecheck", "status": "passed"},
                        {"category": "unit_tests", "status": "passed"},
                    ],
                    "tests_total": 4,
                    "tests_passed": 4,
                    "tests_failed": 0,
                    "tests_skipped": 0,
                },
            }
        return {"status": "success", "summary": {"budget": {"used_chars": 12_000}}}

    monkeypatch.setattr("packages.intake.analyzer._run_ai_dev", fake_run)
    result = analyze_project(str(tmp_path), "fix parser")
    assert result.total_files == 7
    assert result.has_tests is True
    assert result.tests_passed == 4
    assert result.lint_status == "passed"
    assert result.context_tokens == 3_000
