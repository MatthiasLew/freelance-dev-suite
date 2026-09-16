"""Freelance Dev Suite — main CLI entrypoint.

Usage:
    freelance job new
    freelance jobs
    freelance status <JOB-ID>
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import click

from freelance_cli import __version__
from freelance_cli.archive_commands import register_archive_commands
from freelance_cli.bug_commands import register_bug_commands
from freelance_cli.config_commands import register_config_commands
from freelance_cli.doctor_commands import register_doctor_command
from freelance_cli.handoff_commands import register_handoff_commands
from freelance_cli.history_commands import register_history_commands
from freelance_cli.job_commands import register_job_commands
from freelance_cli.mcp_commands import register_mcp_commands
from freelance_cli.output import emit_json, exit_with_error
from freelance_cli.requirements_commands import register_requirements_command
from freelance_cli.scope_commands import register_scope_commands
from freelance_cli.tracking_commands import register_tracking_commands
from freelance_cli.work_commands import work
from packages.storage_utils import StateError, atomic_write_json, safe_read_json
from packages.timeline.manager import TimelineManager
from packages.workspace.manager import WorkspaceManager


def _get_manager() -> WorkspaceManager:
    """Create a WorkspaceManager with default config."""
    return WorkspaceManager()


def _manager_factory() -> WorkspaceManager:
    """Resolve the manager lazily so tests and embeddings can inject it."""
    return _get_manager()


def _configure_streams() -> None:
    """Configure stdout and stderr to UTF-8 with replacement error handling.

    Prevents UnicodeEncodeError on Windows default console code pages (e.g. CP1250, CP437).
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")


_configure_streams()


# ──────────────────────────── Root group ────────────────────────────


@click.group()
@click.version_option(version=__version__, prog_name="freelance")
def main() -> None:
    """Freelance Dev Suite — manage freelance jobs from intake to handoff."""
    _configure_streams()


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

    job_id = job_id.upper()
    manager = _get_manager()
    found_job = manager.get_job(job_id)

    if found_job is None:
        exit_with_error(f"Job {job_id} not found.", command="analyze", json_mode=json_output)
        return

    repo_path = found_job.repository
    if not repo_path:
        exit_with_error(
            f"Job {job_id} has no repository set.", command="analyze", json_mode=json_output
        )
        return

    repo = Path(repo_path).resolve()
    if not repo.exists():
        exit_with_error(
            f"Repository path does not exist: {repo}", command="analyze", json_mode=json_output
        )
        return

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
        exit_with_error(str(exc), command="analyze", json_mode=json_output)
        return

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
        exit_with_error(str(exc), command="analyze", json_mode=json_output)
        return

    # Save results to job workspace
    job_dir = manager.get_job_dir(job_id)
    if job_dir:
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(analysis_dir / "intake.json", intake.to_dict())
        atomic_write_json(analysis_dir / "ai-cost.json", ai_cost.to_dict())
        TimelineManager().record_event(
            job_dir, job_id, "analysis_performed", metadata={"check_mode": check_mode}
        )

    # Update job status
    if found_job.status == "LEAD":
        manager.update_job_status(job_id, "ANALYSIS", "Intake analysis completed")

    if json_output:
        emit_json({"intake": intake.to_dict(), "ai_cost": ai_cost.to_dict()}, command="analyze")
        return

    # Display results
    click.secho("PROJECT ANALYSIS", fg="cyan", bold=True)
    click.echo("-" * 50)
    click.echo(intake.summary())

    click.secho("AI COST ESTIMATE", fg="cyan", bold=True)
    click.echo("-" * 50)
    click.echo(ai_cost.summary())

    click.secho("✓ Analysis saved to workspace", fg="green")
    click.echo()


