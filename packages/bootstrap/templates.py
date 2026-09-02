"""Project templates for Python and C# application bootstrap."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.requirements.models import RequirementsSpec


@dataclass
class TemplateInfo:
    """Metadata describing a project starter template."""

    name: str
    language: str
    description: str
    default_dependencies: list[str]


TEMPLATES: dict[str, TemplateInfo] = {
    "python-cli": TemplateInfo(
        name="python-cli",
        language="Python",
        description="Command-line interface application with Click, pytest, ruff, and mypy.",
        default_dependencies=["click>=8.1"],
    ),
    "python-api": TemplateInfo(
        name="python-api",
        language="Python",
        description="RESTful API service with FastAPI, uvicorn, pydantic, and pytest.",
        default_dependencies=["fastapi>=0.110.0", "uvicorn>=0.28.0", "pydantic>=2.6.0"],
    ),
    "python-desktop": TemplateInfo(
        name="python-desktop",
        language="Python",
        description="Desktop application using Tkinter/CustomTkinter with clean architecture.",
        default_dependencies=["customtkinter>=5.2.0"],
    ),
    "data-processing": TemplateInfo(
        name="data-processing",
        language="Python",
        description="Data pipeline and reporting with CSV, JSON, and Excel/openpyxl.",
        default_dependencies=["openpyxl>=3.1.0"],
    ),
    "automation-script": TemplateInfo(
        name="automation-script",
        language="Python",
        description="Automation script with structured logging, retry logic, and error handling.",
        default_dependencies=[],
    ),
    "csharp-console": TemplateInfo(
        name="csharp-console",
        language="C#",
        description=".NET Console application with xUnit testing project.",
        default_dependencies=[],
    ),
    "csharp-desktop": TemplateInfo(
        name="csharp-desktop",
        language="C#",
        description=".NET Desktop application structure with modular separation.",
        default_dependencies=[],
    ),
    "csharp-library": TemplateInfo(
        name="csharp-library",
        language="C#",
        description=".NET Class library with unit tests and packaging setup.",
        default_dependencies=[],
    ),
}


def list_templates() -> list[TemplateInfo]:
    """Return all available project starter templates."""
    return list(TEMPLATES.values())


def get_template(name: str) -> TemplateInfo:
    """Retrieve template metadata by name."""
    clean = name.strip().lower()
    if clean not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        raise ValueError(f"Unknown template '{name}'. Available templates: {available}")
    return TEMPLATES[clean]


def _slugify_pkg(name: str) -> str:
    """Convert arbitrary project name to a valid Python package identifier."""
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")
    if not slug or slug[0].isdigit():
        slug = f"app_{slug}"
    return slug


def _format_requirements_doc(spec: RequirementsSpec | None, project_name: str) -> str:
    if spec:
        return spec.to_markdown()
    return f"""# Requirements — {project_name}

**Status:** `DRAFT`

## Requirements

### General
- [ ] Implement core functionality according to client specification

## Acceptance Criteria
- [ ] All automated tests pass
- [ ] Application installs and runs cleanly
"""


def _format_acceptance_doc(spec: RequirementsSpec | None, project_name: str) -> str:
    if spec and spec.acceptance_criteria:
        lines = [f"# Acceptance Criteria — {project_name}", ""]
        for ac in spec.acceptance_criteria:
            box = "[x]" if ac.completed else "[ ]"
            lines.append(f"- {box} `{ac.id}`: {ac.criterion}")
        lines.append("")
        return "\n".join(lines)

    return f"""# Acceptance Criteria — {project_name}

- [ ] All requested functional features operate as expected
- [ ] Edge cases handled without crashes
- [ ] Automated test suite passes 100%
- [ ] Code passes lint and type check validation
"""


def _format_handoff_doc(project_name: str, description: str) -> str:
    return f"""# Client Handoff Guide — {project_name}

## Summary
{description or "Delivery package for client project."}

## Installation & Setup
See [README.md](../README.md) for full installation and execution instructions.

## Verification Checklist
- [ ] All requirements completed and verified
- [ ] Automated tests passing
- [ ] Environment variables configured in `.env`
- [ ] Documentation and user guide provided
"""


def generate_template_files(
    template_name: str,
    project_name: str,
    description: str = "",
    requirements_spec: RequirementsSpec | None = None,
) -> dict[str, str]:
    """Generate all initial files for a given project template."""
    tmpl = get_template(template_name)
    pkg_name = _slugify_pkg(project_name)
    desc = description or f"{project_name} application."

    files: dict[str, str] = {}

    # Standard docs
    files["docs/REQUIREMENTS.md"] = _format_requirements_doc(requirements_spec, project_name)
    files["docs/ACCEPTANCE.md"] = _format_acceptance_doc(requirements_spec, project_name)
    files["docs/HANDOFF.md"] = _format_handoff_doc(project_name, desc)
    files["CHANGELOG.md"] = "# Changelog\n\n## 0.1.0\n\n- Initial project bootstrap.\n"

    # ai-dev-cli-tools config
    lang_lower = tmpl.language.lower()
    files[".ai-dev-tools.toml"] = f"""[project]
