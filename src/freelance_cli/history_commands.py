"""Job business history and audit timeline CLI commands."""

from __future__ import annotations

from collections.abc import Callable

import click

from freelance_cli.output import emit_json, exit_with_error
from packages.timeline.manager import TimelineManager
from packages.workspace.manager import WorkspaceManager


def register_history_commands(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.command("history")
    @click.argument("job_id")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def history(job_id: str, json_output: bool) -> None:
        """View append-only business event timeline for a job."""
        clean_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(clean_id)

        if not job_dir:
            exit_with_error(f"Job {clean_id} not found.", command="history", json_mode=json_output)
            return

        timeline = TimelineManager()
        events = timeline.list_events(job_dir)

        if json_output:
            emit_json([e.to_dict() for e in events], command="history")
            return

        if not events:
            click.echo()
            click.echo(f"No business events recorded for job {clean_id}.")
            click.echo()
            return

        click.echo()
        click.secho(f"BUSINESS EVENT TIMELINE — {clean_id}", bold=True, fg="cyan")
        click.echo("-" * 75)
        click.secho(f"{'EVENT ID':<10} {'TIMESTAMP':<24} {'EVENT TYPE':<24} {'STATUS'}", bold=True)
        click.echo("-" * 75)
        for e in events:
            color = (
                "green" if e.status == "SUCCESS" else ("yellow" if e.status == "WARN" else "cyan")
            )
            rel = f" [{e.related_id}]" if e.related_id else ""
            click.echo(
                f"{e.event_id:<10} {e.timestamp[:19]:<24} {e.event_type + rel:<24} ", nl=False
            )
            click.secho(e.status, fg=color)
        click.echo("-" * 75)
        click.echo(f"Total: {len(events)} event(s)\n")
