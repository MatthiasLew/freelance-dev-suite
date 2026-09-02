"""Project scaffolding orchestrator with git initialization and ai-dev integration."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .templates import generate_template_files, get_template

if TYPE_CHECKING:
    from packages.requirements.models import RequirementsSpec


@dataclass
class ScaffoldResult:
    """Outcome of scaffolding a project from a template."""

    project_path: str
    template_name: str
    files_created: list[str] = field(default_factory=list)
    git_initialized: bool = False
    bootstrap_executed: bool = False
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        git_status = "Initialized" if self.git_initialized else "Skipped / Already git repo"
        boot_status = "Executed" if self.bootstrap_executed else "Not run"
        lines: list[str] = [
            f"Project Path:        {self.project_path}",
            f"Template:            {self.template_name}",
            f"Files Created:       {len(self.files_created)}",
            f"Git Repository:      {git_status}",
            f"ai-dev Bootstrap:    {boot_status}",
        ]
        if self.issues:
            lines.append("Warnings / Issues:")
            for issue in self.issues:
                lines.append(f"  • {issue}")
        return "\n".join(lines)


class ProjectScaffolder:
    """Orchestrates project directory structure creation and tool setup."""

    def scaffold(
        self,
        target_dir: Path,
        template_name: str,
        project_name: str = "",
        description: str = "",
        requirements_spec: RequirementsSpec | None = None,
        init_git: bool = True,
        run_bootstrap: bool = False,
    ) -> ScaffoldResult:
        """Create project files from template and set up git and dev environment."""
        target_dir = target_dir.expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        tmpl = get_template(template_name)
        proj_name = project_name.strip() or target_dir.name or "project"
        files_dict = generate_template_files(
            template_name=tmpl.name,
            project_name=proj_name,
            description=description,
            requirements_spec=requirements_spec,
        )

        files_created: list[str] = []
        issues: list[str] = []

        # Write files
        for rel_path, content in files_dict.items():
            dest = target_dir / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_text(content, encoding="utf-8")
                files_created.append(rel_path)
            except OSError as exc:
                issues.append(f"Failed to write {rel_path}: {exc}")

        # Git initialization
        git_initialized = False
        if init_git and not (target_dir / ".git").exists():
            git_exe = shutil.which("git")
            if git_exe:
                try:
                    subprocess.run(
                        [git_exe, "init", "-b", "master"],
                        cwd=target_dir,
                        capture_output=True,
                        check=False,
                    )
                    subprocess.run(
                        [git_exe, "add", "."],
                        cwd=target_dir,
                        capture_output=True,
                        check=False,
                    )
                    subprocess.run(
                        [
                            git_exe,
                            "commit",
                            "-m",
                            f"feat: initial project bootstrap ({tmpl.name})",
                        ],
                        cwd=target_dir,
                        capture_output=True,
                        check=False,
                    )
                    git_initialized = True
                except Exception as exc:
                    issues.append(f"Git init error: {exc}")
            else:
                issues.append("git command not found on PATH; skipped git init")

        # Optional ai-dev bootstrap invocation
        bootstrap_executed = False
        if run_bootstrap:
            from packages.intake.analyzer import AIDevIntegrationError, _ai_dev_command

            try:
                cmd = [*_ai_dev_command(), "--project", str(target_dir), "--json", "bootstrap"]
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if res.returncode in {0, 1}:
                    bootstrap_executed = True
                else:
                    issues.append(f"ai-dev bootstrap returned code {res.returncode}")
            except (AIDevIntegrationError, OSError, json.JSONDecodeError) as exc:
                issues.append(f"ai-dev bootstrap skipped: {exc}")

        return ScaffoldResult(
            project_path=str(target_dir),
            template_name=tmpl.name,
            files_created=files_created,
            git_initialized=git_initialized,
            bootstrap_executed=bootstrap_executed,
            issues=issues,
        )


def scaffold_project(
    target_dir: Path,
    template_name: str,
    project_name: str = "",
    description: str = "",
    requirements_spec: RequirementsSpec | None = None,
    init_git: bool = True,
    run_bootstrap: bool = False,
) -> ScaffoldResult:
    """Convenience functional interface for project scaffolding."""
    return ProjectScaffolder().scaffold(
        target_dir=target_dir,
        template_name=template_name,
        project_name=project_name,
        description=description,
        requirements_spec=requirements_spec,
        init_git=init_git,
        run_bootstrap=run_bootstrap,
    )
