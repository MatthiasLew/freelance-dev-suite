"""Handoff package generator creating client-facing deliverables and release zip."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .checker import IGNORED_DIRECTORIES
from .models import HandoffPackage, QualityGateReport

if TYPE_CHECKING:
    from freelance_cli.models.job import Job
    from packages.requirements.models import RequirementsSpec


class HandoffPackager:
    """Creates delivery documents and clean release archive for client handoff."""

    def create_package(
        self,
        job: Job,
        project_dir: Path,
        output_dir: Path,
        requirements_spec: RequirementsSpec | None = None,
        quality_report: QualityGateReport | None = None,
        create_archive: bool = True,
    ) -> HandoffPackage:
        """Generate client documentation and build release.zip."""
        output_dir.mkdir(parents=True, exist_ok=True)
        created_files: list[str] = []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 1. README_CLIENT.md
        client_readme_path = output_dir / "README_CLIENT.md"
        client_readme_path.write_text(
            self._render_client_readme(job, project_dir, now_str),
            encoding="utf-8",
        )
        created_files.append("README_CLIENT.md")

        # 2. INSTALLATION.md
        install_path = output_dir / "INSTALLATION.md"
        install_path.write_text(
            self._render_installation_guide(job, project_dir),
            encoding="utf-8",
        )
        created_files.append("INSTALLATION.md")

        # 3. USER_GUIDE.md
        user_guide_path = output_dir / "USER_GUIDE.md"
        user_guide_path.write_text(
            self._render_user_guide(job, project_dir),
            encoding="utf-8",
        )
        created_files.append("USER_GUIDE.md")

        # 4. CHANGELOG.md
        changelog_path = output_dir / "CHANGELOG.md"
        changelog_content = self._extract_changelog(project_dir)
        changelog_path.write_text(changelog_content, encoding="utf-8")
        created_files.append("CHANGELOG.md")

        # 5. TEST_REPORT.md
        test_report_path = output_dir / "TEST_REPORT.md"
        test_report_path.write_text(
            self._render_test_report(job, quality_report, now_str),
            encoding="utf-8",
        )
        created_files.append("TEST_REPORT.md")

        # 6. REQUIREMENTS.md
        req_path = output_dir / "REQUIREMENTS.md"
        req_content = (
            requirements_spec.to_markdown()
            if requirements_spec
            else f"# Requirements — {job.id}\n\nNo specification was tracked."
        )
        req_path.write_text(req_content, encoding="utf-8")
        created_files.append("REQUIREMENTS.md")

        # 7. release.zip
        archive_path: Path | None = None
        if create_archive and project_dir.exists():
            zip_dest = output_dir / "release.zip"
            self._build_release_zip(project_dir, zip_dest)
            archive_path = zip_dest
            created_files.append("release.zip")

        return HandoffPackage(
            job_id=job.id,
            output_dir=str(output_dir.resolve()),
            created_files=created_files,
            archive_path=str(archive_path.resolve()) if archive_path else None,
        )

    def _render_client_readme(self, job: Job, project_dir: Path, timestamp: str) -> str:
        return f"""# Project Delivery — {job.id}

**Client:** {job.client}  
**Date:** {timestamp}  
**Status:** DELIVERED  

---

## Overview
{job.description}

## Deliverables in this Package
- **Source Code Archive:** `release.zip` (clean source files ready for deployment)
- **Setup & Installation:** [INSTALLATION.md](INSTALLATION.md)
- **User Guide:** [USER_GUIDE.md](USER_GUIDE.md)
- **Quality & Test Report:** [TEST_REPORT.md](TEST_REPORT.md)
- **Verified Requirements:** [REQUIREMENTS.md](REQUIREMENTS.md)
- **Change History:** [CHANGELOG.md](CHANGELOG.md)