@main.command("estimate")
@click.argument("job_id")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def estimate(job_id: str, json_output: bool) -> None:
    """Generate a full quote estimate based on prior analysis."""

    job_id = job_id.upper()
    manager = _get_manager()
    found_job = manager.get_job(job_id)

    if found_job is None:
        exit_with_error(f"Job {job_id} not found.", command="estimate", json_mode=json_output)
        return

    job_dir = manager.get_job_dir(job_id)
    if not job_dir:
        exit_with_error(
            f"Workspace not found for {job_id}.", command="estimate", json_mode=json_output
        )
        return

    # Load analysis data
    intake_path = job_dir / "analysis" / "intake.json"
    ai_cost_path = job_dir / "analysis" / "ai-cost.json"

    if not intake_path.exists() or not ai_cost_path.exists():
        exit_with_error(
            f"Analysis not found. Run 'freelance analyze {job_id}' first.",
            command="estimate",
            json_mode=json_output,
        )
        return

    try:
        intake_data = safe_read_json(intake_path)
        ai_cost_data = safe_read_json(ai_cost_path)
    except (OSError, StateError, ValueError) as exc:
        exit_with_error(
            f"Failed reading analysis data: {exc}", command="estimate", json_mode=json_output
        )
        return

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
    atomic_write_json(analysis_dir / "estimate.json", quote.to_dict())
    TimelineManager().record_event(
        job_dir,
        job_id,
        "estimate_created",
        metadata={"price_pln": quote.recommended_quote_min_pln},
    )

    if json_output:
        emit_json(quote.to_dict(), command="estimate")
        return

    # Display results
    click.echo()
    click.secho("QUOTE ESTIMATE", fg="cyan", bold=True)
    click.echo("-" * 50)
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


