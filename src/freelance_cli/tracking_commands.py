"""Time tracking and profitability CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Callable

import click

from packages.workspace.manager import WorkspaceManager


def register_tracking_commands(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.group()
    def timer() -> None:
        """Track working time and development sessions for jobs."""

    @timer.command("start")
    @click.argument("job_id")
    @click.option(
        "--activity",
        type=str,
        default="development",
        help="Activity type (development, debugging, research, communication, handoff).",
    )
    def timer_start(job_id: str, activity: str) -> None:
        """Start recording a work session."""
        from packages.tracking.timer import TimeTracker

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        tracker = TimeTracker()
        entry = tracker.start_timer(job_dir, job_id, activity)
        click.secho(f"✓ Timer started for {job_id} [{entry.id}]", fg="green", bold=True)
        click.echo(f"  Activity:   {entry.activity}")
        click.echo(f"  Started at: {entry.start_time}")

    @timer.command("stop")
    @click.argument("job_id", required=False, default=None)
    @click.option("--note", type=str, default="", help="Session note or description.")
    def timer_stop(job_id: str | None, note: str) -> None:
        """Stop active recording session and log elapsed time."""
        from packages.tracking.timer import TimeTracker

        manager = manager_factory()

        target_job_id = job_id.upper() if job_id else None
        if not target_job_id:
            # Search for active timer across active jobs
            for j in manager.list_jobs():
                j_dir = manager.get_job_dir(j.id)
                if j_dir:
                    t_log = TimeTracker().get_time_log(j_dir, j.id)
                    if t_log.active_entry:
                        target_job_id = j.id
                        break

        if not target_job_id:
            click.secho("✗ No active timer session found.", fg="red", err=True)
            sys.exit(1)

        job_dir = manager.get_job_dir(target_job_id)
        if not job_dir:
            click.secho(f"✗ Job {target_job_id} not found.", fg="red", err=True)
            sys.exit(1)

        tracker = TimeTracker()
        try:
            stopped = tracker.stop_timer(job_dir, target_job_id, note)
        except ValueError as exc:
            click.secho(f"✗ {exc}", fg="red", err=True)
            sys.exit(1)

        click.secho(f"✓ Timer stopped for {target_job_id} [{stopped.id}]", fg="green", bold=True)
        dur_h = stopped.duration_minutes / 60.0
        click.echo(f"  Duration:   {stopped.duration_minutes:.1f} min ({dur_h:.2f}h)")
        if stopped.note:
            click.echo(f"  Note:       {stopped.note}")

    @timer.command("status")
    @click.argument("job_id", required=False, default=None)
    def timer_status(job_id: str | None) -> None:
        """Check status of active timer session."""
        from packages.tracking.timer import TimeTracker

        manager = manager_factory()
        tracker = TimeTracker()

        if job_id:
            clean_id = job_id.upper()
            job_dir = manager.get_job_dir(clean_id)
            if not job_dir:
                click.secho(f"✗ Job {clean_id} not found.", fg="red", err=True)
                sys.exit(1)
            t_log = tracker.get_time_log(job_dir, clean_id)
            if t_log.active_entry:
                click.secho(f"● Timer ACTIVE for {clean_id}", fg="green", bold=True)
                click.echo(f"  Session:    {t_log.active_entry.id}")
                click.echo(f"  Activity:   {t_log.active_entry.activity}")
                click.echo(f"  Started:    {t_log.active_entry.start_time}")
                click.echo(f"  Total logged: {t_log.total_duration_hours:.2f}h")
            else:
                click.echo(
                    f"No active timer for {clean_id}. "
                    f"Total logged: {t_log.total_duration_hours:.2f}h"
                )
            return

        # Check all active jobs
        found_active = False
        for j in manager.list_jobs():
            j_dir = manager.get_job_dir(j.id)
            if j_dir:
                t_log = tracker.get_time_log(j_dir, j.id)
                if t_log.active_entry:
                    found_active = True
                    click.secho(f"● Timer ACTIVE for {j.id} ({j.client})", fg="green", bold=True)
                    click.echo(f"  Session:    {t_log.active_entry.id}")
                    click.echo(f"  Activity:   {t_log.active_entry.activity}")
                    click.echo(f"  Started:    {t_log.active_entry.start_time}")

        if not found_active:
            click.echo("No active timer running.")

    @timer.command("log")
    @click.argument("job_id")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def timer_log(job_id: str, json_output: bool) -> None:
        """Display time log and recorded sessions for a job."""
        import json as _json

        from packages.tracking.timer import TimeTracker

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        tracker = TimeTracker()
        time_log = tracker.get_time_log(job_dir, job_id)

        if json_output:
            click.echo(_json.dumps(time_log.to_dict(), indent=2, ensure_ascii=False))
            return

        click.echo()
        click.secho(f"TIME LOG — {job_id}", bold=True)
        mins = time_log.total_duration_minutes
        click.echo(f"Total Logged: {time_log.total_duration_hours:.2f}h ({mins:.1f} mins)")
        click.echo("-" * 65)

        if not time_log.entries:
            click.echo("No completed time sessions logged.")
        else:
            click.secho(f"{'SESSION ID':<14} {'ACTIVITY':<16} {'DURATION':<12} {'NOTE'}", bold=True)
            for e in time_log.entries:
                dur_str = f"{e.duration_minutes:.1f}m ({e.duration_minutes / 60.0:.2f}h)"
                click.echo(f"{e.id:<14} {e.activity:<16} {dur_str:<12} {e.note}")

        if time_log.active_entry:
            click.echo()
            act_id = time_log.active_entry.id
            act_type = time_log.active_entry.activity
            click.secho(f"● Active session: {act_id} ({act_type})", fg="green")
        click.echo()

    # ──────────────────── Profitability / Stats ──────────────────────────

    @main.command("stats")
    @click.argument("job_id")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def stats(job_id: str, json_output: bool) -> None:
        """Calculate and display profitability analysis for a job."""
        import json as _json

        from packages.tracking.profitability import ProfitabilityCalculator

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        calc = ProfitabilityCalculator()
        report = calc.calculate(job_id, job_dir)

        if json_output:
            click.echo(_json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            return

        click.echo()
        click.echo(report.summary())
        click.echo()
