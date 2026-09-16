"""System diagnostics and ai-dev compatibility verification."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import Any

import click

from freelance_cli import __version__
from freelance_cli.output import emit_json
from packages.storage_utils import (
    CURRENT_STATE_SCHEMA_VERSION,
    StateError,
    safe_read_json,
)
from packages.workspace.manager import WorkspaceManager

MINIMUM_AI_DEV_VERSION = (1, 2, 0)


def _parse_version(version_str: str) -> tuple[int, ...]:
    clean = version_str.strip().lstrip("v").split()[-1]
    parts: list[int] = []
    for piece in clean.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            break
    return tuple(parts) if parts else (0, 0, 0)


def check_environment(manager: WorkspaceManager) -> dict[str, Any]:
    """Run diagnostics on environment, workspace, tools, and state schema."""
    checks: list[dict[str, Any]] = []
    issues: list[str] = []

    # 1. Python runtime
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)
    checks.append(
        {
            "name": "Python Environment",
            "status": "PASS" if py_ok else "FAIL",
            "details": f"Python {py_ver} on {platform.system()} ({platform.machine()})",
        }
    )
    if not py_ok:
        issues.append(f"Python version {py_ver} is unsupported. Python >=3.11 required.")

    # 2. Workspace root & write permissions
    ws_path = manager.config.workspace_path
    ws_exists = ws_path.exists()
    ws_writable = os.access(ws_path, os.W_OK) if ws_exists else os.access(ws_path.parent, os.W_OK)
    checks.append(
        {
            "name": "Workspace Directory",
            "status": "PASS"
            if (ws_exists and ws_writable)
            else ("WARN" if not ws_exists else "FAIL"),
            "details": f"{ws_path} (exists={ws_exists}, writable={ws_writable})",
        }
    )
    if not ws_writable:
        issues.append(f"Workspace directory {ws_path} is not writable.")

    # 3. Git executable
    git_bin = shutil.which("git")
    git_ver = ""
    if git_bin:
        try:
            res = subprocess.run(
                [git_bin, "--version"], capture_output=True, text=True, check=False
            )
            git_ver = res.stdout.strip()
        except OSError:
            git_ver = "unknown"
    checks.append(
        {
            "name": "Git Executable",
            "status": "PASS" if git_bin else "WARN",
            "details": git_ver if git_bin else "git executable not found in PATH",
        }
    )

    # 4. ai-dev technical engine availability and version
    ai_dev_bin = shutil.which("ai-dev")
    ai_dev_ver_str = ""
    ai_dev_compatible = False
    if ai_dev_bin:
        try:
            res = subprocess.run(
                [ai_dev_bin, "--version"], capture_output=True, text=True, check=False
            )
            ai_dev_ver_str = res.stdout.strip()
            parsed_ver = _parse_version(ai_dev_ver_str)
            ai_dev_compatible = parsed_ver >= MINIMUM_AI_DEV_VERSION
        except OSError:
            ai_dev_ver_str = "error executing ai-dev"
    checks.append(
        {
            "name": "ai-dev Technical Engine",
            "status": "PASS" if ai_dev_compatible else ("FAIL" if ai_dev_bin else "WARN"),
            "details": (
                f"{ai_dev_ver_str} (compatible: {ai_dev_compatible})"
                if ai_dev_bin
                else "ai-dev executable not found (technical engine optional, install via [ai-dev])"
            ),
        }
    )
    if ai_dev_bin and not ai_dev_compatible:
        issues.append(f"ai-dev version {ai_dev_ver_str} is below minimum supported 1.2.0")

    # 5. State schema verification across existing active jobs
    corrupted_jobs: list[str] = []
    incompatible_jobs: list[str] = []
    total_jobs = 0
    active_dir = ws_path / "active"
    if active_dir.exists():
        for job_folder in active_dir.iterdir():
            job_file = job_folder / "job.json"
            if job_file.exists():
                total_jobs += 1
                try:
                    safe_read_json(job_file)
                except StateError as exc:
                    if "Unsupported schema_version" in str(exc):
                        incompatible_jobs.append(job_folder.name)
                    else:
                        corrupted_jobs.append(job_folder.name)

    state_status = "PASS"
    state_details = (
        f"{total_jobs} active job(s) verified (schema_version <= {CURRENT_STATE_SCHEMA_VERSION})"
    )
    if corrupted_jobs or incompatible_jobs:
        state_status = "FAIL"
        state_details = (
            f"Errors in jobs: corrupted={corrupted_jobs}, incompatible={incompatible_jobs}"
        )
        issues.append(state_details)

    checks.append(
        {
            "name": "Persistent State Schema",
            "status": state_status,
            "details": state_details,
        }
    )

    overall_status = "HEALTHY"
    if issues:
        overall_status = "UNHEALTHY"
    elif any(c["status"] == "WARN" for c in checks):
        overall_status = "WARNING"

    return {
        "overall_status": overall_status,
        "freelance_version": __version__,
        "schema_version": CURRENT_STATE_SCHEMA_VERSION,
        "checks": checks,
        "issues": issues,
    }


def register_doctor_command(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.command("doctor")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON diagnostics.")
    def doctor(json_output: bool) -> None:
        """Verify environment, workspace permissions, ai-dev engine, and state schema."""
        manager = manager_factory()
        diag = check_environment(manager)

        if json_output:
            emit_json(
                data=diag,
                command="doctor",
                status="success" if diag["overall_status"] != "UNHEALTHY" else "error",
                exit_code=0 if diag["overall_status"] != "UNHEALTHY" else 1,
                errors=diag["issues"],
            )
            return

        click.echo()
        click.secho(
            f"FREELANCE DEV SUITE DOCTOR — v{diag['freelance_version']}",
            bold=True,
            fg="cyan",
        )
        click.echo("-" * 65)
        for check in diag["checks"]:
            st = check["status"]
            color = "green" if st == "PASS" else ("yellow" if st == "WARN" else "red")
            icon = "✓" if st == "PASS" else ("⚠" if st == "WARN" else "✗")
            click.secho(f"[{icon}] {check['name']:<28} {st:<6}", fg=color, bold=True)
            click.echo(f"    {check['details']}")

        click.echo("-" * 65)
        overall = diag["overall_status"]
        color = "green" if overall == "HEALTHY" else ("yellow" if overall == "WARNING" else "red")
        click.secho(f"Overall Status: {overall}", fg=color, bold=True)
        if diag["issues"]:
            click.secho("\nAction Required:", fg="red", bold=True)
            for iss in diag["issues"]:
                click.echo(f"  • {iss}")
        click.echo()
        if overall == "UNHEALTHY":
            sys.exit(1)