@main.command("templates")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def templates_list(json_output: bool) -> None:
    """List available project starter templates."""
    from packages.bootstrap.templates import list_templates

    tmpls = list_templates()
    if json_output:
        emit_json(
            [
                {
                    "name": t.name,
                    "language": t.language,
                    "description": t.description,
                    "default_dependencies": t.default_dependencies,
                }
                for t in tmpls
            ],
            command="templates",
        )
        return

    click.echo()
    click.secho(f"{'TEMPLATE':<20} {'LANGUAGE':<10} {'DESCRIPTION'}", bold=True)
    click.echo("-" * 80)
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
@click.option(
    "--dry-run", is_flag=True, help="Simulate bootstrap without writing files or initializing git."
)
@click.option("--explain", is_flag=True, help="Explain what bootstrap would do.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def bootstrap(
    template_name: str,
    project_name: str,
    target_path: Path | None,
    description: str,
    no_git: bool,
    run_ai_bootstrap: bool,
    dry_run: bool,
    explain: bool,
    json_output: bool,
) -> None:
    """Bootstrap a new standalone project from a template."""
    from packages.bootstrap.scaffolder import scaffold_project
    from packages.bootstrap.templates import generate_template_files, get_template

    dest = target_path or Path.cwd() / (project_name or template_name)
    proj_name = project_name or dest.name

    try:
        tmpl = get_template(template_name)
    except ValueError as exc:
        exit_with_error(str(exc), command="bootstrap", json_mode=json_output)
        return

    if explain or dry_run:
        simulated_files = list(
            generate_template_files(
                template_name=tmpl.name,
                project_name=proj_name,
                description=description,
            ).keys()
        )
        plan = {
            "mode": "explain" if explain else "dry-run",
            "template": tmpl.name,
            "language": tmpl.language,
            "target_dir": str(dest.resolve()),
            "project_name": proj_name,
            "files_to_generate": simulated_files,
            "init_git": not no_git,
            "run_bootstrap": run_ai_bootstrap,
        }
        if json_output:
            emit_json(plan, command="bootstrap")
            return
        click.echo()
        title = "EXPLAIN BOOTSTRAP PLAN" if explain else "DRY-RUN BOOTSTRAP (NO CHANGES MADE)"
        click.secho(title, fg="yellow" if dry_run else "cyan", bold=True)
        click.echo("-" * 55)
        click.echo(f"  Template:        {tmpl.name} ({tmpl.language})")
        click.echo(f"  Target Dir:      {dest.resolve()}")
        click.echo(f"  Project Name:    {proj_name}")
        click.echo(f"  Git Init:        {'Enabled' if not no_git else 'Disabled'}")
        click.echo(f"  ai-dev Bootstrap:{'Enabled' if run_ai_bootstrap else 'Disabled'}")
        click.echo(f"  Files ({len(simulated_files)}):")
        for f in simulated_files:
            click.echo(f"    • {f}")
        click.echo()
        return

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
        exit_with_error(str(exc), command="bootstrap", json_mode=json_output)
        return

    if json_output:
        emit_json(result.to_dict(), command="bootstrap")
        return

    click.echo()
    click.secho(f"✓ Project bootstrapped from {template_name}", fg="green", bold=True)
    click.echo("-" * 55)
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
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate starting the job without writing files or changing state.",
)
@click.option("--explain", is_flag=True, help="Explain what starting the job would do.")
@click.option("--json", "json_output", is_flag=True, help="Print structured JSON.")
def start_job(
    job_id: str,
    template_name: str,
    custom_path: Path | None,
    no_git: bool,
    run_ai_bootstrap: bool,
    dry_run: bool,
    explain: bool,
    json_output: bool,
) -> None:
    """Bootstrap and start implementation for a freelance job."""
    from packages.bootstrap.scaffolder import scaffold_project
    from packages.bootstrap.templates import generate_template_files, get_template
    from packages.requirements.models import RequirementsSpec

    job_id = job_id.upper()
    manager = _get_manager()
    found_job = manager.get_job(job_id)

    if found_job is None:
        exit_with_error(f"Job {job_id} not found.", command="start", json_mode=json_output)
        return

    job_dir = manager.get_job_dir(job_id)
    if not job_dir:
        exit_with_error(
            f"Workspace not found for {job_id}.",
            command="start",
            json_mode=json_output,
        )
        return

    target_dir = custom_path or (job_dir / "project")

    # Load requirements specification if already generated
    req_spec: RequirementsSpec | None = None
    req_json_path = job_dir / "analysis" / "requirements.json"
    if req_json_path.exists():
        try:
            req_data = safe_read_json(req_json_path)
            req_spec = RequirementsSpec.from_dict(req_data)
        except (OSError, StateError, ValueError):
            req_spec = None

    try:
        tmpl = get_template(template_name)
    except ValueError as exc:
        exit_with_error(str(exc), command="start", json_mode=json_output)
        return

    if explain or dry_run:
        simulated_files = list(
            generate_template_files(
                template_name=tmpl.name,
                project_name=f"{job_id}-{found_job.client}",
                description=found_job.description,
                requirements_spec=req_spec,
            ).keys()
        )
        plan = {
            "mode": "explain" if explain else "dry-run",
            "job_id": job_id,
            "current_status": found_job.status,
            "target_status": "IN_PROGRESS",
            "template": tmpl.name,
            "target_dir": str(target_dir.resolve()),
            "files_to_generate": simulated_files,
            "init_git": not no_git,
            "run_bootstrap": run_ai_bootstrap,
            "requirements_detected": req_spec is not None,
        }
        if json_output:
            emit_json(plan, command="start")
            return
        click.echo()
        title = (
            f"EXPLAIN START PLAN — {job_id}"
            if explain
            else f"DRY-RUN START — {job_id} (NO CHANGES MADE)"
        )
        click.secho(title, fg="yellow" if dry_run else "cyan", bold=True)
        click.echo("-" * 60)
        click.echo(f"  Job ID:          {job_id} ({found_job.client})")
        click.echo(f"  Status Change:   {found_job.status} -> IN_PROGRESS")
        click.echo(f"  Template:        {tmpl.name} ({tmpl.language})")
        click.echo(f"  Target Dir:      {target_dir.resolve()}")
        click.echo(f"  Git Init:        {'Enabled' if not no_git else 'Disabled'}")
        click.echo(f"  ai-dev Bootstrap:{'Enabled' if run_ai_bootstrap else 'Disabled'}")
        req_info = f"Loaded ({len(req_spec.requirements)} functional reqs)" if req_spec else "None"
        click.echo(f"  Requirements:    {req_info}")
        click.echo(f"  Files ({len(simulated_files)}):")
        for f in simulated_files:
            click.echo(f"    • {f}")
        click.echo()
        return

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
        exit_with_error(str(exc), command="start", json_mode=json_output)
        return

    # Update job repository and status
    found_job.repository = str(target_dir.resolve())
    if found_job.status in {"LEAD", "ANALYSIS", "WAITING_FOR_CLIENT", "ACCEPTED"}:
        found_job.change_status("IN_PROGRESS", f"Bootstrapped with {template_name}")

    from packages.workspace.storage import save_job

    save_job(found_job, manager.config.workspace_path)
    TimelineManager().record_event(
        job_dir,
        job_id,
        "job_started",
        metadata={"template": template_name, "repository": str(target_dir.resolve())},
    )

    if json_output:
        out_payload = {
            "job": found_job.to_dict(),
            "scaffold": result.to_dict(),
        }
        emit_json(out_payload, command="start")
        return

    click.echo()
    click.secho(f"✓ Started {job_id} ({template_name})", fg="green", bold=True)
    click.echo("-" * 55)
    click.echo(f"  Client:       {found_job.client}")
    click.echo(f"  Description:  {found_job.description}")
    click.echo(f"  Status:       {found_job.status}")
    click.echo(f"  Repository:   {found_job.repository}")
    click.echo(f"  Files:        {len(result.files_created)} scaffolded")
    if result.git_initialized:
        click.echo("  Git:          Initialized with initial commit")
    click.echo()