name = "{project_name}"
language = "{lang_lower}"

[check]
mode = "full"
"""

    if tmpl.language == "Python":
        files.update(_generate_python_files(template_name, project_name, pkg_name, desc))
    elif tmpl.language == "C#":
        files.update(_generate_csharp_files(template_name, project_name, desc))

    return files


def _generate_python_files(
    template_name: str,
    project_name: str,
    pkg_name: str,
    description: str,
) -> dict[str, str]:
    files: dict[str, str] = {}

    files[".gitignore"] = """__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
build/
dist/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.env
"""

    files[".env.example"] = """# Application environment variables
ENVIRONMENT=development
LOG_LEVEL=INFO
"""

    files["README.md"] = f"""# {project_name}

{description}

## Requirements
- Python >= 3.11

## Setup

```bash
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows:
.venv\\Scripts\\activate

pip install -e ".[dev]"
cp .env.example .env
```

## Running

```bash
python -m {pkg_name}
```

## Tests and Quality

```bash
pytest
ruff check .
mypy src tests
```
"""

    init_py = '"""Package initialization."""\n\n__version__ = "0.1.0"\n'

    # Template-specific code
    if template_name == "python-cli":
        deps = '["click>=8.1"]'
        script_entry = f'{pkg_name} = "{pkg_name}.cli:main"'
        files[f"src/{pkg_name}/__init__.py"] = init_py
        files[f"src/{pkg_name}/cli.py"] = f'''"""Command-line interface."""

from __future__ import annotations

import click


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """{description}"""


@main.command()
@click.option("--name", default="World", help="Name to greet.")
def run(name: str) -> None:
    """Execute primary command."""
    click.echo(f"Hello, {{name}} from {project_name}!")


if __name__ == "__main__":
    main()
'''
        files[f"src/{pkg_name}/__main__.py"] = f"""from {pkg_name}.cli import main

if __name__ == "__main__":
    main()
"""
        files["tests/test_cli.py"] = f"""from click.testing import CliRunner

from {pkg_name}.cli import main


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_run() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--name", "Alice"])
    assert result.exit_code == 0
    assert "Alice" in result.output
"""

    elif template_name == "python-api":
        deps = '["fastapi>=0.110.0", "uvicorn>=0.28.0", "pydantic>=2.6.0"]'
        script_entry = f'{pkg_name} = "{pkg_name}.app:main"'
        files[f"src/{pkg_name}/__init__.py"] = init_py
        files[f"src/{pkg_name}/app.py"] = f'''"""FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="{project_name}",
    description="{description}",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {{"status": "healthy", "service": "{project_name}"}}


def main() -> None:
    """Run uvicorn development server."""
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
'''
        files[f"src/{pkg_name}/__main__.py"] = f"""from {pkg_name}.app import main

if __name__ == "__main__":
    main()
"""
        files["tests/test_api.py"] = f"""from fastapi.testclient import TestClient

from {pkg_name}.app import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
"""

    elif template_name == "python-desktop":
        deps = '["customtkinter>=5.2.0"]'
        script_entry = f'{pkg_name} = "{pkg_name}.gui:main"'
        files[f"src/{pkg_name}/__init__.py"] = init_py
        files[f"src/{pkg_name}/gui.py"] = f'''"""Desktop GUI application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class MainApplication(tk.Tk):
    """Main desktop application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("{project_name}")
        self.geometry("600x400")

        self.label = ttk.Label(self, text="Welcome to {project_name}", font=("Helvetica", 14))
        self.label.pack(pady=20)


def main() -> None:
    app = MainApplication()
    app.mainloop()


if __name__ == "__main__":
    main()
'''
        files[f"src/{pkg_name}/__main__.py"] = f"""from {pkg_name}.gui import main

if __name__ == "__main__":
    main()
"""
        files["tests/test_gui.py"] = f"""from {pkg_name}.gui import MainApplication


def test_main_window_init() -> None:
    # Verify class can be imported and initialized
    assert MainApplication is not None
"""

    elif template_name == "data-processing":
        deps = '["openpyxl>=3.1.0"]'
        script_entry = f'{pkg_name} = "{pkg_name}.pipeline:main"'
        files[f"src/{pkg_name}/__init__.py"] = init_py
        files[f"src/{pkg_name}/pipeline.py"] = f'''"""Data processing pipeline."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def process_csv_records(
    records: list[dict[str, Any]], deduplicate_key: str | None = None
) -> list[dict[str, Any]]:
    """Process and deduplicate record dataset."""
    if not deduplicate_key:
        return records

    seen: set[Any] = set()
    cleaned: list[dict[str, Any]] = []
    for row in records:
        val = row.get(deduplicate_key)
        if val not in seen:
            seen.add(val)
            cleaned.append(row)
    return cleaned


def main() -> None:
    print("Running {project_name} data pipeline...")


if __name__ == "__main__":
    main()
'''
        files[f"src/{pkg_name}/__main__.py"] = f"""from {pkg_name}.pipeline import main

