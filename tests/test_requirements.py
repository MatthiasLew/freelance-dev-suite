"""Tests for the requirements-to-checklist module and CLI integration."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.requirements import (
    AcceptanceCriterion,
    RequirementApprovalState,
    RequirementItem,
    RequirementsSpec,
    generate_requirements,
    parse_requirements_markdown,
)


class TestRequirementsModels:
    """Test data structures, state transitions, progress tracking, and formatting."""

    def test_requirements_spec_creation_and_dict_roundtrip(self) -> None:
        spec = RequirementsSpec(
            job_id="JOB-001",
            title="CSV Data Cleaner",
            approval_state=RequirementApprovalState.DRAFT.value,
            requirements=[
                RequirementItem(id="req-1", title="Import CSV file", section="Input"),
                RequirementItem(id="req-2", title="Filter duplicates", section="Processing"),
                RequirementItem(id="req-3", title="Export XLSX", section="Output"),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-1", criterion="Processes 10k rows under 2s"),
                AcceptanceCriterion(id="ac-2", criterion="Output opens in MS Excel"),
            ],
            assumptions=["UTF-8 encoding only"],
            out_of_scope=["Web interface"],
            questions=["What delimiter is used?"],
            unresolved_decisions=["Decide whether to use pandas or openpyxl"],
        )

        data = spec.to_dict()
        assert data["job_id"] == "JOB-001"
        assert data["approval_state"] == "DRAFT"
        assert len(data["requirements"]) == 3
        assert len(data["acceptance_criteria"]) == 2

        loaded = RequirementsSpec.from_dict(data)
        assert loaded.job_id == spec.job_id
        assert loaded.title == spec.title
        assert len(loaded.requirements) == 3
        assert loaded.requirements[0].title == "Import CSV file"
        assert loaded.requirements[0].section == "Input"
        assert len(loaded.acceptance_criteria) == 2
        assert loaded.assumptions == ["UTF-8 encoding only"]

    def test_confirmation_and_change_workflow(self) -> None:
        spec = RequirementsSpec(
            job_id="JOB-002",
            title="API Bugfix",
        )
        assert spec.approval_state == RequirementApprovalState.DRAFT.value
        # Confirm
        spec.confirm(confirmed_by="Client Alice")
        assert spec.approval_state == RequirementApprovalState.CLIENT_CONFIRMED.value
        assert spec.confirmed_at
        assert spec.confirmed_by == "Client Alice"

        # Mark changed
        spec.mark_changed("Client added auth requirement")
        assert spec.approval_state == RequirementApprovalState.CHANGED.value
        assert spec.version == 2
        assert any("Client added auth requirement" in d for d in spec.unresolved_decisions)

    def test_progress_calculation_and_item_toggle(self) -> None:
        spec = RequirementsSpec(
            job_id="JOB-003",
            title="Automation Script",
            requirements=[
                RequirementItem(id="req-1", title="Task 1", completed=False),
                RequirementItem(id="req-2", title="Task 2", completed=False),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-1", criterion="Passes unit tests", completed=False),
            ],
        )
        done, total, pct = spec.progress
        assert done == 0
        assert total == 3
        assert pct == 0.0

        # Toggle by ID
        assert spec.toggle_item("req-1", completed=True)
        done, total, pct = spec.progress
        assert done == 1
        assert total == 3
        assert pct == 33.3

        # Toggle by numeric index (1-based)
        assert spec.toggle_item("3", completed=True)  # ac-1
        done, total, pct = spec.progress
        assert done == 2
        assert total == 3
        assert pct == 66.7

        # Uncheck
        assert spec.toggle_item("req-1", completed=False)
        done, total, pct = spec.progress
        assert done == 1
        assert pct == 33.3

        # Invalid target ID
        assert not spec.toggle_item("non-existent-id")

    def test_markdown_and_checklist_rendering(self) -> None:
        spec = RequirementsSpec(
            job_id="JOB-004",
            title="Report Generator",
            requirements=[
                RequirementItem(id="req-1", title="Read input", section="Input"),
                RequirementItem(id="req-2", title="Create PDF", section="Output"),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-1", criterion="PDF generated without errors"),
            ],
            assumptions=["Standard Linux font available"],
        )
        md = spec.to_markdown()
        assert "# Requirements — JOB-004: Report Generator" in md
        assert "### Input" in md
        assert "- [ ] `req-1`: Read input" in md
        assert "## Acceptance Criteria" in md
        assert "- [ ] `ac-1`: PDF generated without errors" in md
        assert "## Assumptions" in md

        checklist = spec.to_checklist_markdown()
        assert "# Work Checklist — JOB-004: Report Generator" in checklist
        assert "- [ ] [req-1] Read input" in checklist
        assert "- [ ] [ac-1] PDF generated without errors" in checklist

        summary = spec.summary()
        assert "JOB-004" in summary
        assert "Report Generator" in summary


class TestRequirementsGeneratorAndParser:
    """Test automatic generation from text and bidirectional markdown synchronization."""

    def test_generate_from_freeform_polish_prompt(self) -> None:
        text = """
        Program ma pobierać CSV,
        usuwać duplikaty,
        sortować po dacie
        i generować Excel.
        """
        spec = generate_requirements(text, job_id="JOB-101", title="Excel Processor")

        assert spec.job_id == "JOB-101"
        assert spec.approval_state == RequirementApprovalState.DRAFT.value
        assert len(spec.requirements) >= 4

        sections = {r.section for r in spec.requirements}
        assert "Input" in sections
        assert "Processing" in sections
        assert "Output" in sections

        # Criteria should be generated
        assert len(spec.acceptance_criteria) >= 3
        assert len(spec.assumptions) >= 2
        assert len(spec.out_of_scope) >= 1

    def test_generate_with_intake_context(self) -> None:
        intake_context = {
            "languages": ["Python", "JavaScript"],
            "has_docker": True,
        }
        spec = generate_requirements(
            "Upload user documents and generate signed URLs",
            job_id="JOB-102",
            intake_context=intake_context,
        )
        assert any("Python" in a for a in spec.assumptions)
        assert any("Docker" in a for a in spec.assumptions)

    def test_parse_requirements_markdown_roundtrip(self) -> None:
        original = RequirementsSpec(
            job_id="JOB-201",
            title="Data Sync Script",
            approval_state=RequirementApprovalState.CLIENT_CONFIRMED.value,
            requirements=[
                RequirementItem(
                    id="req-1", title="Fetch API data", section="Input", completed=True
                ),
                RequirementItem(
                    id="req-2",
                    title="Transform payload",
                    section="Processing",
                    notes="uses pydantic",
                ),
                RequirementItem(id="req-3", title="Save to Postgres", section="Output"),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="ac-1", criterion="Syncs 500 records per second", completed=True
                ),
                AcceptanceCriterion(id="ac-2", criterion="Handles network timeout gracefully"),
            ],
            assumptions=["Postgres 16 is accessible"],
            out_of_scope=["Real-time websockets"],
            questions=["What is the rate limit on the source API?"],
            unresolved_decisions=["Retry policy backoff multiplier"],
            confirmed_at="2026-09-02T12:00:00+02:00",
            confirmed_by="Client Bob",
            version=2,
        )

        md = original.to_markdown()
        parsed = parse_requirements_markdown(md, job_id="JOB-201")

        assert parsed.job_id == "JOB-201"
        assert parsed.title == "Data Sync Script"
        assert parsed.approval_state == RequirementApprovalState.CLIENT_CONFIRMED.value
        assert parsed.version == 2
        assert parsed.confirmed_by == "Client Bob"
        assert len(parsed.requirements) == 3
        assert parsed.requirements[0].completed is True
        assert parsed.requirements[1].notes == "uses pydantic"
        assert parsed.requirements[1].section == "Processing"
        assert len(parsed.acceptance_criteria) == 2
        assert parsed.acceptance_criteria[0].completed is True
        assert parsed.assumptions == ["Postgres 16 is accessible"]
        assert parsed.out_of_scope == ["Real-time websockets"]
        assert parsed.questions == ["What is the rate limit on the source API?"]
        assert parsed.unresolved_decisions == ["Retry policy backoff multiplier"]


class TestRequirementsCLI:
    """Test CLI commands for freelance requirements."""

    def test_requirements_cli_generate_confirm_check_workflow(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        workspace_dir = tmp_path / "workspace"

        # Create job
        result = cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Acme Corp",
                "--description",
                "CSV cleanup script",
                "--source",
                "Useme",
            ],
        )
        assert result.exit_code == 0
        job_id = "JOB-001"

        # 1. Initial requirements generation from text
        result_req = cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--from-text",
                "Program ma pobierać CSV, usuwać duplikaty, sortować po dacie i generować Excel.",
            ],
        )
        assert result_req.exit_code == 0
        assert "REQUIREMENTS SPECIFICATION" in result_req.output
        assert "DRAFT" in result_req.output

        # Verify files created in workspace
        job_dirs = list((workspace_dir / "active").iterdir())
        assert len(job_dirs) == 1
        job_dir = job_dirs[0]

        json_file = job_dir / "analysis" / "requirements.json"
        req_md = job_dir / "client" / "requirements.md"
        checklist_md = job_dir / "work" / "checklist.md"

        assert json_file.exists()
        assert req_md.exists()
        assert checklist_md.exists()

        data = json.loads(json_file.read_text(encoding="utf-8"))
        assert data["approval_state"] == "DRAFT"
        assert len(data["requirements"]) >= 4

        # 2. Confirm requirements
        result_confirm = cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--confirm",
                "--confirmed-by",
                "Client Mark",
            ],
        )
        assert result_confirm.exit_code == 0
        data_confirmed = json.loads(json_file.read_text(encoding="utf-8"))
        assert data_confirmed["approval_state"] == "CLIENT_CONFIRMED"
        assert data_confirmed["confirmed_by"] == "Client Mark"

        # 3. Check item in checklist
        result_check = cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--check",
                "req-1",
            ],
        )
        assert result_check.exit_code == 0
        data_checked = json.loads(json_file.read_text(encoding="utf-8"))
        assert data_checked["requirements"][0]["completed"] is True

        # 4. View checklist only
        result_chk = cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--checklist",
            ],
        )
        assert result_chk.exit_code == 0
        assert "# Work Checklist" in result_chk.output
        assert "[x] [req-1]" in result_chk.output

        # 5. JSON output
        result_json = cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--json",
            ],
        )
        assert result_json.exit_code == 0
        parsed_out = json.loads(result_json.output)
        assert parsed_out["job_id"] == job_id
        assert parsed_out["approval_state"] == "CLIENT_CONFIRMED"

    def test_requirements_cli_job_not_found(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["requirements", "JOB-999"])
        assert result.exit_code != 0
        assert "not found" in result.output

