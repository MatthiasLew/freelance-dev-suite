"""Click commands for repository-backed development work sessions."""

from __future__ import annotations

import json
from typing import Any

import click

from packages.work.manager import WorkManager
from packages.work.models import WorkSession


def _work_manager() -> WorkManager:
    # Import lazily so the root CLI can inject its test workspace manager.
    from freelance_cli.cli import _get_manager

    return WorkManager(_get_manager())


def _emit_error(exc: Exception) -> None:
    raise click.ClickException(str(exc)) from exc


def _session_payload(manager: WorkManager, session: WorkSession) -> dict[str, Any]:
    return {**session.to_dict(), "elapsed_minutes": manager.elapsed_minutes(session)}


def _show_session(manager: WorkManager, session: WorkSession) -> None:
    elapsed = manager.elapsed_minutes(session)
    click.secho(f"{session.id} — {session.status}", bold=True)
    click.echo(f"  Job:          {session.job_id}")
    click.echo(f"  Task:         {session.task}")
    click.echo(f"  Agent/model:  {session.agent} / {session.model or 'not recorded'}")
    click.echo(f"  Time:         {elapsed:.2f} min")
    click.echo(f"  Tokens:       {session.total_tokens}")
    click.echo(f"  AI cost:      {session.ai_cost_pln:.4f} PLN")
    click.echo(f"  Validation:   {session.validation_status}")
    click.echo(f"  Scope:        {session.scope_classification or 'not checked'}")
    if session.related_requirements:
        click.echo(f"  Requirements: {', '.join(session.related_requirements)}")


@click.group()
def work() -> None:
    """Manage real development sessions connected to ai-dev-cli-tools."""


@work.command("start")
@click.argument("job_id")
@click.option("--task", required=True, help="Concrete development task.")
@click.option("--agent", default="generic", show_default=True, help="AI agent/client name.")
@click.option("--model", default=None, help="AI model used for this work session.")
@click.option(
    "--requirement",
    "requirements",
    multiple=True,
    help="Related requirement ID; may be repeated.",
)
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def work_start(
    job_id: str,
    task: str,
    agent: str,
    model: str | None,
    requirements: tuple[str, ...],
    json_output: bool,
) -> None:
    """Prepare context, check scope, and start a work timer."""
    manager = _work_manager()
    try:
        session = manager.start(
            job_id,
            task,
            agent=agent.lower(),
            model=model,
            related_requirements=list(requirements),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        _emit_error(exc)
        return
    if json_output:
        click.echo(json.dumps(_session_payload(manager, session), indent=2, ensure_ascii=False))
        return
    click.secho(f"✓ Started {session.id}", fg="green", bold=True)
    _show_session(manager, session)
    if session.scope_classification not in {"", "IN_SCOPE"}:
        click.secho(
            "⚠ Task is not classified as fully in scope; review the saved scope analysis.",
            fg="yellow",
        )


@work.command("status")
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def work_status(job_id: str, json_output: bool) -> None:
    """Show the current or most recent session for a job."""
    manager = _work_manager()
    try:
        session = manager.current_for_job(job_id)
    except (OSError, ValueError) as exc:
        _emit_error(exc)
        return
    if session is None:
        raise click.ClickException(f"No work sessions found for {job_id.upper()}.")
    if json_output:
        click.echo(json.dumps(_session_payload(manager, session), indent=2, ensure_ascii=False))
        return
    _show_session(manager, session)


@work.command("finish")
@click.argument("work_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def work_finish(work_id: str, json_output: bool) -> None:
    """Validate changes, stop the timer, and finalize a work session."""
    manager = _work_manager()
    try:
        session = manager.finish(work_id)
    except (OSError, RuntimeError, ValueError) as exc:
        _emit_error(exc)
        return
    if json_output:
        click.echo(json.dumps(_session_payload(manager, session), indent=2, ensure_ascii=False))
        return
    color = "green" if session.status == "VERIFIED" else "yellow"
    click.secho(f"✓ Finished {session.id}: {session.status}", fg=color, bold=True)
    _show_session(manager, session)


@work.command("resume")
@click.argument("work_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def work_resume(work_id: str, json_output: bool) -> None:
    """Resume a session using incremental acknowledged ai-dev context."""
    manager = _work_manager()
    try:
        session = manager.resume(work_id)
    except (OSError, RuntimeError, ValueError) as exc:
        _emit_error(exc)
        return
    if json_output:
        click.echo(json.dumps(_session_payload(manager, session), indent=2, ensure_ascii=False))
        return
    click.secho(f"✓ Resumed {session.id}", fg="green", bold=True)
    _show_session(manager, session)


@work.command("list")
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def work_list(job_id: str, json_output: bool) -> None:
    """List all development sessions for a job."""
    manager = _work_manager()
    try:
        sessions = manager.list_for_job(job_id)
    except (OSError, ValueError) as exc:
        _emit_error(exc)
        return
    if json_output:
        click.echo(
            json.dumps(
                [_session_payload(manager, session) for session in sessions],
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if not sessions:
        click.echo(f"No work sessions found for {job_id.upper()}.")
        return
    click.echo(f"{'WORK ID':<12} {'STATUS':<12} {'MIN':>9} {'TOKENS':>10}  TASK")
    click.echo("-" * 72)
    for session in sessions:
        click.echo(
            f"{session.id:<12} {session.status:<12} "
            f"{manager.elapsed_minutes(session):>9.2f} {session.total_tokens:>10}  "
            f"{session.task[:35]}"
        )
