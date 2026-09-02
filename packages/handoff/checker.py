"""Quality Gate verification checks for freelance project handoff."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .models import CheckStatus, GateStatus, QualityCheckResult, QualityGateReport

if TYPE_CHECKING:
    from packages.requirements.models import RequirementsSpec

IGNORED_DIRECTORIES = {
    ".ai",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vs",
    "bin",
    "build",
    "dist",
    "node_modules",
    "obj",
    "venv",
}

SOURCE_EXTENSIONS = {
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".ts",
    ".tsx",
}

SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"), "Private cryptographic key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "GitHub Personal Access Token"),
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "API Secret Token (OpenAI/Anthropic style)"),
    (
        re.compile(
            r"""(?i)(?:api_key|apikey|secret_key|client_secret)\s*[:=]\s*['"][a-zA-Z0-9_\-]{16,}['"]"""
        ),
        "Hardcoded API Key / Secret",
    ),
]

DEBUG_PATTERNS = [
    (re.compile(r"\bbreakpoint\(\)"), "breakpoint() debug call"),
    (re.compile(r"\bpdb\.set_trace\(\)"), "pdb.set_trace() debug call"),
    (re.compile(r"\bdebugger;"), "debugger; statement"),
    (re.compile(r"\bimport pdb\b"), "import pdb debug module"),
]

TODO_PATTERNS = [
    (re.compile(r"\b(?:TODO|FIXME|XXX|HACK)\b:?\s*(.*)"), "Unresolved TODO / FIXME item"),
]


