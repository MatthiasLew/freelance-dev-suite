"""Tests for scope-change-detector module, proposal generator, and CLI integration."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.requirements.models import (
    AcceptanceCriterion,
    RequirementItem,
    RequirementsSpec,
)
from packages.scope import (
    ScopeChangeDetector,
    ScopeChangeItem,
    ScopeClassification,
)


class TestScopeModels:
    """Test ScopeChangeItem serialization and markdown generation."""

    def test_scope_item_serialization(self) -> None:
        item = ScopeChangeItem(
            id="CHANGE-001",
            job_id="JOB-001",
            requested_text="Dodaj eksport do PDF",
            classification=ScopeClassification.OUT_OF_SCOPE.value,
            new_functionalities=["Dodaj eksport do PDF"],
            estimated_additional_hours=3.0,
            estimated_ai_cost_pln=12.0,
            suggested_extra_price_pln=450.0,
            impact_assessment="Nowa funkcjonalność",
            client_proposal_message="Wycena rozszerzenia: 450 PLN",
        )

        data = item.to_dict()
        assert data["id"] == "CHANGE-001"
        assert data["suggested_extra_price_pln"] == 450.0

        restored = ScopeChangeItem.from_dict(data)
        assert restored.id == item.id
        assert restored.classification == ScopeClassification.OUT_OF_SCOPE.value

    def test_scope_item_markdown(self) -> None:
        item = ScopeChangeItem(
            id="CHANGE-001",
            job_id="JOB-001",
            requested_text="Eksport XLS",
            classification=ScopeClassification.OUT_OF_SCOPE.value,
            estimated_additional_hours=2.0,
            suggested_extra_price_pln=300.0,
            client_proposal_message="Proposal content here",
        )
        md = item.to_markdown()
        assert "CHANGE-001" in md
        assert "OUT_OF_SCOPE" in md
        assert "300 PLN" in md
        assert item.to_proposal_markdown() == "Proposal content here"


class TestScopeDetector:
    """Test ScopeChangeDetector classification, pricing, and persistence."""

    def _sample_spec(self) -> RequirementsSpec:
        return RequirementsSpec(
            job_id="JOB-001",
            title="Sample Job",
            requirements=[
                RequirementItem(
                    id="REQ-001",
                    section="Backend",
                    title="User authentication via email and password",
                ),
                RequirementItem(
                    id="REQ-002",
                    section="Data",
                    title="CSV transaction file import",
                ),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="AC-001",
                    criterion="Valid credentials return JWT token",
                ),
                AcceptanceCriterion(
                    id="AC-002",
                    criterion="Import parsed records to database",
                ),
            ],
        )

    def test_in_scope_detection(self) -> None:
        detector = ScopeChangeDetector()
        spec = self._sample_spec()

        res = detector.analyze_request(
            job_id="JOB-001",
            change_id="CHANGE-001",
            requested_text="Weryfikacja logowania użytkownika przez email i hasło",
            requirements_spec=spec,
        )

        assert res.classification == ScopeClassification.IN_SCOPE.value
        assert res.estimated_additional_hours == 0.0
        assert res.suggested_extra_price_pln == 0.0
        assert "bez żadnych dodatkowych opłat" in res.client_proposal_message

    def test_minor_extension_detection(self) -> None:
        detector = ScopeChangeDetector()
        spec = self._sample_spec()

        tweak_text = (
            "Drobna zmiana: zmień formatowanie i tekst etykiety "
            "na formularzu logowania użytkownika"
        )
        res = detector.analyze_request(
            job_id="JOB-001",
            change_id="CHANGE-001",
            requested_text=tweak_text,
            requirements_spec=spec,
        )

        assert res.classification == ScopeClassification.MINOR_EXTENSION.value
        assert res.estimated_additional_hours > 0
        assert res.suggested_extra_price_pln > 0
        assert "drobna modyfikacja" in res.client_proposal_message.lower()

    def test_out_of_scope_detection(self) -> None:
        detector = ScopeChangeDetector()
        spec = self._sample_spec()

        res = detector.analyze_request(
            job_id="JOB-001",
            change_id="CHANGE-001",
            requested_text="Dodaj eksport do pliku PDF oraz wysyłkę e-mailem",
            requirements_spec=spec,
            hourly_rate_pln=150.0,
        )

        assert res.classification == ScopeClassification.OUT_OF_SCOPE.value
        assert res.estimated_additional_hours >= 2.0
        assert res.suggested_extra_price_pln >= 300.0
        assert "Wycena rozszerzenia" in res.client_proposal_message

    def test_breaking_change_detection(self) -> None:
        detector = ScopeChangeDetector()
        spec = self._sample_spec()

        res = detector.analyze_request(
            job_id="JOB-001",
            change_id="CHANGE-001",
            requested_text="Przepisz cały backend na mikroserwisy zamiast monolitu",
            requirements_spec=spec,
        )

        assert res.classification == ScopeClassification.BREAKING_CHANGE.value
        assert res.estimated_additional_hours >= 10.0
        assert "architektury" in res.client_proposal_message

    def test_save_load_list_and_snapshot(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "active" / "JOB-001-scope-test"
        job_dir.mkdir(parents=True, exist_ok=True)

        detector = ScopeChangeDetector()
        spec = self._sample_spec()

        # 1. Snapshot
        snap_path = detector.create_snapshot(job_dir, spec)
        assert snap_path.exists()

        # 2. Save change
        item1 = ScopeChangeItem(
            id="CHANGE-001",
            job_id="JOB-001",
            requested_text="Eksport PDF",
            suggested_extra_price_pln=450.0,
        )
        saved = detector.save_change(item1, job_dir)
        assert "json" in saved
        assert "analysis" in saved
        assert "proposal" in saved
        assert detector.next_change_id(job_dir) == "CHANGE-002"

        # 3. Load & list
        loaded = detector.load_change(job_dir, "CHANGE-001")
        assert loaded is not None
        assert loaded.suggested_extra_price_pln == 450.0

        all_changes = detector.list_changes(job_dir)
        assert len(all_changes) == 1


class TestScopeCLI:
    """Test CLI commands: freelance scope check, list, show, snapshot."""

    def test_cli_scope_lifecycle(self, cli_runner: CliRunner) -> None:
        # 1. Create job
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Cyberdyne",
                "--description",
                "Defense System",
                "--source",
                "Direct",
            ],
        )
        job_id = "JOB-001"

        # 2. Add requirements
        cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--from-text",
                "Moduł logowania i autoryzacji tokenem JWT",
                "--confirm",
            ],
        )

        # 3. Snapshot
        snap_res = cli_runner.invoke(main, ["scope", "snapshot", job_id])
        assert snap_res.exit_code == 0
        assert "Requirements baseline snapshot created" in snap_res.output

        # 4. Check Out-of-Scope request
        check_res = cli_runner.invoke(
            main,
            [
                "scope",
                "check",
                job_id,
                "Dodaj eksport raportów do formatu PDF i Excel",
                "--rate",
                "200.0",
            ],
        )
        assert check_res.exit_code == 0
        assert "SCOPE ANALYSIS — CHANGE-001: OUT_OF_SCOPE" in check_res.output
        assert "Suggested Surcharge:" in check_res.output

        # 5. List changes
        list_res = cli_runner.invoke(main, ["scope", "list", job_id])
        assert list_res.exit_code == 0
        assert "CHANGE-001" in list_res.output
        assert "OUT_OF_SCOPE" in list_res.output

        # 6. Show proposal
        prop_res = cli_runner.invoke(
            main,
            ["scope", "show", job_id, "CHANGE-001", "--proposal"],
        )
        assert prop_res.exit_code == 0
        assert "Wycena rozszerzenia (CHANGE-001)" in prop_res.output

        # 7. Show full analysis
        show_res = cli_runner.invoke(
            main,
            ["scope", "show", job_id, "CHANGE-001"],
        )
        assert show_res.exit_code == 0
        assert "# Scope Change Analysis: CHANGE-001" in show_res.output

    def test_cli_scope_json(self, cli_runner: CliRunner) -> None:
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Massive",
                "--description",
                "Platform",
                "--source",
                "Direct",
            ],
        )
        job_id = "JOB-001"

        check_res = cli_runner.invoke(
            main,
            ["scope", "check", job_id, "Nowy moduł płatności", "--json"],
        )
        assert check_res.exit_code == 0
        data = json.loads(check_res.output)
        assert data["scope_change"]["id"] == "CHANGE-001"
        assert "proposal" in data["files"]

        list_res = cli_runner.invoke(main, ["scope", "list", job_id, "--json"])
        assert list_res.exit_code == 0
        list_data = json.loads(list_res.output)
        assert len(list_data) == 1
        assert list_data[0]["id"] == "CHANGE-001"
