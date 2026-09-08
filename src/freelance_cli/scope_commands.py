"""Scope-change CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import click

from packages.storage_utils import storage_lock
from packages.workspace.manager import WorkspaceManager


def register_scope_commands(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.group()
    def scope() -> None:
        """Manage scope changes, scope creep detection, and client price proposals."""

    @scope.command("check")
    @click.argument("job_id")
    @click.argument("request_text", required=False, default=None)
    @click.option("--from-text", "flag_text", type=str, default=None, help="New request text.")
    @click.option(
        "--from-file",
        "file_path",
        type=click.Path(exists=True, path_type=Path),
        default=None,
        help="Read request from file.",
    )
    @click.option(
        "--rate",
        "hourly_rate",
        type=float,
        default=150.0,
        help="Developer hourly rate in PLN (default: 150.0).",
    )
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def scope_check(
        job_id: str,
        request_text: str | None,
        flag_text: str | None,
        file_path: Path | None,
        hourly_rate: float,
        json_output: bool,
    ) -> None:
        """Analyze client request against baseline scope and calculate surcharge."""
        import json as _json

        from packages.requirements.models import RequirementsSpec
        from packages.scope.detector import ScopeChangeDetector

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        content = ""
        if request_text:
            content = request_text
        elif flag_text is not None:
            content = flag_text
        elif file_path is not None:
            content = file_path.read_text(encoding="utf-8")
        else:
            content = click.prompt("Paste or enter client request text")

        # Load baseline requirements spec if available
        spec_path = job_dir / "analysis" / "requirements.json"
        req_spec: RequirementsSpec | None = None
        if spec_path.exists():
            try:
                with open(spec_path, encoding="utf-8") as f:
                    req_spec = RequirementsSpec.from_dict(_json.load(f))
            except (OSError, _json.JSONDecodeError):
                pass

        detector = ScopeChangeDetector()
        with storage_lock(job_dir / "work" / "scope" / ".scope.lock"):
            change_id = detector.next_change_id(job_dir)
            change_item = detector.analyze_request(
                job_id=job_id,
                change_id=change_id,
                requested_text=content,
                requirements_spec=req_spec,
                hourly_rate_pln=hourly_rate,
            )
            saved_paths = detector.save_change(change_item, job_dir)

        if json_output:
            out = {
                "scope_change": change_item.to_dict(),
                "files": {k: str(v) for k, v in saved_paths.items()},
            }
            click.echo(_json.dumps(out, indent=2, ensure_ascii=False))
            return

        click.echo()
        if change_item.classification == "IN_SCOPE":
            click.secho(f"✓ SCOPE ANALYSIS — {change_item.id}: IN_SCOPE", fg="green", bold=True)
        elif change_item.classification == "MINOR_EXTENSION":
            click.secho(
                f"ℹ SCOPE ANALYSIS — {change_item.id}: MINOR_EXTENSION", fg="blue", bold=True
            )
        elif change_item.classification == "BREAKING_CHANGE":
            click.secho(
                f"⚠ SCOPE ANALYSIS — {change_item.id}: BREAKING_CHANGE", fg="red", bold=True
            )
        else:
            click.secho(
                f"⚠ SCOPE ANALYSIS — {change_item.id}: OUT_OF_SCOPE", fg="yellow", bold=True
            )

        click.echo("-" * 65)
        click.echo(f"  Classification:     {change_item.classification}")
        click.echo(f"  Additional Hours:   {change_item.estimated_additional_hours:.1f}h")
        click.echo(f"  Estimated AI Cost:  ~{change_item.estimated_ai_cost_pln:.2f} PLN")
        click.secho(
            f"  Suggested Surcharge: {change_item.suggested_extra_price_pln:.0f} PLN netto",
            bold=True,
        )
        click.echo(f"  Proposal document:  {saved_paths['proposal']}")
        click.echo(f"  Technical analysis: {saved_paths['analysis']}")
        click.echo()

    @scope.command("list")
    @click.argument("job_id")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def scope_list(job_id: str, json_output: bool) -> None:
        """List all tracked scope change analyses for a job."""
        import json as _json

        from packages.scope.detector import ScopeChangeDetector

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        detector = ScopeChangeDetector()
        changes = detector.list_changes(job_dir)

        if json_output:
            click.echo(_json.dumps([c.to_dict() for c in changes], indent=2, ensure_ascii=False))
            return

        if not changes:
            click.echo(f"No scope change analyses found for {job_id}.")
            return

        click.echo()
        click.secho(
            f"{'CHANGE ID':<12} {'CLASSIFICATION':<18} {'HOURS':<8} {'SURCHARGE':<12} {'REQUEST'}",
            bold=True,
        )
        click.echo("-" * 80)
        for c in changes:
            req_snippet = c.requested_text[:35] + ("..." if len(c.requested_text) > 35 else "")
            click.echo(
                f"{c.id:<12} {c.classification:<18} {c.estimated_additional_hours:<8.1f} "
                f"{c.suggested_extra_price_pln:<12.0f} {req_snippet}"
            )
        click.echo()

    @scope.command("show")
    @click.argument("job_id")
    @click.argument("change_id")
    @click.option(
        "--proposal", "show_proposal", is_flag=True, help="Display only proposal message."
    )
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def scope_show(job_id: str, change_id: str, show_proposal: bool, json_output: bool) -> None:
        """Show details or client proposal message for a scope change."""
        import json as _json

        from packages.scope.detector import ScopeChangeDetector

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        detector = ScopeChangeDetector()
        change_item = detector.load_change(job_dir, change_id)
        if not change_item:
            msg = f"✗ Scope change {change_id.upper()} not found for {job_id}."
            click.secho(msg, fg="red", err=True)
            sys.exit(1)

        if json_output:
            click.echo(_json.dumps(change_item.to_dict(), indent=2, ensure_ascii=False))
            return

        if show_proposal:
            click.echo(change_item.to_proposal_markdown())
            return

        click.echo(change_item.to_markdown())

    @scope.command("snapshot")
    @click.argument("job_id")
    def scope_snapshot(job_id: str) -> None:
        """Create a baseline snapshot of approved project requirements."""
        import json as _json

        from packages.requirements.models import RequirementsSpec
        from packages.scope.detector import ScopeChangeDetector

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        spec_path = job_dir / "analysis" / "requirements.json"
        if not spec_path.exists():
            click.secho(
                f"✗ No requirements found for {job_id}. "
                f"Run 'freelance requirements {job_id}' first.",
                fg="red",
                err=True,
            )
            sys.exit(1)

        with open(spec_path, encoding="utf-8") as f:
            spec = RequirementsSpec.from_dict(_json.load(f))

        detector = ScopeChangeDetector()
        snap_path = detector.create_snapshot(job_dir, spec)
        click.secho(f"✓ Requirements baseline snapshot created: {snap_path}", fg="green")
