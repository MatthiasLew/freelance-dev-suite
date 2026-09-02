"""Freelance Dev Suite — main CLI entrypoint.

Usage:
    freelance job new
    freelance jobs
    freelance status <JOB-ID>
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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
@click.option(
    "--from-text", "from_text", type=str, default=None, help="Generate from raw text description."
)
@click.option(
    "--from-file",
    "from_file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Generate from file.",
)
@click.option(
    "--confirm", "confirm_flag", is_flag=True, help="Mark requirements as CLIENT_CONFIRMED."
)
@click.option(
    "--confirmed-by",
    "confirmed_by",
    type=str,
    default="client",
    help="Client name or note for confirmation.",
)
@click.option(
    "--changed",
    "changed_note",
    type=str,
    default=None,
    help="Mark requirements as CHANGED with revision note.",
)
@click.option(
    "--check",
    "check_item",
    type=str,
    default=None,
    help="Mark item or criterion ID/index as completed.",
)
@click.option(
    "--uncheck",
    "uncheck_item",
    type=str,
    default=None,
    help="Mark item or criterion ID/index as incomplete.",
)
@click.option(
    "--checklist", "checklist_view", is_flag=True, help="Display actionable work checklist."
)
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def requirements(
    job_id: str,
    from_text: str | None,
    from_file: Path | None,
    confirm_flag: bool,
    confirmed_by: str,
    changed_note: str | None,
    check_item: str | None,
    uncheck_item: str | None,
    checklist_view: bool,
    json_output: bool,
) -> None:
    """Create, view, and track requirements and acceptance checklist for a job."""
    import json as _json

    from packages.requirements.generator import (
        generate_requirements,
        parse_requirements_markdown,
    )
    from packages.requirements.models import RequirementsSpec

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

    analysis_dir = job_dir / "analysis"
    client_dir = job_dir / "client"
    work_dir = job_dir / "work"
    for d in (analysis_dir, client_dir, work_dir):
        d.mkdir(parents=True, exist_ok=True)

    json_path = analysis_dir / "requirements.json"
    req_md_path = client_dir / "requirements.md"
    checklist_md_path = work_dir / "checklist.md"
    intake_path = analysis_dir / "intake.json"
    original_req_path = client_dir / "original-request.md"

    intake_data: dict[str, Any] | None = None
    if intake_path.exists():
        try:
            with open(intake_path, encoding="utf-8") as f:
                intake_data = _json.load(f)
        except (OSError, _json.JSONDecodeError):
            intake_data = None

    spec: RequirementsSpec | None = None

    # 1. Generate from text / file if requested
    if from_text is not None or from_file is not None:
        raw_text = (
            from_text
            if from_text is not None
            else from_file.read_text(encoding="utf-8")  # type: ignore[union-attr]
        )
        spec = generate_requirements(
            raw_text,
            job_id=job_id,
            title=found_job.description,
            intake_context=intake_data,
        )
    # 2. Or load from requirements.json if exists
    elif json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                spec = RequirementsSpec.from_dict(_json.load(f))
        except (OSError, _json.JSONDecodeError):
            spec = None

    # 3. Or load from client/requirements.md if edited manually
    if spec is None and req_md_path.exists():
        try:
            spec = parse_requirements_markdown(
                req_md_path.read_text(encoding="utf-8"), job_id=job_id
            )
        except OSError:
            spec = None

    # 4. Or generate initial specification from job details / original request
    if spec is None:
        raw_text = ""
        if original_req_path.exists():
            try:
                raw_text = original_req_path.read_text(encoding="utf-8")
            except OSError:
                raw_text = ""
        if not raw_text.strip():
            raw_text = f"{found_job.description}\n{found_job.notes}".strip()

        spec = generate_requirements(
            raw_text,
            job_id=job_id,
            title=found_job.description,
            intake_context=intake_data,
        )

    # Apply actions
    if confirm_flag:
        spec.confirm(confirmed_by=confirmed_by)
    elif changed_note is not None:
        spec.mark_changed(note=changed_note)

    if check_item is not None and not spec.toggle_item(check_item, completed=True):
        click.secho(f"⚠ Item or index '{check_item}' not found in checklist.", fg="yellow")

    if uncheck_item is not None and not spec.toggle_item(uncheck_item, completed=False):
        click.secho(f"⚠ Item or index '{uncheck_item}' not found in checklist.", fg="yellow")

    # Persist all 3 representations
    with open(json_path, "w", encoding="utf-8") as f:
        _json.dump(spec.to_dict(), f, indent=2, ensure_ascii=False)

    req_md_path.write_text(spec.to_markdown(), encoding="utf-8")
    checklist_md_path.write_text(spec.to_checklist_markdown(), encoding="utf-8")

    # Output formatting
    if json_output:
        click.echo(_json.dumps(spec.to_dict(), indent=2, ensure_ascii=False))
        return

    if checklist_view:
        click.echo(spec.to_checklist_markdown())
        return

    click.echo()
    if spec.approval_state == "CLIENT_CONFIRMED":
        status_color = "green"
    elif spec.approval_state == "DRAFT":
        status_color = "yellow"
    else:
        status_color = "magenta"

    click.secho(f"REQUIREMENTS SPECIFICATION — {job_id}", fg=status_color, bold=True)
    click.echo("─" * 55)
    click.echo(spec.summary())
    click.echo()
    click.echo(f"  • Requirements spec: {req_md_path}")
    click.echo(f"  • Work checklist:    {checklist_md_path}")
    click.echo(f"  • JSON data:         {json_path}")
    click.echo()


@main.command("templates")
def templates_list() -> None:
    """List available project starter templates."""
    from packages.bootstrap.templates import list_templates

    tmpls = list_templates()
    click.echo()
    click.secho(f"{'TEMPLATE':<20} {'LANGUAGE':<10} {'DESCRIPTION'}", bold=True)
    click.echo("─" * 80)
    for t in tmpls:
        click.echo(f"{t.name:<20} {t.language:<10} {t.description}")
    click.echo()


@main.command("bootstrap")
@click.argument("template_name")
@click.option("--name", "project_name", type=str, default="", help="Project name.")
@click.option(
    "--path",
    "target_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Target directory path.",
)
@click.option("--description", type=str, default="", help="Project description.")
@click.option("--no-git", is_flag=True, help="Do not initialize git repository.")
@click.option("--bootstrap", "run_ai_bootstrap", is_flag=True, help="Run ai-dev bootstrap.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def bootstrap(
    template_name: str,
    project_name: str,
    target_path: Path | None,
    description: str,
    no_git: bool,
    run_ai_bootstrap: bool,
    json_output: bool,
) -> None:
    """Bootstrap a new standalone project from a template."""
    import json as _json

    from packages.bootstrap.scaffolder import scaffold_project

    dest = target_path or Path.cwd() / (project_name or template_name)
    proj_name = project_name or dest.name

    try:
        result = scaffold_project(
            target_dir=dest,
            template_name=template_name,
            project_name=proj_name,
            description=description,
            init_git=not no_git,
            run_bootstrap=run_ai_bootstrap,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(_json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    click.echo()
    click.secho(f"✓ Project bootstrapped from {template_name}", fg="green", bold=True)
    click.echo("─" * 55)
    click.echo(result.summary())
    click.echo()


@main.command("start")
@click.argument("job_id")
@click.option(
    "--template",
    "template_name",
    type=str,
    default="python-cli",
    help="Starter template name (use 'freelance templates' to view all).",
)
@click.option(
    "--path",
    "custom_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom project destination path.",
)
@click.option("--no-git", is_flag=True, help="Do not initialize git repository.")
@click.option("--bootstrap", "run_ai_bootstrap", is_flag=True, help="Run ai-dev bootstrap.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def start_job(
    job_id: str,
    template_name: str,
    custom_path: Path | None,
    no_git: bool,
    run_ai_bootstrap: bool,
    json_output: bool,
) -> None:
    """Bootstrap and start implementation for a freelance job."""
    import json as _json

    from packages.bootstrap.scaffolder import scaffold_project
    from packages.requirements.models import RequirementsSpec

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

    target_dir = custom_path or (job_dir / "project")

    # Load requirements specification if already generated
    req_spec: RequirementsSpec | None = None
    req_json_path = job_dir / "analysis" / "requirements.json"
    if req_json_path.exists():
        try:
            with open(req_json_path, encoding="utf-8") as f:
                req_spec = RequirementsSpec.from_dict(_json.load(f))
        except (OSError, _json.JSONDecodeError):
            req_spec = None

    try:
        result = scaffold_project(
            target_dir=target_dir,
            template_name=template_name,
            project_name=f"{job_id}-{found_job.client}",
            description=found_job.description,
            requirements_spec=req_spec,
            init_git=not no_git,
            run_bootstrap=run_ai_bootstrap,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # Update job repository and status
    found_job.repository = str(target_dir.resolve())
    if found_job.status in {"LEAD", "ANALYSIS", "WAITING_FOR_CLIENT", "ACCEPTED"}:
        found_job.change_status("IN_PROGRESS", f"Bootstrapped with {template_name}")

    from packages.workspace.storage import save_job

    save_job(found_job, manager.config.workspace_path)

    if json_output:
        out_payload = {
            "job": found_job.to_dict(),
            "scaffold": result.to_dict(),
        }
        click.echo(_json.dumps(out_payload, indent=2, ensure_ascii=False))
        return

    click.echo()
    click.secho(f"✓ Started {job_id} ({template_name})", fg="green", bold=True)
    click.echo("─" * 55)
    click.echo(f"  Client:       {found_job.client}")
    click.echo(f"  Description:  {found_job.description}")
    click.echo(f"  Status:       {found_job.status}")
    click.echo(f"  Repository:   {found_job.repository}")
    click.echo(f"  Files:        {len(result.files_created)} scaffolded")
    if result.git_initialized:
        click.echo("  Git:          Initialized with initial commit")
    click.echo()


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
    manager = _get_manager()
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
    click.echo("─" * 60)
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
    manager = _get_manager()
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

    found_job.change_status("DELIVERED", notes or "Job closed and delivered to client.")
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
    click.echo("─" * 55)
    click.echo(f"  Client:     {found_job.client}")
    click.echo(f"  Status:     {found_job.status}")
    if archived_path:
        click.echo(f"  Archived:   {archived_path}")
    click.echo()



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
