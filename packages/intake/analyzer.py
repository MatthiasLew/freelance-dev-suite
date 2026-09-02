"""Project intake analysis backed by ``ai-dev-cli-tools``."""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from .complexity import classify_complexity, estimate_work_hours
from .risk import assess_risk

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
EXCLUDED_DIRECTORIES = {
    ".ai",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "venv",
}


class AIDevIntegrationError(RuntimeError):
    """Raised when the technical engine cannot return a usable report."""


@dataclass
class IntakeResult:
    """Structured result of project intake analysis."""

    project_path: str
    languages: list[str]
    frameworks: list[str]
    package_managers: list[str]
    has_tests: bool
    has_lint: bool
    has_typecheck: bool
    has_docker: bool
    has_ci: bool
    total_files: int
    source_files: int
    loc: int
    dependency_count: int
    repo_size_bytes: int
    risk_level: str
    risk_factors: list[str]
    complexity: str
    estimated_hours_min: float
    estimated_hours_max: float
    workspace_count: int
    scan_data: dict[str, Any]
    timestamp: str
    validation_status: str = "unknown"
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    lint_status: str = "not_detected"
    typecheck_status: str = "not_detected"
    context_tokens: int = 0
    critical_problems: list[str] = field(default_factory=list)
    check_data: dict[str, Any] = field(default_factory=dict)
    context_data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntakeResult:
        """Load an intake result, including artifacts created by older versions."""
        known = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        factors = "\n  - ".join(self.risk_factors) if self.risk_factors else "None"
        problems = "\n  - ".join(self.critical_problems) if self.critical_problems else "None"
        return f"""Project: {self.project_path}
Timestamp: {self.timestamp}
Complexity: {self.complexity}
Risk Level: {self.risk_level}
Estimated Hours: {self.estimated_hours_min:.1f}-{self.estimated_hours_max:.1f}h

Size Metrics:
- Total Files: {self.total_files}
- Source Files: {self.source_files}
- LOC: {self.loc}
- Repo Size: {self.repo_size_bytes / 1024 / 1024:.2f} MB
- Dependencies: {self.dependency_count}
- Workspaces: {self.workspace_count}
- Context Tokens: {self.context_tokens}

Tech Stack:
- Languages: {", ".join(self.languages) or "None detected"}
- Frameworks: {", ".join(self.frameworks) or "None detected"}
- Package Managers: {", ".join(self.package_managers) or "None detected"}

Validation:
- Overall: {self.validation_status}
- Tests: {self.tests_passed} passed / {self.tests_failed} failed / {self.tests_skipped} skipped
- Lint: {self.lint_status}
- Typecheck: {self.typecheck_status}
- Docker detected: {self.has_docker}
- CI detected: {self.has_ci}

Critical Problems:
  - {problems}

Risk Factors:
  - {factors}
"""


def _ai_dev_command() -> list[str]:
    configured = os.environ.get("AI_DEV_EXECUTABLE")
    if configured:
        return shlex.split(configured, posix=os.name != "nt")
    executable = shutil.which("ai-dev")
    if executable:
        return [executable]
    if importlib.util.find_spec("ai_dev_tools") is not None:
        return [sys.executable, "-m", "ai_dev_tools.cli"]
    raise AIDevIntegrationError(
        "ai-dev-cli-tools is unavailable. Install freelance-dev-suite[ai-dev] "
        "or set AI_DEV_EXECUTABLE to the ai-dev executable."
    )


def _run_ai_dev(project: Path, *arguments: str) -> dict[str, Any]:
    command = [*_ai_dev_command(), "--project", str(project), "--json", *arguments]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise AIDevIntegrationError(
            f"ai-dev {' '.join(arguments)} returned invalid JSON: {detail}"
        ) from exc
    if not isinstance(payload, dict):
        raise AIDevIntegrationError(f"ai-dev {' '.join(arguments)} returned a non-object report")
    if completed.returncode not in {0, 1}:
        detail = completed.stderr.strip() or str(payload.get("issues", "unknown error"))
        raise AIDevIntegrationError(f"ai-dev {' '.join(arguments)} failed: {detail}")
    return payload


def count_source_and_loc(project_path: str) -> tuple[int, int, int]:
    """Count source files, non-empty lines, and repository bytes."""
    root = Path(project_path)
    source_files = 0
    loc = 0
    repo_size_bytes = 0
    for path in root.rglob("*"):
        if any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        if not path.is_file():
            continue
        try:
            repo_size_bytes += path.stat().st_size
            if path.suffix.lower() in SOURCE_EXTENSIONS:
                source_files += 1
                with path.open(encoding="utf-8", errors="ignore") as source:
                    loc += sum(1 for line in source if line.strip())
        except OSError:
            continue
    return source_files, loc, repo_size_bytes


def parse_dependencies(project_path: str, package_managers: list[str]) -> int:
    """Count declared dependencies without double-counting identical names."""
    root = Path(project_path)
    dependencies: set[str] = set()
    package_json = root / "package.json"
    if package_json.exists() and {"npm", "yarn", "pnpm"}.intersection(package_managers):
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            dependencies.update(data.get("dependencies", {}))
            dependencies.update(data.get("devDependencies", {}))
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    pyproject = root / "pyproject.toml"
    if pyproject.exists() and {"pip", "poetry", "pip/pyproject"}.intersection(package_managers):
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            for value in data.get("project", {}).get("dependencies", []):
                dependencies.add(str(value).split("[", 1)[0].split(" ", 1)[0].lower())
            optional = data.get("project", {}).get("optional-dependencies", {})
            for values in optional.values():
                for value in values:
                    dependencies.add(str(value).split("[", 1)[0].split(" ", 1)[0].lower())
            dependencies.update(data.get("tool", {}).get("poetry", {}).get("dependencies", {}))
        except (OSError, tomllib.TOMLDecodeError, TypeError, AttributeError):
            pass
    requirements = root / "requirements.txt"
    if requirements.exists():
        try:
            for line in requirements.read_text(encoding="utf-8").splitlines():
                clean = line.strip()
                if clean and not clean.startswith(("#", "-")):
                    dependencies.add(clean.split("[", 1)[0].split("=", 1)[0].lower())
        except OSError:
            pass
    return len(dependencies)