if __name__ == "__main__":
    main()
"""
        files["tests/test_pipeline.py"] = f"""from {pkg_name}.pipeline import process_csv_records


def test_process_csv_records_deduplication() -> None:
    raw = [
        {{"id": "1", "name": "Alice"}},
        {{"id": "2", "name": "Bob"}},
        {{"id": "1", "name": "Alice Duplicate"}},
    ]
    cleaned = process_csv_records(raw, deduplicate_key="id")
    assert len(cleaned) == 2
    assert [r["id"] for r in cleaned] == ["1", "2"]
"""

    else:  # automation-script
        deps = "[]"
        script_entry = f'{pkg_name} = "{pkg_name}.main:run"'
        files[f"src/{pkg_name}/__init__.py"] = init_py
        files[f"src/{pkg_name}/main.py"] = f'''"""Automation script entrypoint."""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def run() -> int:
    """Execute automation task."""
    logger.info("Starting automation task for {project_name}...")
    # Add automation logic here
    logger.info("Task completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
'''
        files[f"src/{pkg_name}/__main__.py"] = f"""from {pkg_name}.main import run

if __name__ == "__main__":
    import sys
    sys.exit(run())
"""
        files["tests/test_automation.py"] = f"""from {pkg_name}.main import run


def test_run_success() -> None:
    assert run() == 0
"""

    # Common pyproject.toml
    files["pyproject.toml"] = f"""[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "{project_name.lower()}"
version = "0.1.0"
description = "{description}"
readme = "README.md"
requires-python = ">=3.11"
dependencies = {deps}

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "ruff>=0.6",
  "mypy>=1.11",
]

[project.scripts]
{script_entry}

[tool.hatch.build.targets.wheel]
packages = ["src/{pkg_name}"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true
mypy_path = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""

    return files


def _generate_csharp_files(
    template_name: str,
    project_name: str,
    description: str,
) -> dict[str, str]:
    files: dict[str, str] = {}
    clean_name = re.sub(r"[^a-zA-Z0-9_]+", "", project_name) or "App"

    files[".gitignore"] = """bin/
obj/
.vs/
*.user
*.suo
.env
"""

    files[".env.example"] = """ENVIRONMENT=Development
"""

    files["README.md"] = f"""# {project_name}

{description}

## Requirements
- .NET 8.0 SDK or higher

## Build & Run

```bash
dotnet build
dotnet run --project src/{clean_name}
```

## Run Tests

```bash
dotnet test
```
"""

    proj_guid = "{A1B2C3D4-0001-0001-0001-000000000001}"
    test_guid = "{A1B2C3D4-0001-0001-0001-000000000002}"
    type_guid = "{9A19103F-16F7-4668-BE54-9A1E7A4F7556}"
    proj_entry = (
        f'Project("{type_guid}") = "{clean_name}", '
        f'"src/{clean_name}/{clean_name}.csproj", "{proj_guid}"'
    )
    test_entry = (
        f'Project("{type_guid}") = "{clean_name}.Tests", '
        f'"tests/{clean_name}.Tests/{clean_name}.Tests.csproj", "{test_guid}"'
    )

    files[f"{clean_name}.sln"] = f"""Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 17
VisualStudioVersion = 17.0.31903.59
MinimumVisualStudioVersion = 10.0.40219.1
{proj_entry}
EndProject
{test_entry}
EndProject
"""

    is_lib = template_name == "csharp-library"
    output_type = "<OutputType>Exe</OutputType>" if not is_lib else ""

    files[f"src/{clean_name}/{clean_name}.csproj"] = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    {output_type}
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
"""

    if is_lib:
        files[f"src/{clean_name}/Class1.cs"] = f"""namespace {clean_name};

public class Service
{{
    public string Greet(string name) => $"Hello, {{name}} from {project_name}!";
}}
"""
    else:
        files[f"src/{clean_name}/Program.cs"] = f"""namespace {clean_name};

public class Program
{{
    public static void Main(string[] args)
    {{
        Console.WriteLine("Hello from {project_name}!");
    }}
}}
"""

    test_csproj_key = f"tests/{clean_name}.Tests/{clean_name}.Tests.csproj"
    files[test_csproj_key] = f"""<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <IsPackable>false</IsPackable>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.9.0" />
    <PackageReference Include="xunit" Version="2.7.0" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.5.7" />
  </ItemGroup>

  <ItemGroup>
    <ProjectReference Include="../../src/{clean_name}/{clean_name}.csproj" />
  </ItemGroup>
</Project>
"""

    files[f"tests/{clean_name}.Tests/UnitTest1.cs"] = f"""using Xunit;

namespace {clean_name}.Tests;

public class UnitTest1
{{
    [Fact]
    public void TestBasicSanity()
    {{
        Assert.True(true);
    }}
}}
"""

    return files
