"""Job creation, listing, status, and lifecycle commands."""

from __future__ import annotations

from collections.abc import Callable

import click

from freelance_cli.models.job import Job, JobSource, JobStatus
from packages.workspace.manager import WorkspaceManager

ManagerFactory = Callable[[], WorkspaceManager]
StatusColor = Callable[[str], str]


def register_job_commands(
    main: click.Group, manager_factory: ManagerFactory, status_color: StatusColor
) -> None:
    """Attach job commands while keeping manager creation injectable for tests."""

    @main.group()
    def job() -> None:
        """Manage individual jobs."""

    @job.command("new")
    @click.option("--client", prompt="Client name", help="Client name or company.")
    @click.option("--description", prompt="Task description", help="Short description of the job.")
    @click.option(
        "--source",
        type=click.Choice([source.value for source in JobSource], case_sensitive=False),
        default=JobSource.OTHER.value,
        prompt="Source (Useme/Upwork/Fiverr/Direct/Other)",
        help="Where the job came from.",
    )
    @click.option("--budget", type=float, default=None, help="Client budget in PLN.")
    @click.option("--deadline", type=str, default=None, help="Deadline (YYYY-MM-DD).")
    @click.option("--repository", type=str, default=None, help="Path or URL to the repository.")
    @click.option("--notes", type=str, default="", help="Additional notes.")
    def job_new(
        client: str,
        description: str,
        source: str,
        budget: float | None,
        deadline: str | None,
        repository: str | None,
        notes: str,
    ) -> None:
        """Create a new freelance job."""
        manager = manager_factory()
        new_job = manager.create_job(
            client=client,
            description=description,
            source=source,
            budget_pln=budget,
            deadline=deadline,
            repository=repository,
            notes=notes,
        )
        click.echo()
        click.secho(f"✓ Created {new_job.id}", fg="green", bold=True)
        click.echo(f"  Client:      {new_job.client}")
        click.echo(f"  Source:      {new_job.source}")
        click.echo(f"  Description: {new_job.description}")
        if new_job.budget_pln:
            click.echo(f"  Budget:      {new_job.budget_pln:.0f} PLN")
        if new_job.deadline:
            click.echo(f"  Deadline:    {new_job.deadline}")
        click.echo(f"  Status:      {new_job.status}")
        click.echo()
        job_dir = manager.get_job_dir(new_job.id)
        if job_dir:
            click.echo(f"  Workspace:   {job_dir}")
        click.echo()

    @main.command("jobs")
    @click.option("--all", "show_all", is_flag=True, help="Include finished/rejected jobs.")
    def jobs_list(show_all: bool) -> None:
        """List all active jobs."""
        jobs = manager_factory().list_jobs(include_finished=show_all)
        if not jobs:
            click.echo("No active jobs found.")
            click.echo('Use "freelance job new" to create one.')
            return
        click.echo()
        click.secho(Job.summary_header(), bold=True)
        click.echo("-" * 90)
        for item in jobs:
            click.secho(item.summary_line(), fg=status_color(item.status))
        click.echo()
        click.echo(f"Total: {len(jobs)} job(s)")
        click.echo()

    @main.command("status")
    @click.argument("job_id")
    def status(job_id: str) -> None:
        """Show detailed status of a specific job."""
        clean_id = job_id.upper()
        manager = manager_factory()
        found_job = manager.get_job(clean_id)
        if found_job is None:
            raise click.ClickException(f"Job {clean_id} not found.")
        click.echo()
        click.secho(f"-- {found_job.id} --", fg=status_color(found_job.status), bold=True)
        click.echo()
        click.echo(found_job.detail_view())
        job_dir = manager.get_job_dir(found_job.id)
        if job_dir:
            click.echo(f"\nWorkspace:   {job_dir}")
        click.echo()

    @job.command("update")
    @click.argument("job_id")
    @click.option(
        "--status",
        "new_status",
        type=click.Choice([status.value for status in JobStatus], case_sensitive=False),
        required=True,
        help="New status.",
    )
    @click.option("--note", type=str, default="", help="Note for the status change.")
    def job_update(job_id: str, new_status: str, note: str) -> None:
        """Update a job's status."""
        clean_id = job_id.upper()
        updated = manager_factory().update_job_status(clean_id, new_status, note)
        if updated is None:
            raise click.ClickException(f"Job {clean_id} not found.")
        click.secho(f"✓ {updated.id} → {updated.status}", fg="green", bold=True)