class QualityGateChecker:
    """Runs comprehensive final validation before project delivery."""

    def check_requirements(
        self, requirements_spec: RequirementsSpec | None
    ) -> QualityCheckResult:
        """Validate that all requirements and acceptance criteria are completed."""
        if requirements_spec is None:
            return QualityCheckResult(
                category="Requirements",
                name="Requirements Checklist",
                status=CheckStatus.WARN.value,
                details="No requirements specification found for this job.",
                warnings=["Specification was not generated prior to handoff."],
            )

        done, total, pct = requirements_spec.progress
        if total == 0:
            return QualityCheckResult(
                category="Requirements",
                name="Requirements Checklist",
                status=CheckStatus.WARN.value,
                details="Specification contains 0 checklist items.",
                warnings=["Specification has no tracked requirements or acceptance criteria."],
            )

        uncompleted_reqs = [
            f"`{r.id}`: {r.title}" for r in requirements_spec.requirements if not r.completed
        ]
        uncompleted_acs = [
            f"`{ac.id}`: {ac.criterion}"
            for ac in requirements_spec.acceptance_criteria
            if not ac.completed
        ]

        issues: list[str] = []
        if uncompleted_reqs:
            issues.extend([f"Incomplete requirement {r}" for r in uncompleted_reqs])
        if uncompleted_acs:
            issues.extend([f"Unverified acceptance criterion {ac}" for ac in uncompleted_acs])

        warnings: list[str] = []
        if requirements_spec.approval_state != "CLIENT_CONFIRMED":
            warnings.append(
                f"Requirements state is `{requirements_spec.approval_state}` "
                "(not marked as CLIENT_CONFIRMED)."
            )

        status = CheckStatus.FAIL.value if issues else (
            CheckStatus.WARN.value if warnings else CheckStatus.PASS.value
        )
        details = f"{done}/{total} completed ({pct:.0f}%) [{requirements_spec.approval_state}]"

        return QualityCheckResult(
            category="Requirements",
            name="Requirements Checklist",
            status=status,
            details=details,
            issues=issues,
            warnings=warnings,
        )

    def check_git_cleanliness(self, project_dir: Path) -> QualityCheckResult:
        """Check for uncommitted files or dirty working tree in git."""
        if not (project_dir / ".git").exists():
            return QualityCheckResult(
                category="Git",
                name="Git Repository Status",
                status=CheckStatus.WARN.value,
                details="Directory is not a git repository.",
                warnings=["Project is not tracked in Git."],
            )

        git_exe = shutil.which("git")
        if not git_exe:
            return QualityCheckResult(
                category="Git",
                name="Git Repository Status",
                status=CheckStatus.WARN.value,
                details="Git executable not found on PATH.",
            )

        res = subprocess.run(
            [git_exe, "status", "--porcelain"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=False,
        )

        uncommitted = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if uncommitted:
            return QualityCheckResult(
                category="Git",
                name="Git Repository Status",
                status=CheckStatus.WARN.value,
                details=f"{len(uncommitted)} uncommitted file(s) found.",
                warnings=[f"Uncommitted: {item}" for item in uncommitted[:10]],
            )

        return QualityCheckResult(
            category="Git",
            name="Git Repository Status",
            status=CheckStatus.PASS.value,
            details="Working tree clean, no uncommitted changes.",
        )

    def check_code_hygiene(self, project_dir: Path) -> QualityCheckResult:
        """Check source code for leftover debug statements and TODO markers."""
        debug_found: list[str] = []
        todo_found: list[str] = []

        for file_path in project_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(project_dir)
            if any(part in IGNORED_DIRECTORIES for part in rel.parts):
                continue
            if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            try:
                lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line_no, line in enumerate(lines, start=1):
                    # Check debug statements
                    for pat, label in DEBUG_PATTERNS:
                        if pat.search(line):
                            debug_found.append(f"{rel}:{line_no} — {label}")
                    # Check TODOs
                    for pat, _ in TODO_PATTERNS:
                        m = pat.search(line)
                        if m:
                            snippet = line.strip()[:60]
                            todo_found.append(f"{rel}:{line_no} — {snippet}")
            except OSError:
                continue

        issues: list[str] = []
        warnings: list[str] = []

        if debug_found:
            issues.extend(debug_found)
        if todo_found:
            warnings.extend(todo_found[:15])

        status = CheckStatus.FAIL.value if issues else (
            CheckStatus.WARN.value if warnings else CheckStatus.PASS.value
        )
        details = (
            f"{len(debug_found)} debug call(s), {len(todo_found)} TODO(s) found"
        )

        return QualityCheckResult(
            category="Hygiene",
            name="Code Hygiene & Debug Code",
            status=status,
            details=details,
            issues=issues,
            warnings=warnings,
        )

    def check_secrets(self, project_dir: Path) -> QualityCheckResult:
        """Scan project files for hardcoded API keys, passwords, and private keys."""
        secrets_found: list[str] = []

        for file_path in project_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(project_dir)
            if any(part in IGNORED_DIRECTORIES for part in rel.parts):
                continue
            if file_path.name in {".env", ".env.example"}:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for pat, label in SECRET_PATTERNS:
                    if pat.search(content):
                        secrets_found.append(f"{rel} contains potential {label}")
            except OSError:
                continue

        status = CheckStatus.FAIL.value if secrets_found else CheckStatus.PASS.value
        details = (
            f"{len(secrets_found)} potential secret(s) found"
            if secrets_found
            else "No hardcoded secrets detected"
        )

        return QualityCheckResult(
            category="Security",
            name="Secrets & Credential Scan",
            status=status,
            details=details,
            issues=secrets_found,
        )

    def check_documentation(self, project_dir: Path) -> QualityCheckResult:
        """Verify presence of core documentation files."""
        required = ["README.md", "CHANGELOG.md"]
        missing = [req for req in required if not (project_dir / req).exists()]

        warnings: list[str] = []
        if not (project_dir / "docs").exists():
            warnings.append("No docs/ directory found.")

        if missing:
            return QualityCheckResult(
                category="Documentation",
                name="Project Documentation",
                status=CheckStatus.WARN.value,
                details=f"Missing standard files: {', '.join(missing)}",
                warnings=[f"Missing {f}" for f in missing] + warnings,
            )

        return QualityCheckResult(
            category="Documentation",
            name="Project Documentation",
            status=CheckStatus.PASS.value,
            details="README.md and CHANGELOG.md present.",
            warnings=warnings,
        )

    def check_technical_health(self, project_dir: Path) -> QualityCheckResult:
        """Run technical validation via ai-dev check or local test runner."""
        from packages.intake.analyzer import AIDevIntegrationError, _ai_dev_command

        try:
            cmd = [
                *_ai_dev_command(),
                "--project",
                str(project_dir),
                "--json",
                "check",
                "--no-cache",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode in {0, 1}:
                data = json.loads(res.stdout)
                summary = data.get("summary", {})
                passed = summary.get("tests_passed", 0)
                failed = summary.get("tests_failed", 0)
                status_str = data.get("status", "unknown")

                if failed > 0 or status_str == "failed":
                    return QualityCheckResult(
                        category="Technical",
                        name="Test & Quality Check",
                        status=CheckStatus.FAIL.value,
                        details=f"Tests: {passed} passed, {failed} failed (Status: {status_str})",
                        issues=[f"{failed} tests failed in validation."],
                    )
                return QualityCheckResult(
                    category="Technical",
                    name="Test & Quality Check",
                    status=CheckStatus.PASS.value,
                    details=f"Validation passed ({passed} tests passed, 0 failed)",
                )
        except (AIDevIntegrationError, OSError, json.JSONDecodeError):
            pass

        # Fallback: run pytest if pyproject.toml / tests present
        if (project_dir / "tests").exists() and (project_dir / "pyproject.toml").exists():
            res = subprocess.run(
                ["pytest", "-q"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                return QualityCheckResult(
                    category="Technical",
                    name="Test & Quality Check",
                    status=CheckStatus.PASS.value,
                    details="pytest executed and passed cleanly.",
                )
            return QualityCheckResult(
                category="Technical",
                name="Test & Quality Check",
                status=CheckStatus.FAIL.value,
                details=f"pytest failed with returncode {res.returncode}.",
                issues=[res.stdout.strip() or res.stderr.strip()],
            )

        return QualityCheckResult(
            category="Technical",
            name="Test & Quality Check",
            status=CheckStatus.PASS.value,
            details="Technical check skipped (no test suite configured).",
        )

    def run_all_checks(
        self,
        job_id: str,
        project_dir: Path,
        requirements_spec: RequirementsSpec | None = None,
        skip_technical: bool = False,
    ) -> QualityGateReport:
        """Run all quality checks and determine final gate status."""
        checks: list[QualityCheckResult] = []

        checks.append(self.check_requirements(requirements_spec))
        checks.append(self.check_git_cleanliness(project_dir))
        checks.append(self.check_code_hygiene(project_dir))
        checks.append(self.check_secrets(project_dir))
        checks.append(self.check_documentation(project_dir))

        if not skip_technical:
            checks.append(self.check_technical_health(project_dir))

        # Determine overall status
        has_fail = any(c.status == CheckStatus.FAIL.value for c in checks)
        has_warn = any(c.status == CheckStatus.WARN.value for c in checks)

        if has_fail:
            overall = GateStatus.BLOCKED.value
        elif has_warn:
            overall = GateStatus.PASS_WITH_WARNINGS.value
        else:
            overall = GateStatus.PASS.value

        return QualityGateReport(
            job_id=job_id,
            project_path=str(project_dir.resolve()),
            overall_status=overall,
            checks=checks,
        )
