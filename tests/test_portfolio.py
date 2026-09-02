"""Tests for portfolio generator and case study models."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.portfolio import PortfolioCaseStudy, PortfolioGenerator


class TestPortfolio:
    """Test PortfolioCaseStudy models, generation, anonymization, and CLI."""

    def test_case_study_model_and_markdown(self) -> None:
        cs = PortfolioCaseStudy(
            job_id="JOB-001",
            title="E-Commerce Payment Pipeline",
            client_name="Stripe Partner",
            industry="Fintech",
            overview="High throughput payment gateway.",
            challenge="Needed PCI compliance and high availability.",
            solution="Microservices in Python and FastAPI.",
            technologies=["Python", "FastAPI", "PostgreSQL"],
            key_features=["Webhook listeners", "Idempotency keys"],
            metrics={"Uptime": "99.99%", "Test Coverage": "95%"},
            testimonial_placeholder="Flawless delivery.",
            is_anonymized=False,
        )

        assert cs.job_id == "JOB-001"
        data = cs.to_dict()
        assert data["industry"] == "Fintech"

        restored = PortfolioCaseStudy.from_dict(data)
        assert restored.title == cs.title

        md = cs.to_markdown()
        assert "# Case Study: E-Commerce Payment Pipeline" in md
        assert "**Client:** Stripe Partner" in md
        assert "`FastAPI`" in md
        assert "99.99%" in md

    def test_portfolio_generator_and_anonymization(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "active" / "JOB-001-portfolio"
        job_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        (job_dir / "job.json").write_text(
            json.dumps({
                "id": "JOB-001",
                "client": "SecretCorp",
                "description": "Internal Fraud Detection Engine",
            }),
            encoding="utf-8",
        )
        (analysis_dir / "intake.json").write_text(
            json.dumps({"stack": ["Python", "Pandas", "Scikit-Learn"]}),
            encoding="utf-8",
        )
        (analysis_dir / "requirements.json").write_text(
            json.dumps({
                "requirements": [
                    {"title": "Real-time anomaly scoring"},
                    {"title": "Automated alert dispatches"},
                ]
            }),
            encoding="utf-8",
        )

        gen = PortfolioGenerator()

        # 1. Standard non-anonymized
        cs, out_path = gen.generate("JOB-001", job_dir, anonymize=False)
        assert cs.client_name == "SecretCorp"
        assert not cs.is_anonymized
        assert out_path.exists()
        assert "SecretCorp" in out_path.read_text(encoding="utf-8")

        # 2. Anonymized
        custom_out = tmp_path / "anon-case-study.md"
        cs_anon, anon_path = gen.generate(
            "JOB-001", job_dir, anonymize=True, output_path=custom_out
        )
        assert cs_anon.is_anonymized
        assert "SecretCorp" not in cs_anon.client_name
        assert anon_path == custom_out
        assert anon_path.exists()

    def test_portfolio_cli(self, cli_runner: CliRunner) -> None:
        new_res = cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Initech",
                "--description",
                "TPS Reporting Automation",
                "--source",
                "Direct",
            ],
        )
        assert new_res.exit_code == 0
        job_id = "JOB-001"

        res = cli_runner.invoke(main, ["portfolio", job_id, "--anonymize"])
        assert res.exit_code == 0
        assert "Case Study Generated Successfully" in res.output
        assert "Anonymized:   True" in res.output

        res_json = cli_runner.invoke(main, ["portfolio", job_id, "--json"])
        assert res_json.exit_code == 0
        data = json.loads(res_json.output)
        assert data["case_study"]["job_id"] == "JOB-001"
