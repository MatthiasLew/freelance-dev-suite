"""Tests for the bug-report-to-reproduction module and CLI integration."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.bugs import (
    BugProcessor,
    BugReport,
    BugSeverity,
    BugStatus,
)


class TestBugModels:
    """Test BugReport serialization, markdown generation, and lifecycle."""

    def test_bug_report_serialization(self) -> None:
        report = BugReport(
            id="BUG-001",
            job_id="JOB-001",
            title="CSV Parser crash",
            raw_description="Fails on empty rows",
            status=BugStatus.REPORTED.value,
            severity=BugSeverity.HIGH.value,
            steps_to_reproduce=["Upload empty CSV", "Click Run"],
            expected_behavior="Return empty list",
            actual_behavior="IndexError",
            environment={"OS": "Windows", "Python": "3.11"},
            error_logs="IndexError: list index out of range",
            questions_for_client=["What file encoding?"],
            regression_test_file="tests/test_empty_csv.py",
        )

        data = report.to_dict()
        assert data["id"] == "BUG-001"
        assert data["severity"] == "HIGH"
        assert len(data["steps_to_reproduce"]) == 2

        restored = BugReport.from_dict(data)
        assert restored.id == report.id
        assert restored.steps_to_reproduce == report.steps_to_reproduce
        assert restored.regression_test_file == "tests/test_empty_csv.py"

    def test_bug_report_status_change(self) -> None:
        report = BugReport(
            id="BUG-001",
            job_id="JOB-001",
            title="Test",
            raw_description="Desc",
        )
        assert report.status == BugStatus.REPORTED.value

        report.change_status("FIX_IN_PROGRESS")
        assert report.status == BugStatus.FIX_IN_PROGRESS.value

        try:
            report.change_status("INVALID_STATUS")
            raise AssertionError("Expected ValueError for invalid status")
        except ValueError as exc:
            assert "Invalid bug status" in str(exc)

    def test_bug_report_markdown_and_repro(self) -> None:
        report = BugReport(
            id="BUG-001",
            job_id="JOB-001",
            title="Login timeout",
            raw_description="Timeout on login",
            steps_to_reproduce=["Open /login", "Wait 5s"],
            expected_behavior="Redirect to dashboard",
            actual_behavior="504 Gateway Timeout",
            questions_for_client=["Which browser?"],
        )

        md = report.to_markdown()
        assert "BUG-001" in md
        assert "Login timeout" in md
        assert "Open /login" in md
        assert "504 Gateway Timeout" in md

        q_md = report.to_questions_markdown()
        assert "Which browser?" in q_md

        py_repro = report.to_repro_script("python")
        assert "def reproduce()" in py_repro
        assert "BUG-001" in py_repro

        cs_repro = report.to_repro_script("csharp")
        assert "namespace BugReproduction" in cs_repro


class TestBugProcessor:
    """Test deterministic report parsing, question generation, and file saving."""

    def test_parse_vague_bug_generates_questions(self) -> None:
        processor = BugProcessor()
        raw = "Aplikacja nie działa, wyskakuje błąd."
        report = processor.parse_raw_report(
            raw_text=raw,
            job_id="JOB-001",
            bug_id="BUG-001",
        )

        assert report.id == "BUG-001"
        assert report.status == BugStatus.NEEDS_INFO.value
        assert len(report.questions_for_client) >= 2
        # Verify questions ask for steps and error details
        joined_q = " ".join(report.questions_for_client)
        assert "kroki" in joined_q or "treść błędu" in joined_q

    def test_parse_detailed_bug_with_traceback(self) -> None:
        processor = BugProcessor()
        raw = """Błąd podczas eksportu raportu PDF na Windowsie

Kroki:
1. Wchodzę w zakładkę Raporty
2. Wybieram zakres dat
3. Klikam Generuj PDF

Oczekiwane: Pobiera się plik PDF
Faktyczne: Aplikacja crashuje z błędem:

Traceback (most recent call last):
  File "app.py", line 42, in export_pdf
    pdf.save(dest)
