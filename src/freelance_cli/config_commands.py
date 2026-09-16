"""Configuration inspection and validation commands."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from freelance_cli.output import emit_json
from packages.workspace.manager import WorkspaceManager


def validate_config(manager: WorkspaceManager) -> tuple[bool, list[str]]:
    """Validate current configuration integrity and consistency."""
    errors: list[str] = []
    cfg = manager.config

    if cfg.pricing.hourly_rate <= 0:
        errors.append(f"Hourly rate must be positive, got {cfg.pricing.hourly_rate}")
    if cfg.pricing.minimum_job_price <= 0:
        errors.append(f"Minimum job price must be positive, got {cfg.pricing.minimum_job_price}")
    if cfg.usd_to_pln_rate <= 0:
        errors.append(f"USD to PLN rate must be positive, got {cfg.usd_to_pln_rate}")

    if not cfg.workspace_root:
        errors.append("Workspace root path cannot be empty")

    if cfg.model_pricing_path and not Path(cfg.model_pricing_path).exists():
        errors.append(f"Custom model pricing file does not exist: {cfg.model_pricing_path}")

    return len(errors) == 0, errors


def register_config_commands(
    main: click.Group, manager_factory: Callable[[], WorkspaceManager]
) -> None:
    @main.group()
    def config() -> None:
        """Inspect and validate suite configuration."""

    @config.command("show")
    @click.option("--json", "json_output", is_flag=True, help="Output structured JSON.")
    def config_show(json_output: bool) -> None:
        """Display effective configuration with masked secrets."""
        manager = manager_factory()
        cfg_dict: dict[str, Any] = manager.config.to_dict()

        if json_output:
            emit_json(data=cfg_dict, command="config show")
            return

        click.echo()
        click.secho("EFFECTIVE FREELANCE CONFIGURATION", bold=True, fg="cyan")
        click.echo("-" * 55)
        click.echo(f"  Workspace Root:     {manager.config.workspace_root}")
        click.echo(f"  Currency:           {manager.config.currency}")
        hr = f"{manager.config.pricing.hourly_rate:.2f} {manager.config.currency}"
        min_p = f"{manager.config.pricing.minimum_job_price:.2f} {manager.config.currency}"
        click.echo(f"  Hourly Rate:        {hr}")
        click.echo(f"  Minimum Job Price:  {min_p}")
        click.echo(f"  Default Model:      {manager.config.default_model}")
        click.echo(f"  USD to PLN Rate:    {manager.config.usd_to_pln_rate:.2f}")
        click.echo(f"  Current Job Counter:{manager.config.job_counter}")
        click.echo("-" * 55)
        click.echo()

    @config.command("validate")
    @click.option(
        "--json", "json_output", is_flag=True, help="Output structured JSON validation report."
    )
    def config_validate(json_output: bool) -> None:
        """Check configuration values for consistency and errors."""
        manager = manager_factory()
        is_valid, errors = validate_config(manager)

        data = {
            "valid": is_valid,
            "errors": errors,
            "config_path": str(manager.config_path or "default"),
        }

        if json_output:
            status = "success" if is_valid else "error"
            emit_json(
                data=data,
                command="config validate",
                status=status,
                exit_code=0 if is_valid else 1,
                errors=errors,
            )
            if not is_valid:
                sys.exit(1)
            return

        click.echo()
        if is_valid:
            click.secho("✓ Configuration is valid and consistent.", fg="green", bold=True)
        else:
            click.secho("✗ Configuration validation failed:", fg="red", bold=True)
            for err in errors:
                click.echo(f"  • {err}")
            sys.exit(1)
        click.echo()
