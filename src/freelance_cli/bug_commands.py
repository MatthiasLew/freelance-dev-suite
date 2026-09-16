"""Client bug-report CLI commands."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import click

from packages.storage_utils import storage_lock
from packages.workspace.manager import WorkspaceManager


def register_bug_commands(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.group()
    def bug() -> None:
        """Manage client bug reports, clarifying questions, and reproduction."""

    @bug.command("add")
    @click.argument("job_id")
    @click.option("--title", type=str, default="", help="Short bug title.")
    @click.option("--from-text", "raw_text", type=str, default=None, help="Raw bug report text.")
    @click.option(
        "--from-file",
        "file_path",
        type=click.Path(exists=True, path_type=Path),
        default=None,
        help="Read report text from file.",
    )
    @click.option(
        "--severity",
        type=click.Choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"], case_sensitive=False),
        default="MEDIUM",
        help="Bug severity level.",
    )
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def bug_add(
        job_id: str,
        title: str,
        raw_text: str | None,
        file_path: Path | None,
        severity: str,
        json_output: bool,
    ) -> None:
        """Add and parse a new bug report for a job."""
        import json as _json

        from packages.bugs.processor import BugProcessor

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        if raw_text is not None:
            content = raw_text
        elif file_path is not None:
            content = file_path.read_text(encoding="utf-8")
        else:
            content = click.prompt("Paste or enter bug description")

        processor = BugProcessor()
        with storage_lock(job_dir / "work" / ".bugs.lock"):
            bug_id = processor.next_bug_id(job_dir)
            bug_report = processor.parse_raw_report(
                raw_text=content,
                job_id=job_id,
                bug_id=bug_id,
                title=title,
                severity=severity.upper(),
            )
            saved_paths = processor.save_bug(bug_report, job_dir)

        if json_output:
            out = {
                "bug": bug_report.to_dict(),
                "files": {k: str(v) for k, v in saved_paths.items()},
            }
            click.echo(_json.dumps(out, indent=2, ensure_ascii=False))
            return

        click.echo()
        click.secho(f"✓ Added bug report: {bug_report.id}", fg="green", bold=True)
        click.echo("-" * 55)
        click.echo(f"  Title:     {bug_report.title}")
        click.echo(f"  Status:    {bug_report.status}")
        click.echo(f"  Severity:  {bug_report.severity}")
        click.echo(f"  Summary:   {saved_paths['summary']}")
        click.echo(f"  Repro:     {saved_paths['repro']}")
        if "questions" in saved_paths:
            click.secho(f"  Questions: {saved_paths['questions']}", fg="yellow")
            click.echo()
            click.secho("Clarifying Questions for Client:", bold=True)
            for q in bug_report.questions_for_client:
                click.echo(f"  • {q}")
        click.echo()

    @bug.command("list")
    @click.argument("job_id")
    @click.option("--status", "status_filter", type=str, default=None, help="Filter by status.")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def bug_list(job_id: str, status_filter: str | None, json_output: bool) -> None:
        """List all bug reports for a job."""
        import json as _json

        from packages.bugs.processor import BugProcessor

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        processor = BugProcessor()
        bugs = processor.list_bugs(job_dir)
        if status_filter:
            clean_f = status_filter.strip().upper()
            bugs = [b for b in bugs if b.status == clean_f]

        if json_output:
            click.echo(_json.dumps([b.to_dict() for b in bugs], indent=2, ensure_ascii=False))
            return

        if not bugs:
            click.echo(f"No bug reports found for {job_id}.")
            return

        click.echo()
        click.secho(f"{'BUG ID':<10} {'STATUS':<18} {'SEVERITY':<10} {'TITLE'}", bold=True)
        click.echo("-" * 75)
        for b in bugs:
            color = (
                "red" if b.status == "NEEDS_INFO" else ("green" if b.status == "FIXED" else "white")
            )
            click.secho(f"{b.id:<10} {b.status:<18} {b.severity:<10} {b.title}", fg=color)
        click.echo()

    @bug.command("show")
    @click.argument("job_id")
    @click.argument("bug_id")
    @click.option(
        "--questions",
        "show_questions",
        is_flag=True,
        help="Display only questions for client.",
    )
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def bug_show(job_id: str, bug_id: str, show_questions: bool, json_output: bool) -> None:
        """Show details or client questions for a bug report."""
        import json as _json

        from packages.bugs.processor import BugProcessor

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        processor = BugProcessor()
        bug_report = processor.load_bug(job_dir, bug_id)
        if not bug_report:
            click.secho(f"✗ Bug {bug_id.upper()} not found for {job_id}.", fg="red", err=True)
            sys.exit(1)

        if json_output:
            click.echo(_json.dumps(bug_report.to_dict(), indent=2, ensure_ascii=False))
            return

        if show_questions:
            click.echo(bug_report.to_questions_markdown())
            return

        click.echo(bug_report.to_markdown())

    @bug.command("status")
    @click.argument("job_id")
    @click.argument("bug_id")
    @click.argument("new_status")
    @click.option("--note", type=str, default="", help="Status update note.")
    def bug_status(job_id: str, bug_id: str, new_status: str, note: str) -> None:
        """Update lifecycle status of a bug report."""
        from packages.bugs.processor import BugProcessor

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        processor = BugProcessor()
        bug_report = processor.load_bug(job_dir, bug_id)
        if not bug_report:
            click.secho(f"✗ Bug {bug_id.upper()} not found for {job_id}.", fg="red", err=True)
            sys.exit(1)

        try:
            bug_report.change_status(new_status, note)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        processor.save_bug(bug_report, job_dir)
        click.secho(f"✓ Updated {bug_report.id} status to {bug_report.status}", fg="green")

    @bug.command("repro")
    @click.argument("job_id")
    @click.argument("bug_id")
    def bug_repro(job_id: str, bug_id: str) -> None:
        """View reproduction script for a bug report."""
        from packages.bugs.processor import BugProcessor

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        processor = BugProcessor()
        bug_report = processor.load_bug(job_dir, bug_id)
        if not bug_report:
            click.secho(f"✗ Bug {bug_id.upper()} not found for {job_id}.", fg="red", err=True)
            sys.exit(1)

        repro_file = job_dir / "work" / "bugs" / f"{bug_report.id}-repro.py"
        if repro_file.exists():
            click.echo(repro_file.read_text(encoding="utf-8"))
        else:
            click.echo(bug_report.to_repro_script())

    @bug.command("test")
    @click.argument("job_id")
    @click.argument("bug_id")
    @click.option(
        "--file",
        "test_file",
        type=str,
        default=None,
        help="Linked regression test file path.",
    )
    def bug_test(job_id: str, bug_id: str, test_file: str | None) -> None:
        """Link a regression test and mark bug as REGRESSION_TESTED."""
        from packages.bugs.processor import BugProcessor

        job_id = job_id.upper()
        manager = manager_factory()
        job_dir = manager.get_job_dir(job_id)
        if not job_dir:
            click.secho(f"✗ Job {job_id} not found.", fg="red", err=True)
            sys.exit(1)

        processor = BugProcessor()
        bug_report = processor.load_bug(job_dir, bug_id)
        if not bug_report:
            click.secho(f"✗ Bug {bug_id.upper()} not found for {job_id}.", fg="red", err=True)
            sys.exit(1)

        if test_file:
            bug_report.regression_test_file = test_file
        bug_report.change_status("REGRESSION_TESTED")
        processor.save_bug(bug_report, job_dir)

        msg = f"✓ Linked regression test for {bug_report.id} (status: REGRESSION_TESTED)"
        click.secho(msg, fg="green")
        if bug_report.regression_test_file:
            click.echo(f"  Test file: {bug_report.regression_test_file}")