# ──────────────────── Portfolio & Calibration ────────────────────────


@main.command("portfolio")
@click.argument("job_id")
@click.option("--anonymize", is_flag=True, help="Anonymize client name and confidential details.")
@click.option(
    "--output",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Custom output file path.",
)
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def portfolio(
    job_id: str,
    anonymize: bool,
    output_file: Path | None,
    json_output: bool,
) -> None:
    """Generate professional Markdown case study from completed job."""

    from packages.portfolio.generator import PortfolioGenerator

    job_id = job_id.upper()
    manager = _get_manager()
    job_dir = manager.get_job_dir(job_id)
    if not job_dir:
        exit_with_error(f"Job {job_id} not found.", command="portfolio", json_mode=json_output)
        return

    gen = PortfolioGenerator()
    case_study, saved_path = gen.generate(
        job_id=job_id,
        job_dir=job_dir,
        anonymize=anonymize,
        output_path=output_file,
    )

    if json_output:
        out = {
            "case_study": case_study.to_dict(),
            "output_path": str(saved_path),
        }
        emit_json(out, command="portfolio")
        return

    click.echo()
    click.secho("✓ Case Study Generated Successfully!", fg="green", bold=True)
    click.echo(f"  Title:        {case_study.title}")
    click.echo(f"  Client:       {case_study.client_name}")
    click.echo(f"  Anonymized:   {case_study.is_anonymized}")
    click.echo(f"  Output file:  {saved_path}")
    click.echo()


@main.command("calibrate")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def calibrate(json_output: bool) -> None:
    """Analyze historical estimation accuracy and recommend calibration."""
    from packages.estimator.calibration import EstimatorCalibrator

    manager = _get_manager()
    calibrator = EstimatorCalibrator()
    result = calibrator.calibrate(manager)

    if json_output:
        emit_json(result, command="calibrate")
        return

    click.echo()
    click.secho("ESTIMATOR CALIBRATION & HISTORICAL ACCURACY", bold=True)
    click.echo("-" * 60)
    click.echo(f"  Jobs Analyzed:          {result['jobs_analyzed']}")
    click.echo(f"  Total Estimated Hours:  {result['total_estimated_hours']:.1f}h")
    click.echo(f"  Total Actual Hours:     {result['total_actual_hours']:.1f}h")
    click.echo(f"  Calibration Multiplier: {result['calibration_multiplier']}x")
    click.echo(f"  Average Variance:       {result['average_variance_percent']:+.1f}%")
    click.echo()
    click.secho(f"  Recommendation: {result['recommendation']}", fg="cyan")
    click.echo()


