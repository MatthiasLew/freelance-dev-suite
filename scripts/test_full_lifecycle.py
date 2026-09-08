"""Exercise the installed CLI and ai-dev integration through a complete job lifecycle."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


def run_json(command: list[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    payload = json.loads(run(command, cwd=cwd, env=env))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object from {' '.join(command)}")
    return payload


def main() -> None:
    configured_freelance = os.environ.get("FREELANCE_EXECUTABLE")
    discovered_freelance = shutil.which("freelance")
    freelance = (
        shlex.split(configured_freelance, posix=os.name != "nt")
        if configured_freelance
        else [discovered_freelance]
        if discovered_freelance
        else []
    )
    ai_dev = os.environ.get("AI_DEV_EXECUTABLE") or shutil.which("ai-dev")
    if not freelance or ai_dev is None:
        raise SystemExit("Both freelance and ai-dev executables must be installed.")

    with tempfile.TemporaryDirectory(prefix="freelance-e2e-") as temporary:
        root = Path(temporary)
        home = root / "home"
        repository = root / "sample-project"
        home.mkdir()
        (repository / "src" / "sample_project").mkdir(parents=True)
        (repository / "tests").mkdir()
        (repository / "src" / "sample_project" / "__init__.py").write_text(
            "def answer() -> int:\n    return 41\n", encoding="utf-8"
        )
        (repository / "tests" / "test_answer.py").write_text(
            "from sample_project import answer\n\n\ndef test_answer() -> None:\n"
            "    assert answer() == 41\n",
            encoding="utf-8",
        )
        (repository / "pyproject.toml").write_text(
            "[build-system]\nrequires = ['hatchling']\nbuild-backend = 'hatchling.build'\n\n"
            "[project]\nname = 'sample-project'\nversion = '0.1.0'\nrequires-python = '>=3.11'\n\n"
            "[tool.pytest.ini_options]\npythonpath = ['src']\n",
            encoding="utf-8",
        )
        (repository / "README.md").write_text("# Sample project\n", encoding="utf-8")
        (repository / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n", encoding="utf-8")

        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        run(["git", "init"], cwd=repository, env=environment)
        run(["git", "config", "user.email", "e2e@example.invalid"], cwd=repository, env=environment)
        run(["git", "config", "user.name", "E2E Test"], cwd=repository, env=environment)
        run(["git", "add", "."], cwd=repository, env=environment)
        run(["git", "commit", "-m", "Initial sample"], cwd=repository, env=environment)

        run(
            [
                *freelance,
                "job",
                "new",
                "--client",
                "E2E Client",
                "--description",
                "Complete lifecycle",
                "--source",
                "Direct",
                "--repository",
                str(repository),
            ],
            cwd=repository,
            env=environment,
        )
        analysis = run_json(
            [*freelance, "analyze", "JOB-001", "--check-mode", "fast", "--json"],
            cwd=repository,
            env=environment,
        )
        if analysis.get("intake", {}).get("project_path") != str(repository):
            raise AssertionError("Intake analysis did not inspect the sample repository.")

        requirements = run_json(
            [
                *freelance,
                "requirements",
                "JOB-001",
                "--from-text",
                "Return the tested answer 42.",
                "--confirm",
                "--confirmed-by",
                "E2E Client",
                "--json",
            ],
            cwd=repository,
            env=environment,
        )
        for item in [
            *requirements.get("requirements", []),
            *requirements.get("acceptance_criteria", []),
        ]:
            identifier = item.get("id")
            if identifier:
                run(
                    [*freelance, "requirements", "JOB-001", "--check", str(identifier)],
                    cwd=repository,
                    env=environment,
                )

        session = run_json(
            [
                *freelance,
                "work",
                "start",
                "JOB-001",
                "--task",
                "Change the tested answer from 41 to 42",
                "--agent",
                "generic",
                "--json",
            ],
            cwd=repository,
            env=environment,
        )
        (repository / "src" / "sample_project" / "__init__.py").write_text(
            "def answer() -> int:\n    return 42\n", encoding="utf-8"
        )
        (repository / "tests" / "test_answer.py").write_text(
            "from sample_project import answer\n\n\ndef test_answer() -> None:\n"
            "    assert answer() == 42\n",
            encoding="utf-8",
        )
        finished = run_json(
            [*freelance, "work", "finish", str(session["id"]), "--json"],
            cwd=repository,
            env=environment,
        )
        if finished.get("status") != "VERIFIED":
            raise AssertionError(f"Work session was not verified: {finished}")

        handoff = run_json(
            [*freelance, "handoff", "JOB-001", "--force", "--json"],
            cwd=repository,
            env=environment,
        )
        if not handoff.get("package"):
            raise AssertionError("Handoff did not create a package.")
        closed = run_json(
            [
                *freelance,
                "finish",
                "JOB-001",
                "--force",
                "--archive",
                "--notes",
                "Automated lifecycle verification",
                "--json",
            ],
            cwd=repository,
            env=environment,
        )
        if not closed.get("archived") or closed.get("job", {}).get("status") != "CLOSED":
            raise AssertionError(f"Job did not close and archive cleanly: {closed}")
        print("Full installed job lifecycle completed successfully.")


if __name__ == "__main__":
    main()
