"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from freelance_cli.config import Config, save_config
from packages.workspace.manager import WorkspaceManager


@pytest.fixture
def cli_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    """CLI runner with an isolated temporary workspace."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    config = Config(workspace_root=str(ws))
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)

    import freelance_cli.cli as cli_module

    def patched_get_manager() -> WorkspaceManager:
        return WorkspaceManager(config_path=config_path)

    monkeypatch.setattr(cli_module, "_get_manager", patched_get_manager)
    return CliRunner()
