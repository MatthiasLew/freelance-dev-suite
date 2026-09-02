"""Freelance Dev Suite — main CLI entrypoint.

Usage:
    freelance job new
    freelance jobs
    freelance status <JOB-ID>
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from freelance_cli import __version__
from freelance_cli.models.job import JobSource, JobStatus
from packages.workspace.manager import WorkspaceManager


def _get_manager() -> WorkspaceManager:
    """Create a WorkspaceManager with default config."""
    return WorkspaceManager()


# ──────────────────────────── Root group ────────────────────────────


@click.group()
@click.version_option(version=__version__, prog_name="freelance")
def main() -> None:
    """Freelance Dev Suite — manage freelance jobs from intake to handoff."""


# ──────────────────────────── Job group ─────────────────────────────


@main.group()
def job() -> None:
    """Manage individual jobs."""


@job.command("new")
@click.option("--client", prompt="Client name", help="Client name or company.")
@click.option("--description", prompt="Task description", help="Short description of the job.")
@click.option(
    "--source",
    type=click.Choice([s.value for s in JobSource], case_sensitive=False),
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
    manager = _get_manager()
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


# ──────────────────────────── Jobs list ─────────────────────────────


@main.command("jobs")
@click.option("--all", "show_all", is_flag=True, help="Include finished/rejected jobs.")
def jobs_list(show_all: bool) -> None:
    """List all active jobs."""
    manager = _get_manager()
    jobs = manager.list_jobs(include_finished=show_all)

    if not jobs:
        click.echo("No active jobs found.")
        click.echo('Use "freelance job new" to create one.')
        return

    from freelance_cli.models.job import Job as JobModel

    click.echo()
    click.secho(JobModel.summary_header(), bold=True)
    click.echo("─" * 90)
    for j in jobs:
        # Color-code by status
        color = _status_color(j.status)
        click.secho(j.summary_line(), fg=color)
    click.echo()
    click.echo(f"Total: {len(jobs)} job(s)")
    click.echo()


# ──────────────────────────── Status ────────────────────────────────


@main.command("status")
@click.argument("job_id")
def status(job_id: str) -> None:
    """Show detailed status of a specific job."""
    job_id = job_id.upper()
    manager = _get_manager()
    found_job = manager.get_job(job_id)

    if found_job is None:
        click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
        sys.exit(1)

    click.echo()
    color = _status_color(found_job.status)
    click.secho(f"── {found_job.id} ──", fg=color, bold=True)
    click.echo()
    click.echo(found_job.detail_view())

    job_dir = manager.get_job_dir(found_job.id)
    if job_dir:
        click.echo(f"\nWorkspace:   {job_dir}")
    click.echo()


# ──────────────────── Status update ─────────────────────────────────


@job.command("update")
@click.argument("job_id")
@click.option(
    "--status",
    "new_status",
    type=click.Choice([s.value for s in JobStatus], case_sensitive=False),
    required=True,
    help="New status.",
)
@click.option("--note", type=str, default="", help="Note for the status change.")
def job_update(job_id: str, new_status: str, note: str) -> None:
    """Update a job's status."""
    job_id = job_id.upper()
    manager = _get_manager()
    updated = manager.update_job_status(job_id, new_status, note)

    if updated is None:
        click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
        sys.exit(1)

    click.secho(f"✓ {updated.id} → {updated.status}", fg="green", bold=True)


# ──────────────────── Placeholder commands ──────────────────────────