FileNotFoundError: [Errno 2] No such file or directory: 'output.pdf'
"""
        report = processor.parse_raw_report(
            raw_text=raw,
            job_id="JOB-001",
            bug_id="BUG-001",
            severity="HIGH",
        )

        assert report.id == "BUG-001"
        assert len(report.steps_to_reproduce) == 3
        assert "Traceback" in report.error_logs
        assert "FileNotFoundError" in report.error_logs
        assert report.environment.get("OS") == "Windows"
        assert report.status == BugStatus.REPORTED.value

    def test_save_load_and_list_bugs(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "active" / "JOB-001-test"
        job_dir.mkdir(parents=True, exist_ok=True)

        processor = BugProcessor()
        assert processor.next_bug_id(job_dir) == "BUG-001"

        bug1 = BugReport(
            id="BUG-001",
            job_id="JOB-001",
            title="First bug",
            raw_description="Desc 1",
            questions_for_client=["Question 1"],
        )
        saved = processor.save_bug(bug1, job_dir)
        assert "json" in saved
        assert "summary" in saved
        assert "questions" in saved
        assert "repro" in saved
        assert (job_dir / "work" / "bugs" / "BUG-001.json").exists()

        assert processor.next_bug_id(job_dir) == "BUG-002"

        bug2 = BugReport(
            id="BUG-002",
            job_id="JOB-001",
            title="Second bug",
            raw_description="Desc 2",
        )
        processor.save_bug(bug2, job_dir)

        # List
        bugs = processor.list_bugs(job_dir)
        assert len(bugs) == 2
        assert [b.id for b in bugs] == ["BUG-001", "BUG-002"]

        # Load
        loaded = processor.load_bug(job_dir, "BUG-001")
        assert loaded is not None
        assert loaded.title == "First bug"


class TestBugCLI:
    """Test CLI commands: freelance bug add, list, show, status, repro, test."""

    def test_cli_bug_lifecycle(self, cli_runner: CliRunner) -> None:
        # 1. Create job
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Umbrella",
                "--description",
                "Data pipeline",
                "--source",
                "Direct",
            ],
        )
        job_id = "JOB-001"

        # 2. Add bug report
        add_res = cli_runner.invoke(
            main,
            [
                "bug",
                "add",
                job_id,
                "--title",
                "Parser crashes on empty line",
                "--from-text",
                "1. Otwieram plik\n2. Parsuje\nWyskakuje IndexError",
                "--severity",
                "HIGH",
            ],
        )
        assert add_res.exit_code == 0
        assert "Added bug report: BUG-001" in add_res.output

        # 3. List bugs
        list_res = cli_runner.invoke(main, ["bug", "list", job_id])
        assert list_res.exit_code == 0
        assert "BUG-001" in list_res.output
        assert "Parser crashes" in list_res.output

        # 4. Show bug
        show_res = cli_runner.invoke(main, ["bug", "show", job_id, "BUG-001"])
        assert show_res.exit_code == 0
        assert "# Bug Report: BUG-001" in show_res.output

        # 5. Show questions
        q_res = cli_runner.invoke(main, ["bug", "show", job_id, "BUG-001", "--questions"])
        assert q_res.exit_code == 0

        # 6. Show repro script
        repro_res = cli_runner.invoke(main, ["bug", "repro", job_id, "BUG-001"])
        assert repro_res.exit_code == 0
        assert "def reproduce()" in repro_res.output

        # 7. Update status
        status_res = cli_runner.invoke(
            main,
            ["bug", "status", job_id, "BUG-001", "FIX_IN_PROGRESS"],
        )
        assert status_res.exit_code == 0
        assert "FIX_IN_PROGRESS" in status_res.output

        # 8. Link regression test
        test_res = cli_runner.invoke(
            main,
            [
                "bug",
                "test",
                job_id,
                "BUG-001",
                "--file",
                "tests/test_bug_001.py",
            ],
        )
        assert test_res.exit_code == 0
        assert "REGRESSION_TESTED" in test_res.output

    def test_cli_bug_json_output(self, cli_runner: CliRunner) -> None:
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Wayne",
                "--description",
                "Security tool",
                "--source",
                "Useme",
            ],
        )
        job_id = "JOB-001"

        add_res = cli_runner.invoke(
            main,
            [
                "bug",
                "add",
                job_id,
                "--from-text",
                "Nie działa",
                "--json",
            ],
        )
        assert add_res.exit_code == 0
        data = json.loads(add_res.output)
        assert data["bug"]["id"] == "BUG-001"
        assert "summary" in data["files"]

        list_res = cli_runner.invoke(main, ["bug", "list", job_id, "--json"])
        assert list_res.exit_code == 0
        list_data = json.loads(list_res.output)
        assert len(list_data) == 1
        assert list_data[0]["id"] == "BUG-001"

    def test_cli_bug_not_found(self, cli_runner: CliRunner) -> None:
        res = cli_runner.invoke(main, ["bug", "show", "JOB-999", "BUG-001"])
        assert res.exit_code != 0
        assert "not found" in res.output
