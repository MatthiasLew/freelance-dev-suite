"""Quality gate, handoff, and job-finalization CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import click

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
        import json as _json

        from packages.handoff.checker import QualityGateChecker
        from packages.handoff.packager import HandoffPackager
        from packages.requirements.models import RequirementsSpec

        job_id = job_id.upper()
        manager = manager_factory()
        found_job = manager.get_job(job_id)

        if found_job is None:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Workspace directory not found for {job_id}.", fg="red", err=True)
            sys.exit(1)

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
                with open(req_json_path, encoding="utf-8") as f:
                    req_spec = RequirementsSpec.from_dict(_json.load(f))
            except (OSError, _json.JSONDecodeError):
                req_spec = None

        # Run Quality Gate
        checker = QualityGateChecker()
        report = checker.run_all_checks(
            job_id=job_id,
            project_dir=project_dir,
            requirements_spec=req_spec,
            skip_technical=skip_tech,
        )

        # Save quality gate report
        qg_json_path = job_dir / "analysis" / "quality-gate.json"
        try:
            with open(qg_json_path, "w", encoding="utf-8") as f:
                _json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError:
            pass

        if report.overall_status == "BLOCKED" and not force:
            if json_output:
                click.echo(_json.dumps({"gate": report.to_dict(), "package": None}, indent=2))
            else:
                click.echo()
                click.secho(report.summary(), fg="red")
                click.echo()
                click.secho(
                    "✗ Quality Gate is BLOCKED. Resolve issues above or use --force to proceed.",
                    fg="red",
                    bold=True,
                )
            sys.exit(1)

        # Generate Handoff package
        packager = HandoffPackager()
        package = packager.create_package(
            job=found_job,
            project_dir=project_dir,
            output_dir=job_dir / "handoff",
            requirements_spec=req_spec,
            quality_report=report,
            create_archive=not no_archive,
        )

        # Update job status
        if found_job.status in {"IN_PROGRESS", "ACCEPTED"}:
            found_job.change_status("READY_FOR_HANDOFF", "Handoff package generated")
            from packages.workspace.storage import save_job

            save_job(found_job, manager.config.workspace_path)

        if json_output:
            click.echo(
                _json.dumps(
                    {"gate": report.to_dict(), "package": package.to_dict()},
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return

        click.echo()
        if report.overall_status == "PASS":
            click.secho("✓ FINAL QUALITY GATE: PASS", fg="green", bold=True)
        else:
            click.secho(
                f"⚠ FINAL QUALITY GATE: {report.overall_status}",
                fg="yellow",
                bold=True,
            )
        click.echo("-" * 60)
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
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def finish(
        job_id: str,
        force: bool,
        archive: bool,
        notes: str,
        json_output: bool,
    ) -> None:
        """Close and finalize a delivered job."""
        import json as _json

        from packages.handoff.checker import QualityGateChecker
        from packages.requirements.models import RequirementsSpec

        job_id = job_id.upper()
        manager = manager_factory()
        found_job = manager.get_job(job_id)

        if found_job is None:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Workspace directory not found for {job_id}.", fg="red", err=True)
            sys.exit(1)

        project_dir = (
            Path(found_job.repository)
            if found_job.repository and Path(found_job.repository).exists()
            else (job_dir / "project" if (job_dir / "project").exists() else job_dir)
        )

        # Run quick validation unless forced
        if not force:
            req_spec: RequirementsSpec | None = None
            req_json_path = job_dir / "analysis" / "requirements.json"
            if req_json_path.exists():
                try:
                    with open(req_json_path, encoding="utf-8") as f:
                        req_spec = RequirementsSpec.from_dict(_json.load(f))
                except (OSError, _json.JSONDecodeError):
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
                    click.echo(
                        _json.dumps(
                            {"job": found_job.to_dict(), "error": "Quality Gate BLOCKED"},
                            indent=2,
                        )
                    )
                else:
                    click.secho(
                        "✗ Cannot finish job: Quality Gate is BLOCKED. Use --force to override.",
                        fg="red",
                        bold=True,
                    )
                    click.echo(report.summary())
                sys.exit(1)

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
            click.echo(_json.dumps(out_data, indent=2, ensure_ascii=False))
            return

        click.echo()
        click.secho(f"✓ Job {job_id} successfully closed!", fg="green", bold=True)
        click.echo("-" * 55)
        click.echo(f"  Client:     {found_job.client}")
        click.echo(f"  Status:     {found_job.status}")
        if archived_path:
            click.echo(f"  Archived:   {archived_path}")
        click.echo()
