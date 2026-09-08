"""Requirements specification CLI command."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from packages.workspace.manager import WorkspaceManager


def register_requirements_command(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.command("requirements")
    @click.argument("job_id")
    @click.option(
        "--from-text",
        "from_text",
        type=str,
        default=None,
        help="Generate from raw text description.",
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
        manager = manager_factory()
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
                from_text if from_text is not None else from_file.read_text(encoding="utf-8")  # type: ignore[union-attr]
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
        click.echo("-" * 55)
        click.echo(spec.summary())
        click.echo()
        click.echo(f"  • Requirements spec: {req_md_path}")
        click.echo(f"  • Work checklist:    {checklist_md_path}")
        click.echo(f"  • JSON data:         {json_path}")
        click.echo()
