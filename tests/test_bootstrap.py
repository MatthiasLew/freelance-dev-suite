"""Tests for the client-project-bootstrap module and CLI integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.bootstrap import (
    ScaffoldResult,
    generate_template_files,
    get_template,
    list_templates,
    scaffold_project,
)
from packages.requirements.models import (
    AcceptanceCriterion,
    RequirementItem,
    RequirementsSpec,
)


class TestTemplates:
    """Test template registry and file generation."""

    def test_list_templates_coverage(self) -> None:
        templates = list_templates()
        assert len(templates) == 8
        names = {t.name for t in templates}
        assert "python-cli" in names
        assert "python-api" in names
        assert "python-desktop" in names
        assert "data-processing" in names
        assert "automation-script" in names
        assert "csharp-console" in names
        assert "csharp-desktop" in names
        assert "csharp-library" in names

    def test_get_template_valid_and_invalid(self) -> None:
        tmpl = get_template("python-cli")
        assert tmpl.name == "python-cli"
        assert tmpl.language == "Python"

        tmpl_upper = get_template("PYTHON-API")
        assert tmpl_upper.name == "python-api"

        try:
            get_template("unknown-template")
            raise AssertionError("Expected ValueError for unknown template")
        except ValueError as exc:
            assert "Available templates" in str(exc)

    def test_generate_python_cli_files(self) -> None:
        files = generate_template_files("python-cli", "my-tool", "Custom CLI tool")
        assert "pyproject.toml" in files
        assert "src/my_tool/__init__.py" in files
        assert "src/my_tool/cli.py" in files
        assert "tests/test_cli.py" in files
        assert ".ai-dev-tools.toml" in files
        assert ".gitignore" in files
        assert ".env.example" in files
        assert "docs/REQUIREMENTS.md" in files
        assert "docs/ACCEPTANCE.md" in files
        assert "docs/HANDOFF.md" in files

    def test_generate_python_api_files(self) -> None:
        files = generate_template_files("python-api", "user-service", "User REST API")
        assert "src/user_service/app.py" in files
        assert "tests/test_api.py" in files
        assert "fastapi" in files["pyproject.toml"]

    def test_generate_csharp_console_files(self) -> None:
        files = generate_template_files("csharp-console", "DataParser", "Console parser")
        assert "DataParser.sln" in files
        assert "src/DataParser/DataParser.csproj" in files
        assert "src/DataParser/Program.cs" in files
        assert "tests/DataParser.Tests/DataParser.Tests.csproj" in files
        assert "tests/DataParser.Tests/UnitTest1.cs" in files


class TestScaffolder:
    """Test project scaffolding logic and git integration."""

    def test_scaffold_project_files_and_git(self, tmp_path: Path) -> None:
        target = tmp_path / "test-cli-app"
        result: ScaffoldResult = scaffold_project(
            target_dir=target,
            template_name="python-cli",
            project_name="test-cli-app",
            description="Test CLI application",
            init_git=True,
        )

        assert Path(result.project_path) == target
        assert result.template_name == "python-cli"
        assert len(result.files_created) >= 8
        assert (target / "pyproject.toml").exists()
        assert (target / "src/test_cli_app/cli.py").exists()
        assert (target / "tests/test_cli.py").exists()

        if result.git_initialized:
            assert (target / ".git").exists()
            log = subprocess.run(
                ["git", "log", "-n", "1", "--oneline"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            assert log.returncode == 0
            assert "feat: initial project bootstrap" in log.stdout

    def test_scaffold_with_requirements_spec(self, tmp_path: Path) -> None:
        target = tmp_path / "req-app"
        spec = RequirementsSpec(
            job_id="JOB-500",
            title="CSV Parser",
            requirements=[
                RequirementItem(id="req-1", title="Parse CSV", section="Input"),
            ],
            acceptance_criteria=[
                AcceptanceCriterion(id="ac-1", criterion="Validates headers"),
            ],
        )

        scaffold_project(
            target_dir=target,
            template_name="data-processing",
            project_name="req-app",
            requirements_spec=spec,
            init_git=False,
        )

        req_doc = (target / "docs/REQUIREMENTS.md").read_text(encoding="utf-8")
        assert "JOB-500" in req_doc
        assert "Parse CSV" in req_doc

        acc_doc = (target / "docs/ACCEPTANCE.md").read_text(encoding="utf-8")
        assert "Validates headers" in acc_doc


class TestBootstrapCLI:
    """Test CLI commands: freelance templates, bootstrap, start."""

    def test_templates_command(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["templates"])
        assert result.exit_code == 0
        assert "python-cli" in result.output
        assert "python-api" in result.output
        assert "csharp-console" in result.output

    def test_bootstrap_standalone_command(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "standalone-api"
        result = cli_runner.invoke(
            main,
            [
                "bootstrap",
                "python-api",
                "--name",
                "standalone-api",
                "--path",
                str(dest),
                "--no-git",
            ],
        )
        assert result.exit_code == 0
        assert "Project bootstrapped" in result.output
        assert (dest / "src/standalone_api/app.py").exists()

    def test_bootstrap_standalone_json(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "json-app"
        result = cli_runner.invoke(
            main,
            [
                "bootstrap",
                "automation-script",
                "--path",
                str(dest),
                "--no-git",
                "--json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["template_name"] == "automation-script"
        assert len(data["files_created"]) >= 5

    def test_start_job_workflow(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        workspace_dir = tmp_path / "workspace"

        # 1. Create job
        create_res = cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Beta Corp",
                "--description",
                "Custom reporting pipeline",
                "--source",
                "Useme",
            ],
        )
        assert create_res.exit_code == 0
        job_id = "JOB-001"

        # 2. Generate requirements
        req_res = cli_runner.invoke(
            main,
            [
                "requirements",
                job_id,
                "--from-text",
                "Pobiera dane z bazy, czyści i generuje raport.",
            ],
        )
        assert req_res.exit_code == 0

        # 3. Start job with template
        start_res = cli_runner.invoke(
            main,
            [
                "start",
                job_id,
                "--template",
                "data-processing",
                "--no-git",
            ],
        )
        assert start_res.exit_code == 0
        assert f"Started {job_id}" in start_res.output

        # Verify job state updated
        job_dirs = list((workspace_dir / "active").iterdir())
        assert len(job_dirs) == 1
        job_dir = job_dirs[0]

        job_meta = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        assert job_meta["status"] == "IN_PROGRESS"
        assert (job_dir / "project").exists()
        assert (job_dir / "project/src").exists()
        assert (job_dir / "project/docs/REQUIREMENTS.md").exists()

    def test_start_job_json_output(self, cli_runner: CliRunner) -> None:
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Gamma",
                "--description",
                "FastAPI backend",
                "--source",
                "Direct",
            ],
        )
        result = cli_runner.invoke(
            main,
            [
                "start",
                "JOB-001",
                "--template",
                "python-api",
                "--no-git",
                "--json",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["job"]["id"] == "JOB-001"
        assert payload["job"]["status"] == "IN_PROGRESS"
        assert payload["scaffold"]["template_name"] == "python-api"

    def test_start_job_not_found(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["start", "JOB-999"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_bootstrap_invalid_template(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(main, ["bootstrap", "non-existent-tmpl"])
        assert result.exit_code != 0
        assert "Available templates" in result.output
