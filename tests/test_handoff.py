"""Tests for the client-handoff module, Quality Gate, and CLI integration."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from freelance_cli.models.job import Job
from packages.handoff import (
    CheckStatus,
    GateStatus,
    HandoffPackager,
    QualityGateChecker,
)
from packages.requirements.models import (
    AcceptanceCriterion,
    RequirementApprovalState,
    RequirementItem,
    RequirementsSpec,
)


class TestQualityGateChecker:
    """Test individual and aggregated quality gate checks."""

    def test_check_requirements_pass_and_fail(self) -> None:
        checker = QualityGateChecker()

        # None spec
        res_none = checker.check_requirements(None)
        assert res_none.status == CheckStatus.WARN.value

        # Incomplete spec
        incomplete_spec = RequirementsSpec(
            job_id="JOB-100",
            title="App",
            approval_state=RequirementApprovalState.CLIENT_CONFIRMED.value,
            requirements=[
                RequirementItem(id="req-1", title="Task 1", completed=True),
                RequirementItem(id="req-2", title="Task 2", completed=False),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-1", criterion="Must work", completed=True),
            ],
        )
        res_fail = checker.check_requirements(incomplete_spec)
        assert res_fail.status == CheckStatus.FAIL.value
        assert len(res_fail.issues) == 1
        assert "req-2" in res_fail.issues[0]

        # Complete spec
        complete_spec = RequirementsSpec(
            job_id="JOB-100",
            title="App",
            approval_state=RequirementApprovalState.CLIENT_CONFIRMED.value,
            requirements=[
                RequirementItem(id="req-1", title="Task 1", completed=True),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-1", criterion="Must work", completed=True),
            ],
        )
        res_pass = checker.check_requirements(complete_spec)
        assert res_pass.status == CheckStatus.PASS.value
        assert not res_pass.issues

    def test_check_code_hygiene(self, tmp_path: Path) -> None:
        checker = QualityGateChecker()

        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        src_file = proj_dir / "app.py"

        # Dirty code with breakpoint and TODO
        src_file.write_text("import pdb\n# TODO: fix this\nbreakpoint()\n", encoding="utf-8")
        res_dirty = checker.check_code_hygiene(proj_dir)
        assert res_dirty.status == CheckStatus.FAIL.value
        assert len(res_dirty.issues) >= 1
        assert len(res_dirty.warnings) >= 1

        # Clean code
        src_file.write_text("def hello() -> str:\n    return 'clean code'\n", encoding="utf-8")
        res_clean = checker.check_code_hygiene(proj_dir)
        assert res_clean.status == CheckStatus.PASS.value
        assert not res_clean.issues

    def test_check_secrets(self, tmp_path: Path) -> None:
        checker = QualityGateChecker()

        proj_dir = tmp_path / "proj_sec"
        proj_dir.mkdir()
        secret_file = proj_dir / "config.py"

        # Leaked key
        secret_file.write_text('OPENAI_KEY = "sk-1234567890abcdef1234567890"\n', encoding="utf-8")
        res_sec = checker.check_secrets(proj_dir)
        assert res_sec.status == CheckStatus.FAIL.value
        assert len(res_sec.issues) >= 1

        # Clean config
        clean_code = 'import os\nOPENAI_KEY = os.getenv("OPENAI_KEY")\n'
        secret_file.write_text(clean_code, encoding="utf-8")
        res_clean = checker.check_secrets(proj_dir)
        assert res_clean.status == CheckStatus.PASS.value
        assert not res_clean.issues

    def test_check_documentation(self, tmp_path: Path) -> None:
        checker = QualityGateChecker()

        proj_dir = tmp_path / "proj_doc"
        proj_dir.mkdir()

        # Missing docs
        res_missing = checker.check_documentation(proj_dir)
        assert res_missing.status == CheckStatus.WARN.value

        # Complete docs
        (proj_dir / "README.md").write_text("# Readme", encoding="utf-8")
        (proj_dir / "CHANGELOG.md").write_text("# Changelog", encoding="utf-8")
        (proj_dir / "docs").mkdir()
        res_ok = checker.check_documentation(proj_dir)
        assert res_ok.status == CheckStatus.PASS.value

    def test_run_all_checks_summary(self, tmp_path: Path) -> None:
        checker = QualityGateChecker()
        proj_dir = tmp_path / "app"
        proj_dir.mkdir()
        (proj_dir / "README.md").write_text("# Readme", encoding="utf-8")
        (proj_dir / "CHANGELOG.md").write_text("# Changelog", encoding="utf-8")
        (proj_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")

        report = checker.run_all_checks(
            job_id="JOB-001",
            project_dir=proj_dir,
            requirements_spec=None,
            skip_technical=True,
        )

        assert report.job_id == "JOB-001"
        assert report.overall_status in {
            GateStatus.PASS.value,
            GateStatus.PASS_WITH_WARNINGS.value,
        }
        assert "FINAL QUALITY GATE REPORT" in report.summary()


class TestHandoffPackager:
    """Test creation of client handoff documentation and release archive."""

    def test_create_package_and_release_zip(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "src").mkdir()
        (project_dir / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
        (project_dir / ".env").write_text("SECRET=12345", encoding="utf-8")
        (project_dir / ".env.local").write_text("SECRET=local", encoding="utf-8")
        (project_dir / ".env.production").write_text("SECRET=prod", encoding="utf-8")
        (project_dir / ".env.example").write_text("SECRET=", encoding="utf-8")

        output_dir = tmp_path / "handoff"

        job = Job(
            id="JOB-001",
            client="Acme Corp",
            description="Client portal backend",
        )

        packager = HandoffPackager()
        package = packager.create_package(
            job=job,
            project_dir=project_dir,
            output_dir=output_dir,
            requirements_spec=None,
            quality_report=None,
            create_archive=True,
        )

        assert package.job_id == "JOB-001"
        assert len(package.created_files) == 7
        assert (output_dir / "README_CLIENT.md").exists()
        assert (output_dir / "INSTALLATION.md").exists()
        assert (output_dir / "USER_GUIDE.md").exists()
        assert (output_dir / "CHANGELOG.md").exists()
        assert (output_dir / "TEST_REPORT.md").exists()
        assert (output_dir / "REQUIREMENTS.md").exists()
        assert (output_dir / "release.zip").exists()

        # Check that release.zip includes src/app.py and .env.example, but excludes .env
        with zipfile.ZipFile(output_dir / "release.zip", "r") as zf:
            namelist = zf.namelist()
            assert any("app.py" in n for n in namelist)
            assert any(".env.example" in n for n in namelist)
            assert not any(
                n == ".env"
                or n.endswith("/.env")
                or n.endswith(".env.local")
                or n.endswith(".env.production")
                for n in namelist
            )


class TestHandoffCLI:
    """Test CLI integration for freelance handoff and finish."""

    def test_handoff_and_finish_lifecycle(self, cli_runner: CliRunner) -> None:
        # 1. Create job
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Globex",
                "--description",
                "Analytics Service",
                "--source",
                "Direct",
            ],
        )
        job_id = "JOB-001"

        # 2. Add requirements and confirm
        cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--from-text",
                "Implement analytics dashboard.",
                "--confirm",
            ],
        )

        # Mark item completed
        cli_runner.invoke(main, ["requirements", job_id, "--check", "1"])
        cli_runner.invoke(main, ["requirements", job_id, "--check", "ac-1"])

        # 3. Start project
        cli_runner.invoke(
            main,
            [
                "start",
                job_id,
                "--template",
                "python-cli",
                "--no-git",
            ],
        )

        # 4. Run handoff
        res_handoff = cli_runner.invoke(
            main,
            [
                "handoff",
                job_id,
                "--skip-technical",
            ],
        )
        assert res_handoff.exit_code == 0
        assert "FINAL QUALITY GATE" in res_handoff.output
        assert "Handoff deliverables created successfully" in res_handoff.output

        from freelance_cli.cli import _get_manager

        mgr = _get_manager()
        job_dir = mgr.get_job_dir(job_id)
        assert job_dir is not None
        assert (job_dir / "handoff" / "README_CLIENT.md").exists()
        assert (job_dir / "handoff" / "release.zip").exists()

        # Verify status is READY_FOR_HANDOFF
        job_data = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        assert job_data["status"] == "READY_FOR_HANDOFF"

        # 5. Finish and archive job
        res_finish = cli_runner.invoke(
            main,
            [
                "finish",
                job_id,
                "--archive",
                "--notes",
                "Client accepted delivery.",
            ],
        )
        assert res_finish.exit_code == 0
        assert f"Job {job_id} successfully closed!" in res_finish.output

        # Verify job is moved to finished/
        archived_dir = mgr.get_job_dir(job_id)
        assert archived_dir is not None
        assert "finished" in str(archived_dir)
        finished_job = json.loads(
            (archived_dir / "job.json").read_text(encoding="utf-8")
        )
        assert finished_job["status"] == "DELIVERED"
        assert "Client accepted delivery" in finished_job["notes"]

    def test_handoff_blocked_without_force(self, cli_runner: CliRunner) -> None:
        create_res = cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Initech",
                "--description",
                "Buggy tool",
                "--source",
                "Direct",
            ],
        )
        assert create_res.exit_code == 0
        job_id = "JOB-001"
        cli_runner.invoke(
            main,
            [
                "start",
                job_id,
                "--template",
                "python-cli",
                "--no-git",
            ],
        )

        from freelance_cli.cli import _get_manager

        mgr = _get_manager()
        job_dir = mgr.get_job_dir(job_id)
        assert job_dir is not None
        # Introduce a critical secret in project
        (job_dir / "project" / "leak.py").write_text(
            'API_KEY = "AKIA1234567890ABCDEF"\n', encoding="utf-8"
        )

        res = cli_runner.invoke(main, ["handoff", job_id, "--skip-technical"])
        assert res.exit_code != 0
        assert "BLOCKED" in res.output

        # With --force it succeeds
        res_force = cli_runner.invoke(
            main, ["handoff", job_id, "--skip-technical", "--force"]
        )
        assert res_force.exit_code == 0
        assert "Handoff deliverables created" in res_force.output

    def test_finish_not_found(self, cli_runner: CliRunner) -> None:
        res = cli_runner.invoke(main, ["finish", "JOB-999"])
        assert res.exit_code != 0
        assert "not found" in res.output
