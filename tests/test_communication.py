"""Tests for client communication models, generator, and CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.communication import ClientMessage, MessageGenerator, MessageStage


class TestClientCommunication:
    """Test ClientMessage models, stage generators, language support, and CLI."""

    def test_client_message_model_and_markdown(self) -> None:
        msg = ClientMessage(
            job_id="JOB-001",
            client_name="Wayne Enterprises",
            stage=MessageStage.QUOTE.value,
            subject="Project Quote — Batcomputer API",
            body="Here is the detailed project scope and quote.",
            language="en",
        )

        assert msg.job_id == "JOB-001"
        data = msg.to_dict()
        assert data["stage"] == "quote"

        restored = ClientMessage.from_dict(data)
        assert restored.subject == msg.subject

        md = msg.to_markdown()
        assert "**Subject:** Project Quote — Batcomputer API" in md
        assert "**To:** Wayne Enterprises" in md

    def test_message_generator_stages(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "active" / "JOB-001-msg"
        job_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        (job_dir / "job.json").write_text(
            json.dumps({"id": "JOB-001", "client": "Cyberdyne", "description": "T-800 Firmware"}),
            encoding="utf-8",
        )
        (analysis_dir / "estimate.json").write_text(
            json.dumps({"price_pln": 5000.0, "hours": 20.0}),
            encoding="utf-8",
        )
        (analysis_dir / "requirements.json").write_text(
            json.dumps({"requirements": [{"title": "Neural net parser"}]}),
            encoding="utf-8",
        )

        gen = MessageGenerator()

        # 1. Intake in Polish
        intake_msg = gen.generate("JOB-001", job_dir, MessageStage.INTAKE, language="pl")
        assert "Potwierdzenie przyjęcia briefu" in intake_msg.subject
        assert "Dzień dobry Cyberdyne" in intake_msg.body

        # 2. Quote in English
        quote_msg = gen.generate(
            "JOB-001", job_dir, MessageStage.QUOTE, language="en", notes="Milestone 1 by Friday"
        )
        assert "Project Proposal" in quote_msg.subject
        assert "5000 PLN" in quote_msg.body
        assert "Milestone 1 by Friday" in quote_msg.body

        # 3. Update / milestone
        update_msg = gen.generate("JOB-001", job_dir, MessageStage.UPDATE, language="pl")
        assert "Status postępu prac" in update_msg.subject

        # 4. Demo
        demo_msg = gen.generate("JOB-001", job_dir, MessageStage.DEMO, language="pl")
        assert "Wersja testowa" in demo_msg.subject

        # 5. Delivery
        deliv_msg = gen.generate("JOB-001", job_dir, MessageStage.DELIVERY, language="en")
        assert "Final Project Delivery" in deliv_msg.subject

        # 6. Reminder
        rem_msg = gen.generate("JOB-001", job_dir, MessageStage.REMINDER, language="pl")
        assert "przypomnienie" in rem_msg.subject.lower()

        # 7. Scope Notice
        scope_msg = gen.generate("JOB-001", job_dir, MessageStage.SCOPE_NOTICE, language="en")
        assert "Scope Extension Notice" in scope_msg.subject

    def test_message_cli(self, cli_runner: CliRunner) -> None:
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Globex",
                "--description",
                "Laser Defense Module",
                "--source",
                "Direct",
            ],
        )
        job_id = "JOB-001"

        res = cli_runner.invoke(main, ["message", job_id, "intake", "--lang", "pl"])
        assert res.exit_code == 0
        assert "CLIENT MESSAGE DRAFT [INTAKE]" in res.output
        assert "Dzień dobry Globex" in res.output

        res_json = cli_runner.invoke(
            main, ["message", job_id, "delivery", "--lang", "en", "--json"]
        )
        assert res_json.exit_code == 0
        data = json.loads(res_json.output)
        assert data["stage"] == "delivery"
        assert data["language"] == "en"
