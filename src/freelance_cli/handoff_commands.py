"""Quality gate, handoff, and job-finalization CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import click

from freelance_cli.output import EXIT_BLOCKED, emit_json, exit_with_error
from packages.storage_utils import StateError, safe_read_json
from packages.workspace.manager import WorkspaceManager


def register_handoff_commands(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.command("handoff")
    @click.argument("job_id")
    @click.option("--force", is_flag=True, help="Create package even if Quality Gate is BLOCKED.")
    @click.option(
        "--skip-technical",
        "skip_tech",
        is_flag=True,
        help="Skip executing slow technical tests / ai-dev check.",
    )
    @click.option("--no-archive", is_flag=True, help="Do not build release.zip archive.")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def handoff(
        job_id: str,
        force: bool,
        skip_tech: bool,
        no_archive: bool,
        json_output: bool,
    ) -> None:
        """Run Quality Gate verification and generate client handoff deliverables."""
        from packages.handoff.checker import QualityGateChecker
        from packages.handoff.packager import HandoffPackager
        from packages.requirements.models import RequirementsSpec

        job_id = job_id.upper()
        manager = manager_factory()
        found_job = manager.get_job(job_id)

        if found_job is None:
            exit_with_error(f"Job {job_id} not found.", command="handoff", json_mode=json_output)
            return

        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            exit_with_error(
                f"Workspace directory not found for {job_id}.",
                command="handoff",
                json_mode=json_output,
            )
            return

        project_dir = (
            Path(found_job.repository)
            if found_job.repository and Path(found_job.repository).exists()
            else (job_dir / "project" if (job_dir / "project").exists() else job_dir)
        )

        # Load requirements spec if available
        req_spec: RequirementsSpec | None = None
        req_json_path = job_dir / "analysis" / "requirements.json"
        if req_json_path.exists():
            try:
                spec_data = safe_read_json(req_json_path)
                req_spec = RequirementsSpec.from_dict(spec_data)
            except (OSError, StateError, ValueError, TypeError):
                req_spec = None

        if not json_output:
            click.echo(f"\n🔍 Running Quality Gate for {job_id} ({found_job.client})...\n")

        checker = QualityGateChecker()
        report = checker.run_all_checks(
            job_id=job_id,
            project_dir=project_dir,
            requirements_spec=req_spec,
            skip_technical=skip_tech,
        )

        if report.overall_status == "BLOCKED" and not force:
            if json_output:
                emit_json(
                    data={"report": report.to_dict(), "package": None},
                    command="handoff",
                    status="blocked",
                    exit_code=EXIT_BLOCKED,
                    errors=["Quality Gate is BLOCKED. Use --force to override."],
                )
            else:
                click.secho(
                    "✗ Cannot generate handoff package: Quality Gate is BLOCKED. "
                    "Resolve issues or use --force.",
                    fg="red",
                    bold=True,
                )
                click.echo(report.summary())
            sys.exit(EXIT_BLOCKED)

        # Generate deliverables package
        handoff_dir = job_dir / "handoff"
        packager = HandoffPackager()
        package = packager.create_package(
            job=found_job,
            project_dir=project_dir,
            output_dir=handoff_dir,
            quality_report=report,
            requirements_spec=req_spec,
            create_archive=not no_archive,
        )

        # Update job status
        if found_job.status in {"IN_PROGRESS", "TESTING"}:
            manager.update_job_status(job_id, "READY_FOR_HANDOFF", "Deliverables package generated")

        if json_output:
            emit_json(
                data={"report": report.to_dict(), "package": package.to_dict()},
                command="handoff",
            )
            return

        click.echo()
        click.secho("QUALITY GATE REPORT", bold=True, fg="cyan")
        click.echo("-" * 55)
        click.echo(report.summary())
        click.echo()
        click.secho("✓ Handoff deliverables created successfully:", fg="green", bold=True)
        click.echo(f"  Destination: {package.output_dir}")
        for fname in package.created_files:
            click.echo(f"  • {fname}")
        if package.archive_path:
            click.echo(f"  • Release zip: {package.archive_path}")
        click.echo()

    @main.command("finish")
    @click.argument("job_id")
    @click.option("--force", is_flag=True, help="Finish job even if Quality Gate is BLOCKED.")
    @click.option("--archive", is_flag=True, help="Move job to finished/ workspace.")
    @click.option("--notes", type=str, default="", help="Additional closing notes.")
    @click.option("--dry-run", is_flag=True, help="Simulate job closure without modifying state.")
    @click.option(
        "--explain",
        is_flag=True,
        help="Explain the steps and checks involved in finishing the job.",
    )
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def finish(
        job_id: str,
        force: bool,
        archive: bool,
        notes: str,
        dry_run: bool,
        explain: bool,
        json_output: bool,
    ) -> None:
        """Close and finalize a delivered job."""
        from packages.handoff.checker import QualityGateChecker
        from packages.requirements.models import RequirementsSpec

        job_id = job_id.upper()
        manager = manager_factory()

        if explain:
            steps = [
                "1. Verify existence of job and workspace directory.",
                (
                    "2. Evaluate Quality Gate checks (technical checks, "
                    "requirements, deliverables) unless --force."
                ),
                "3. Transition job status to CLOSED with optional closing notes.",
                "4. Atomically persist updated job.json.",
                "5. If --archive is requested, move job from active/ to finished/.",
            ]
            if json_output:
                emit_json(data={"steps": steps}, command="finish --explain")
                return
            click.echo()
            click.secho("FINISH JOB EXECUTION PLAN", fg="cyan", bold=True)
            for s in steps:
                click.echo(f"  {s}")
            click.echo()
            return

        found_job = manager.get_job(job_id)
        if found_job is None:
            exit_with_error(f"Job {job_id} not found.", command="finish", json_mode=json_output)
            return

        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            exit_with_error(
                f"Workspace directory not found for {job_id}.",
                command="finish",
                json_mode=json_output,
            )
            return

        project_dir = (
            Path(found_job.repository)
            if found_job.repository and Path(found_job.repository).exists()
            else (job_dir / "project" if (job_dir / "project").exists() else job_dir)
        )

        # Run quick validation unless forced
        report = None
        if not force:
            req_spec: RequirementsSpec | None = None
            req_json_path = job_dir / "analysis" / "requirements.json"
            if req_json_path.exists():
                try:
                    spec_data = safe_read_json(req_json_path)
                    req_spec = RequirementsSpec.from_dict(spec_data)
                except (OSError, StateError, ValueError, TypeError):
                    req_spec = None

            checker = QualityGateChecker()
            report = checker.run_all_checks(
                job_id=job_id,
                project_dir=project_dir,
                requirements_spec=req_spec,
                skip_technical=True,
            )

            if report.overall_status == "BLOCKED":
                if json_output:
                    emit_json(
                        data={"job": found_job.to_dict(), "error": "Quality Gate BLOCKED"},
                        command="finish",
                        status="blocked",
                        exit_code=EXIT_BLOCKED,
                        errors=[
                            "Cannot finish job: Quality Gate is BLOCKED. Use --force to override."
                        ],
                    )
                else:
                    click.secho(
                        "✗ Cannot finish job: Quality Gate is BLOCKED. Use --force to override.",
                        fg="red",
                        bold=True,
                    )
                    click.echo(report.summary())
                sys.exit(EXIT_BLOCKED)

        if dry_run:
            planned = {
                "dry_run": True,
                "job_id": job_id,
                "client": found_job.client,
                "current_status": found_job.status,
                "target_status": "CLOSED",
                "notes": notes,
                "will_archive": archive,
                "quality_gate_passed": report.overall_status if report else "skipped",
            }
            if json_output:
                emit_json(planned, command="finish")
                return
            click.echo()
            click.secho(
                f"[DRY-RUN] Would finish {job_id} ({found_job.client})", fg="yellow", bold=True
            )
            click.echo(f"  Status transition: {found_job.status} → CLOSED")
            click.echo(f"  Will archive:     {archive}")
            if notes:
                click.echo(f"  Closing notes:    {notes}")
            click.echo()
            return

        found_job.change_status("CLOSED", notes or "Job closed and delivered to client.")
        if notes:
            found_job.notes = f"{found_job.notes}\n[FINISH] {notes}".strip()

        from packages.workspace.storage import save_job

        save_job(found_job, manager.config.workspace_path)

        archived_path: Path | None = None
        if archive:
            archived_path = manager.archive_job(job_id)

        if json_output:
            out_data = {
                "job": found_job.to_dict(),
                "archived": bool(archived_path),
                "archived_path": str(archived_path) if archived_path else None,
            }
            emit_json(out_data, command="finish")
            return

        click.echo()
        click.secho(f"✓ Job {job_id} successfully closed!", fg="green", bold=True)
        click.echo("-" * 55)
        click.echo(f"  Client:     {found_job.client}")
        click.echo(f"  Status:     {found_job.status}")
        if archived_path:
            click.echo(f"  Archived:   {archived_path}")
        click.echo()