## Support & Acceptance
Please review the delivered materials and verify operation against
[REQUIREMENTS.md](REQUIREMENTS.md).
If you have any questions or require support, please contact your developer.
"""

    def _render_installation_guide(self, job: Job, project_dir: Path) -> str:
        # If project has a README, extract instructions if available
        repo_readme = project_dir / "README.md"
        if repo_readme.exists():
            content = repo_readme.read_text(encoding="utf-8", errors="ignore")
            if "## Setup" in content or "## Installation" in content:
                return f"""# Installation Guide — {job.id}

{content}
"""

        return f"""# Installation Guide — {job.id}

## System Requirements
- Python >= 3.11 or .NET 8.0 SDK (depending on project stack)
- Git (optional)

## Setup Steps

1. Extract `release.zip` into your target directory.
2. Copy environment template:
   ```bash
   cp .env.example .env
   ```
3. Configure your API keys and variables in `.env`.
4. Install dependencies:
   - For Python:
     ```bash
     python -m venv .venv
     # Windows:
     .venv\\Scripts\\activate
     # Linux / macOS:
     source .venv/bin/activate

     pip install -e .
     ```
   - For .NET:
     ```bash
     dotnet restore
     dotnet build
     ```
"""

    def _render_user_guide(self, job: Job, project_dir: Path) -> str:
        return f"""# User & Operations Guide — {job.id}

## Getting Started
Ensure all steps from [INSTALLATION.md](INSTALLATION.md) have been performed.

## Running the Application
Refer to the command-line help or application launcher:

```bash
# Example CLI execution:
python -m <package_name> --help
```

## Configuration
Application behavior can be customized via `.env` file settings and command-line flags.

## Troubleshooting
- Check that `.env` contains valid credentials.
- Verify network connectivity if external APIs or databases are utilized.
"""

    def _extract_changelog(self, project_dir: Path) -> str:
        cl_path = project_dir / "CHANGELOG.md"
        if cl_path.exists():
            return cl_path.read_text(encoding="utf-8", errors="ignore")
        return "# Changelog\n\n## 1.0.0\n\n- Initial client release.\n"

    def _render_test_report(
        self,
        job: Job,
        report: QualityGateReport | None,
        timestamp: str,
    ) -> str:
        if report is None:
            return f"""# Quality & Test Report — {job.id}

**Date:** {timestamp}  
**Status:** NOT RUN  
"""

        lines = [
            f"# Quality & Test Report — {job.id}",
            "",
            f"**Date:** {timestamp}  ",
            f"**Overall Quality Gate Status:** `{report.overall_status}`  ",
            "",
            "## Quality Gate Checklist",
            "",
            "| Check | Status | Details |",
            "|---|---|---|",
        ]
        for c in report.checks:
            icon = "✅" if c.status == "PASS" else ("⚠️" if c.status == "WARN" else "❌")
            lines.append(f"| {c.name} | {icon} `{c.status}` | {c.details} |")

        lines.append("")
        all_issues = [(c.name, iss) for c in report.checks for iss in c.issues]
        if all_issues:
            lines.append("## Identified Issues")
            for name, iss in all_issues:
                lines.append(f"- ❌ **{name}:** {iss}")
            lines.append("")

        all_warns = [(c.name, w) for c in report.checks for w in c.warnings]
        if all_warns:
            lines.append("## Warnings / Notes")
            for name, w in all_warns:
                lines.append(f"- ⚠️ **{name}:** {w}")
            lines.append("")

        return "\n".join(lines)

    def _build_release_zip(self, project_dir: Path, zip_dest: Path) -> None:
        """Create clean zip file of project directory, skipping temp files and secrets."""
        with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in project_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(project_dir)
                # Skip ignored folders
                if any(part in IGNORED_DIRECTORIES for part in rel.parts):
                    continue
                # Skip actual .env files (keep .env.example)
                if file_path.name == ".env":
                    continue
                # Skip zip if inside project_dir
                if file_path.resolve() == zip_dest.resolve():
                    continue

                zf.write(file_path, arcname=str(rel))
