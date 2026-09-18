"""Job backup, export, and safe import CLI commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import click

from freelance_cli.output import emit_json, exit_with_error

if TYPE_CHECKING:
    from packages.workspace.manager import WorkspaceManager


def register_archive_commands(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.command("export")
    @click.argument("job_id")
    @click.option(
        "--output",
        "output_path",
        type=click.Path(path_type=Path),
        default=None,
        help="Custom export destination (.tar.gz).",
    )
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def export_job(job_id: str, output_path: Path | None, json_output: bool) -> None:
        """Export a job workspace to a portable, verified archive."""
        clean_id = job_id.upper()
        manager = manager_factory()
        found_job = manager.get_job(clean_id)

        if not found_job:
            exit_with_error(f"Job {clean_id} not found.", command="export", json_mode=json_output)
            return

        job_dir = manager.get_job_dir(clean_id)
        if not job_dir:
            exit_with_error(
                f"Workspace directory for {clean_id} not found.",
                command="export",
                json_mode=json_output,
            )
            return

        from packages.archive.manager import ArchiveManager

        archiver = ArchiveManager()
        archive_file = archiver.export_job(found_job, job_dir, output_archive=output_path)

        if json_output:
            emit_json(
                data={
                    "job_id": clean_id,
                    "archive_path": str(archive_file),
                    "size_bytes": archive_file.stat().st_size,
                },
                command="export",
            )
            return

        click.echo()
        click.secho(f"✓ Job {clean_id} exported successfully!", fg="green", bold=True)
        click.echo(f"  Archive: {archive_file}")
        click.echo(f"  Size:    {archive_file.stat().st_size} bytes")
        click.echo()

    @main.command("import")
    @click.argument("archive_file", type=click.Path(exists=True, path_type=Path))
    @click.option("--force", is_flag=True, help="Overwrite if job already exists.")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def import_job(archive_file: Path, force: bool, json_output: bool) -> None:
        """Safely import a job archive into the current workspace."""
        manager = manager_factory()
        from packages.archive.manager import ArchiveManager

        archiver = ArchiveManager()

        try:
            imported_job = archiver.import_job(
                archive_file,
                workspace_root=manager.config.workspace_path,
                force=force,
            )
        except Exception as exc:
            exit_with_error(
                f"Failed to import {archive_file.name}: {exc}",
                command="import",
                json_mode=json_output,
            )
            return

        if json_output:
            emit_json(
                data={
                    "job": imported_job.to_dict(),
                    "imported_from": str(archive_file),
                },
                command="import",
            )
            return

        click.echo()
        click.secho(f"✓ Job {imported_job.id} imported successfully!", fg="green", bold=True)
        click.echo(f"  Client:      {imported_job.client}")
        click.echo(f"  Description: {imported_job.description}")
        click.echo(f"  Status:      {imported_job.status}")
        click.echo()