@main.command("analyze")
@click.argument("job_id")
@click.option(
    "--check-mode",
    type=click.Choice(["fast", "full"]),
    default="full",
    show_default=True,
    help="Validation depth passed to ai-dev check.",
)
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def analyze(job_id: str, check_mode: str, json_output: bool) -> None:
    """Run project intake analysis on a job's repository."""
    import json as _json

    job_id = job_id.upper()
    manager = _get_manager()
    found_job = manager.get_job(job_id)

    if found_job is None:
        click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
        sys.exit(1)

    repo_path = found_job.repository
    if not repo_path:
        click.secho(f"✗ Job {job_id} has no repository set.", fg="red", err=True)
        sys.exit(1)

    repo = Path(repo_path).resolve()
    if not repo.exists():
        click.secho(f"✗ Repository path does not exist: {repo}", fg="red", err=True)
        sys.exit(1)

    if not json_output:
        click.echo(f"\n🔍 Analyzing {repo} for {job_id}...\n")

    # Run intake analysis
    from packages.intake.analyzer import AIDevIntegrationError, analyze_project

    try:
        intake = analyze_project(
            str(repo),
            task_description=found_job.description,
            validation_mode=check_mode,
        )
    except (AIDevIntegrationError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    # Run AI cost estimate
    from packages.ai_cost.estimator import estimate_ai_cost
    from packages.ai_cost.pricing import load_model_pricing

    pricing_path = (
        Path(manager.config.model_pricing_path) if manager.config.model_pricing_path else None
    )
    try:
        models = load_model_pricing(pricing_path)
        ai_cost = estimate_ai_cost(
            loc=intake.loc,
            source_files=intake.source_files,
            complexity=intake.complexity,
            task_description=found_job.description,
            model_name=manager.config.default_model,
            context_tokens=intake.context_tokens,
            models=models,
            exchange_rate=manager.config.usd_to_pln_rate,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # Save results to job workspace
    job_dir = manager.get_job_dir(job_id)
    if job_dir:
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        with open(analysis_dir / "intake.json", "w", encoding="utf-8") as f:
            _json.dump(intake.to_dict(), f, indent=2, ensure_ascii=False)
        with open(analysis_dir / "ai-cost.json", "w", encoding="utf-8") as f:
            _json.dump(ai_cost.to_dict(), f, indent=2, ensure_ascii=False)

    # Update job status
    if found_job.status == "LEAD":
        manager.update_job_status(job_id, "ANALYSIS", "Intake analysis completed")

    if json_output:
        click.echo(_json.dumps({"intake": intake.to_dict(), "ai_cost": ai_cost.to_dict()}))
        return

    # Display results
    click.secho("PROJECT ANALYSIS", fg="cyan", bold=True)
    click.echo("─" * 50)
    click.echo(intake.summary())

    click.secho("AI COST ESTIMATE", fg="cyan", bold=True)
    click.echo("─" * 50)
    click.echo(ai_cost.summary())

    click.secho("✓ Analysis saved to workspace", fg="green")
    click.echo()


@main.command("estimate")
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def estimate(job_id: str, json_output: bool) -> None:
    """Generate a full quote estimate based on prior analysis."""
    import json as _json

    job_id = job_id.upper()
    manager = _get_manager()
    found_job = manager.get_job(job_id)

    if found_job is None:
        click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
        sys.exit(1)

    job_dir = manager.get_job_dir(job_id)
    if not job_dir:
        click.secho(f"✗ Workspace not found for {job_id}.", fg="red", err=True)
        sys.exit(1)

    # Load analysis data
    intake_path = job_dir / "analysis" / "intake.json"
    ai_cost_path = job_dir / "analysis" / "ai-cost.json"

    if not intake_path.exists() or not ai_cost_path.exists():
        click.secho(
            f"✗ Analysis not found. Run 'freelance analyze {job_id}' first.",
            fg="red",
            err=True,
        )
        sys.exit(1)

    with open(intake_path, encoding="utf-8") as f:
        intake_data = _json.load(f)
    with open(ai_cost_path, encoding="utf-8") as f:
        ai_cost_data = _json.load(f)

    # Calculate quote
    from packages.estimator.calculator import calculate_quote

    config = manager.config
    quote = calculate_quote(
        estimated_hours_min=intake_data["estimated_hours_min"],
        estimated_hours_max=intake_data["estimated_hours_max"],
        ai_cost_pln=ai_cost_data["cost_pln_expected"],
        risk_level=intake_data["risk_level"],
        hourly_rate=config.pricing.hourly_rate,
        client_budget_pln=found_job.budget_pln,
        deadline=found_job.deadline,
        minimum_job_price=config.pricing.minimum_job_price,
        risk_buffer_percent=config.pricing.risk_buffer_percent,
    )

    # Save estimate
    analysis_dir = job_dir / "analysis"
    with open(analysis_dir / "estimate.json", "w", encoding="utf-8") as f:
        _json.dump(quote.to_dict(), f, indent=2, ensure_ascii=False)

    if json_output:
        click.echo(_json.dumps(quote.to_dict()))
        return

    # Display results
    click.echo()
    click.secho("QUOTE ESTIMATE", fg="cyan", bold=True)
    click.echo("─" * 50)
    click.echo(quote.summary())

    # Budget check
    if found_job.budget_pln:
        if quote.is_budget_sufficient(found_job.budget_pln):
            click.secho(
                f"✓ Client budget ({found_job.budget_pln:.0f} PLN) covers minimum price.",
                fg="green",
            )
        else:
            click.secho(
                f"✗ Client budget ({found_job.budget_pln:.0f} PLN) is below "
                f"minimum ({quote.minimum_technical_price_pln:.0f} PLN).",
                fg="red",
            )

    click.secho("\n✓ Estimate saved to workspace", fg="green")
    click.echo()


@main.command("requirements")
@click.argument("job_id")
def requirements(job_id: str) -> None:
    """Create a requirements checklist. (Not yet implemented)"""
    click.secho(f"⚠ requirements is not yet implemented for {job_id.upper()}", fg="yellow")


@main.command("start")
@click.argument("job_id")
def start_job(job_id: str) -> None:
    """Bootstrap a project. (Not yet implemented)"""
    click.secho(f"⚠ start is not yet implemented for {job_id.upper()}", fg="yellow")


@main.command("handoff")
@click.argument("job_id")
def handoff(job_id: str) -> None:
    """Run final QA and create handoff package. (Not yet implemented)"""
    click.secho(f"⚠ handoff is not yet implemented for {job_id.upper()}", fg="yellow")


@main.command("finish")
@click.argument("job_id")
def finish(job_id: str) -> None:
    """Close and archive a completed job. (Not yet implemented)"""
    click.secho(f"⚠ finish is not yet implemented for {job_id.upper()}", fg="yellow")


# ──────────────────── Bug group ─────────────────────────────────────


@main.group()
def bug() -> None:
    """Manage bug reports."""


@bug.command("add")
@click.argument("job_id")
def bug_add(job_id: str) -> None:
    """Add a bug report. (Not yet implemented)"""
    click.secho(f"⚠ bug add is not yet implemented for {job_id.upper()}", fg="yellow")


@bug.command("list")
@click.argument("job_id")
def bug_list(job_id: str) -> None:
    """List bug reports. (Not yet implemented)"""
    click.secho(f"⚠ bug list is not yet implemented for {job_id.upper()}", fg="yellow")


# ──────────────────── Scope group ───────────────────────────────────


@main.group()
def scope() -> None:
    """Scope change detection."""


@scope.command("check")
@click.argument("job_id")
def scope_check(job_id: str) -> None:
    """Detect scope changes. (Not yet implemented)"""
    click.secho(f"⚠ scope check is not yet implemented for {job_id.upper()}", fg="yellow")


# ──────────────────── Helpers ───────────────────────────────────────


def _status_color(status: str) -> str:
    """Map job status to a terminal color."""
    color_map: dict[str, str] = {
        "LEAD": "cyan",
        "ANALYSIS": "blue",
        "WAITING_FOR_CLIENT": "yellow",
        "ACCEPTED": "green",
        "IN_PROGRESS": "green",
        "TESTING": "magenta",
        "READY_FOR_HANDOFF": "bright_green",
        "DELIVERED": "bright_green",
        "CLOSED": "white",
        "REJECTED": "red",
    }
    return color_map.get(status, "white")


if __name__ == "__main__":
    main()
