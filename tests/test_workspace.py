"""Tests for the workspace module — Job model, storage, and manager."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from freelance_cli.config import Config, save_config, load_config
from freelance_cli.models.job import Job, JobStatus, StatusChange
from packages.workspace.storage import (
    save_job,
    load_job,
    find_all_jobs,
    find_job_by_id,
    find_job_dir,
    job_dir_name,
    _slugify,
)
from packages.workspace.manager import WorkspaceManager


# ──────────────────── Fixtures ──────────────────────────────────────

@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace root."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "active").mkdir()
    (ws / "finished").mkdir()
    return ws


@pytest.fixture
def tmp_config(tmp_path: Path, tmp_workspace: Path) -> tuple[Config, Path]:
    """Create a temporary config pointing to tmp workspace."""
    config = Config(workspace_root=str(tmp_workspace))
    config_path = tmp_path / "config.yaml"
    save_config(config, config_path)
    return config, config_path


@pytest.fixture
def sample_job() -> Job:
    """Create a sample job for testing."""
    return Job(
        id="JOB-001",
        client="TestClient",
        description="Fix API endpoint",
        source="Useme",
        budget_pln=500.0,
        deadline="2026-09-15",
        repository="./client-api",
    )


# ──────────────────── Job model tests ───────────────────────────────

class TestJobModel:
    def test_create_job(self, sample_job: Job) -> None:
        assert sample_job.id == "JOB-001"
        assert sample_job.client == "TestClient"
        assert sample_job.status == "LEAD"

    def test_change_status(self, sample_job: Job) -> None:
        sample_job.change_status("ANALYSIS", "Starting analysis")
        assert sample_job.status == "ANALYSIS"
        assert len(sample_job.status_history) == 1
        assert sample_job.status_history[0]["from_status"] == "LEAD"
        assert sample_job.status_history[0]["to_status"] == "ANALYSIS"
        assert sample_job.status_history[0]["note"] == "Starting analysis"

    def test_multiple_status_changes(self, sample_job: Job) -> None:
        sample_job.change_status("ANALYSIS")
        sample_job.change_status("ACCEPTED")
        sample_job.change_status("IN_PROGRESS")
        assert sample_job.status == "IN_PROGRESS"
        assert len(sample_job.status_history) == 3

    def test_to_dict_roundtrip(self, sample_job: Job) -> None:
        data = sample_job.to_dict()
        restored = Job.from_dict(data)
        assert restored.id == sample_job.id
        assert restored.client == sample_job.client
        assert restored.budget_pln == sample_job.budget_pln

    def test_summary_line(self, sample_job: Job) -> None:
        line = sample_job.summary_line()
        assert "JOB-001" in line
        assert "TestClient" in line
        assert "500 PLN" in line

    def test_detail_view(self, sample_job: Job) -> None:
        detail = sample_job.detail_view()
        assert "JOB-001" in detail
        assert "TestClient" in detail
        assert "Useme" in detail
        assert "500 PLN" in detail

    def test_summary_header(self) -> None:
        header = Job.summary_header()
        assert "ID" in header
        assert "STATUS" in header
        assert "CLIENT" in header


# ──────────────────── Storage tests ─────────────────────────────────

class TestStorage:
    def test_slugify(self) -> None:
        assert _slugify("Hello World") == "hello-world"
        assert _slugify("ABC!@#Special") == "abc-special"
        assert _slugify("") == ""

    def test_job_dir_name(self, sample_job: Job) -> None:
        name = job_dir_name(sample_job)
        assert name.startswith("JOB-001-")
        assert "testclient" in name

    def test_save_and_load(self, sample_job: Job, tmp_workspace: Path) -> None:
        job_dir = save_job(sample_job, tmp_workspace)
        assert job_dir.exists()
        assert (job_dir / "job.json").exists()
        assert (job_dir / "client").is_dir()
        assert (job_dir / "analysis").is_dir()
        assert (job_dir / "work").is_dir()
        assert (job_dir / "handoff").is_dir()

        loaded = load_job(job_dir / "job.json")
        assert loaded.id == sample_job.id
        assert loaded.client == sample_job.client

    def test_find_all_jobs(self, tmp_workspace: Path) -> None:
        job1 = Job(id="JOB-001", client="A", description="Task A")
        job2 = Job(id="JOB-002", client="B", description="Task B")
        save_job(job1, tmp_workspace)
        save_job(job2, tmp_workspace)

        jobs = find_all_jobs(tmp_workspace)
        assert len(jobs) == 2
        ids = {j.id for j in jobs}
        assert "JOB-001" in ids
        assert "JOB-002" in ids

    def test_find_all_jobs_empty(self, tmp_workspace: Path) -> None:
        jobs = find_all_jobs(tmp_workspace)
        assert jobs == []

    def test_find_job_by_id(self, sample_job: Job, tmp_workspace: Path) -> None:
        save_job(sample_job, tmp_workspace)
        found = find_job_by_id("JOB-001", tmp_workspace)
        assert found is not None
        assert found.id == "JOB-001"

    def test_find_job_by_id_not_found(self, tmp_workspace: Path) -> None:
        result = find_job_by_id("JOB-999", tmp_workspace)
        assert result is None

    def test_find_job_dir(self, sample_job: Job, tmp_workspace: Path) -> None:
        saved_dir = save_job(sample_job, tmp_workspace)
        found_dir = find_job_dir("JOB-001", tmp_workspace)
        assert found_dir == saved_dir


# ──────────────────── Manager tests ─────────────────────────────────

class TestWorkspaceManager:
    def test_create_job(
        self, tmp_config: tuple[Config, Path], tmp_workspace: Path
    ) -> None:
        config, config_path = tmp_config
        manager = WorkspaceManager(config=config, config_path=config_path)
        job = manager.create_job(
            client="TestCo",
            description="Build API",
            source="Useme",
            budget_pln=800.0,
            deadline="2026-09-20",
        )
        assert job.id == "JOB-001"
        assert job.client == "TestCo"
        assert job.status == "LEAD"

    def test_create_multiple_jobs(
        self, tmp_config: tuple[Config, Path]
    ) -> None:
        config, config_path = tmp_config
        manager = WorkspaceManager(config=config, config_path=config_path)
        j1 = manager.create_job(client="A", description="Task A")
        j2 = manager.create_job(client="B", description="Task B")
        assert j1.id == "JOB-001"
        assert j2.id == "JOB-002"

    def test_list_jobs(self, tmp_config: tuple[Config, Path]) -> None:
        config, config_path = tmp_config
        manager = WorkspaceManager(config=config, config_path=config_path)
        manager.create_job(client="A", description="Task A")
        manager.create_job(client="B", description="Task B")

        jobs = manager.list_jobs()
        assert len(jobs) == 2

    def test_get_job(self, tmp_config: tuple[Config, Path]) -> None:
        config, config_path = tmp_config
        manager = WorkspaceManager(config=config, config_path=config_path)
        created = manager.create_job(client="Test", description="Thing")

        found = manager.get_job(created.id)
        assert found is not None
        assert found.client == "Test"

    def test_get_nonexistent_job(
        self, tmp_config: tuple[Config, Path]
    ) -> None:
        config, config_path = tmp_config
        manager = WorkspaceManager(config=config, config_path=config_path)
        assert manager.get_job("JOB-999") is None

    def test_update_job_status(
        self, tmp_config: tuple[Config, Path]
    ) -> None:
        config, config_path = tmp_config
        manager = WorkspaceManager(config=config, config_path=config_path)
        manager.create_job(client="Test", description="Thing")

        updated = manager.update_job_status("JOB-001", "ANALYSIS", "Starting")
        assert updated is not None
        assert updated.status == "ANALYSIS"

    def test_counter_persists(self, tmp_config: tuple[Config, Path]) -> None:
        config, config_path = tmp_config
        manager = WorkspaceManager(config=config, config_path=config_path)
        manager.create_job(client="A", description="Task A")

        # Reload config and create new manager
        config2 = load_config(config_path)
        manager2 = WorkspaceManager(config=config2, config_path=config_path)
        j2 = manager2.create_job(client="B", description="Task B")
        assert j2.id == "JOB-002"


# ──────────────────── Config tests ──────────────────────────────────

class TestConfig:
    def test_default_config(self) -> None:
        config = Config()
        assert config.currency == "PLN"
        assert config.pricing.hourly_rate == 70.0
        assert config.pricing.minimum_job_price == 150.0

    def test_save_and_load(self, tmp_path: Path) -> None:
        config = Config(currency="EUR")
        config.pricing.hourly_rate = 100.0
        path = tmp_path / "config.yaml"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.currency == "EUR"
        assert loaded.pricing.hourly_rate == 100.0

    def test_next_job_id(self) -> None:
        config = Config()
        assert config.next_job_id() == "JOB-001"
        assert config.next_job_id() == "JOB-002"
        assert config.next_job_id() == "JOB-003"
        assert config.job_counter == 3

    def test_workspace_paths(self) -> None:
        config = Config(workspace_root="/tmp/test-ws")
        assert config.active_dir == Path("/tmp/test-ws/active")
        assert config.finished_dir == Path("/tmp/test-ws/finished")
