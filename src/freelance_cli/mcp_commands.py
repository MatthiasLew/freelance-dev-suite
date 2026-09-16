"""MCP server CLI command."""

from __future__ import annotations

from pathlib import Path

import click

from packages.mcp.server import run_stdio_server


def register_mcp_commands(main: click.Group) -> None:
    @main.group()
    def mcp() -> None:
        """Local Model Context Protocol (MCP) server for business workflow."""

    @mcp.command("serve")
    @click.option(
        "--workspace",
        "workspace_path",
        type=click.Path(path_type=Path),
        default=None,
        help="Custom workspace root directory.",
    )
    def mcp_serve(workspace_path: Path | None) -> None:
        """Run the local STDIO MCP server for AI coding agents."""
        run_stdio_server(workspace_root=workspace_path)