# ──────────────────── Client Communication & Pricing ──────────────────


@main.command("message")
@click.argument("job_id")
@click.argument(
    "stage",
    type=click.Choice(
        ["intake", "quote", "update", "demo", "delivery", "reminder", "scope-notice"],
        case_sensitive=False,
    ),
)
@click.option(
    "--lang",
    type=click.Choice(["pl", "en"], case_sensitive=False),
    default="pl",
    help="Message language (pl or en).",
)
@click.option("--notes", type=str, default="", help="Custom notes, questions, or details.")
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def message(
    job_id: str,
    stage: str,
    lang: str,
    notes: str,
    json_output: bool,
) -> None:
    """Generate professional client messages (emails, updates, handoff, proposals)."""
    from packages.communication.generator import MessageGenerator

    job_id = job_id.upper()
    manager = _get_manager()
    job_dir = manager.get_job_dir(job_id)
    if not job_dir:
        exit_with_error(f"Job {job_id} not found.", command="message", json_mode=json_output)
        return

    gen = MessageGenerator()
    msg = gen.generate(
        job_id=job_id,
        job_dir=job_dir,
        stage=stage,
        language=lang.lower(),
        notes=notes,
    )

    if json_output:
        emit_json(msg.to_dict(), command="message")
        return

    click.echo()
    click.secho(f"CLIENT MESSAGE DRAFT [{msg.stage.upper()}]", bold=True, fg="cyan")
    click.echo("-" * 65)
    click.echo(msg.to_markdown())
    click.echo("-" * 65)
    click.echo()


@main.command("pricing")
@click.option("--model", "model_name", type=str, default=None, help="Model name to update.")
@click.option(
    "--input-price",
    type=float,
    default=None,
    help="Input price per million tokens ($).",
)
@click.option(
    "--output-price",
    type=float,
    default=None,
    help="Output price per million tokens ($).",
)
@click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
def pricing(
    model_name: str | None,
    input_price: float | None,
    output_price: float | None,
    json_output: bool,
) -> None:
    """List or update model pricing for AI cost estimation."""

    from packages.ai_cost.pricing import (
        ModelPricing,
        load_model_pricing,
        save_model_pricing,
    )

    models = load_model_pricing()

    if model_name:
        if input_price is None or output_price is None:
            exit_with_error(
                "Both --input-price and --output-price are required when updating a model.",
                command="pricing",
                json_mode=json_output,
            )
            return

        models[model_name] = ModelPricing(
            name=model_name,
            input_per_million=input_price,
            output_per_million=output_price,
        )
        save_model_pricing(models)
        click.secho(
            f"✓ Updated pricing for {model_name}: ${input_price}/M in, ${output_price}/M out",
            fg="green",
        )

    if json_output:
        out = {
            k: {
                "input_per_million": m.input_per_million,
                "output_per_million": m.output_per_million,
            }
            for k, m in models.items()
        }
        emit_json(out, command="pricing")
        return

    click.echo()
    click.secho("CONFIGURED AI MODEL PRICING (USD / 1M tokens)", bold=True)
    click.echo(f"{'MODEL':<22} {'INPUT ($/M)':<15} {'OUTPUT ($/M)':<15}")
    click.echo("-" * 52)
    for name, m in sorted(models.items()):
        click.echo(f"{name:<22} ${m.input_per_million:<14.2f} ${m.output_per_million:<14.2f}")
    click.echo()


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


register_job_commands(main, _manager_factory, _status_color)
register_requirements_command(main, _manager_factory)
register_handoff_commands(main, _manager_factory)
register_bug_commands(main, _manager_factory)
register_scope_commands(main, _manager_factory)
register_tracking_commands(main, _manager_factory)
register_doctor_command(main, _manager_factory)
register_config_commands(main, _manager_factory)
register_history_commands(main, _manager_factory)
register_archive_commands(main, _manager_factory)
register_mcp_commands(main)
main.add_command(work)


if __name__ == "__main__":
    main()