def _check_result_status(summary: dict[str, Any], category: str) -> str:
    results = summary.get("results", [])
    if not isinstance(results, list):
        return "not_detected"
    matching = [
        item for item in results if isinstance(item, dict) and item.get("category") == category
    ]
    if not matching:
        plan = summary.get("plan", [])
        detected = any(isinstance(item, dict) and item.get("category") == category for item in plan)
        return "not_run" if detected else "not_detected"
    return "failed" if any(item.get("status") == "failed" for item in matching) else "passed"


def _critical_problems(check_summary: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    results = check_summary.get("results", [])
    if not isinstance(results, list):
        return problems
    for result in results:
        if not isinstance(result, dict) or result.get("status") != "failed":
            continue
        name = str(result.get("name", result.get("category", "check")))
        reason = str(result.get("first_failure_reason") or "validation failed")
        problems.append(f"{name}: {reason}")
    return problems


def _context_token_count(context_summary: dict[str, Any]) -> int:
    budget = context_summary.get("budget", {})
    if isinstance(budget, dict) and isinstance(budget.get("used_chars"), int):
        return max(1, (int(budget["used_chars"]) + 3) // 4)
    accounting = context_summary.get("token_accounting", {})
    if isinstance(accounting, dict) and isinstance(accounting.get("input_tokens"), int):
        return int(accounting["input_tokens"])
    return 0


def analyze_project(
    project_path: str,
    task_description: str = "",
    validation_mode: str = "full",
) -> IntakeResult:
    """Analyze a project using current ai-dev JSON contracts."""
    project = Path(project_path).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    if validation_mode not in {"fast", "full"}:
        raise ValueError("validation_mode must be 'fast' or 'full'")

    scan_report = _run_ai_dev(project, "scan")
    map_report = _run_ai_dev(project, "map")
    check_report = _run_ai_dev(project, "check", "--mode", validation_mode, "--no-cache")
    context_arguments = ["context", "build", "--max-chars", "50000"]
    if task_description:
        context_arguments.extend(["--task", task_description])
    context_report = _run_ai_dev(project, *context_arguments)

    scan = scan_report.get("summary", {})
    repository_map = map_report.get("summary", {})
    check = check_report.get("summary", {})
    context = context_report.get("summary", {})
    if not all(isinstance(item, dict) for item in (scan, repository_map, check, context)):
        raise AIDevIntegrationError("ai-dev returned an incompatible summary schema")

    languages = [str(item) for item in scan.get("languages", [])]
    frameworks = [str(item) for item in scan.get("frameworks", [])]
    package_managers = [str(item) for item in scan.get("package_managers", [])]
    plan = check.get("plan", [])
    categories = {
        str(item.get("category"))
        for item in plan
        if isinstance(item, dict) and item.get("category")
    }
    has_tests = "unit_tests" in categories
    has_lint = "lint" in categories
    has_typecheck = "typecheck" in categories
    total_files = int(repository_map.get("file_count_scanned", 0))
    source_files, loc, repo_size = count_source_and_loc(str(project))
    dependency_count = parse_dependencies(str(project), package_managers)
    tests_failed = int(check.get("tests_failed", 0))
    validation_status = str(check_report.get("status", "unknown"))

    risk_level, risk_factors = assess_risk(
        has_tests=has_tests,
        has_lint=has_lint,
        has_typecheck=has_typecheck,
        has_docker=bool(scan.get("docker")),
        has_ci=bool(scan.get("ci")),
        total_files=total_files,
        dependency_count=dependency_count,
        config_warnings=[str(item) for item in scan.get("config_warnings", [])],
        tests_failed=tests_failed,
        validation_status=validation_status,
    )
    complexity = classify_complexity(
        languages_count=len(languages),
        frameworks_count=len(frameworks),
        loc=loc,
        total_files=total_files,
        workspace_count=int(scan.get("workspace_count", 1)),
    )
    estimated_min, estimated_max = estimate_work_hours(complexity, task_description)

    return IntakeResult(
        project_path=str(project),
        languages=languages,
        frameworks=frameworks,
        package_managers=package_managers,
        has_tests=has_tests,
        has_lint=has_lint,
        has_typecheck=has_typecheck,
        has_docker=bool(scan.get("docker")),
        has_ci=bool(scan.get("ci")),
        total_files=total_files,
        source_files=source_files,
        loc=loc,
        dependency_count=dependency_count,
        repo_size_bytes=repo_size,
        risk_level=risk_level,
        risk_factors=risk_factors,
        complexity=complexity,
        estimated_hours_min=estimated_min,
        estimated_hours_max=estimated_max,
        workspace_count=int(scan.get("workspace_count", 1)),
        scan_data=scan,
        timestamp=datetime.now().astimezone().isoformat(),
        validation_status=validation_status,
        tests_total=int(check.get("tests_total", 0)),
        tests_passed=int(check.get("tests_passed", 0)),
        tests_failed=tests_failed,
        tests_skipped=int(check.get("tests_skipped", 0)),
        lint_status=_check_result_status(check, "lint"),
        typecheck_status=_check_result_status(check, "typecheck"),
        context_tokens=_context_token_count(context),
        critical_problems=_critical_problems(check),
        check_data=check,
        context_data=context,
    )
