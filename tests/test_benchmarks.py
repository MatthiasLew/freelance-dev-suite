"""Performance and scaling benchmark tests."""

from __future__ import annotations

import time
from pathlib import Path

from freelance_cli.config import Config
from packages.tracking.timer import WorkTimer
from packages.workspace.manager import WorkspaceManager


def test_scale_benchmark_job_creation_and_listing(tmp_path: Path) -> None:
    """Ensure workspace operations scale efficiently across 50 jobs."""
    cfg = Config(workspace_root=str(tmp_path))
    manager = WorkspaceManager(config=cfg)

    t0 = time.perf_counter()
    for i in range(50):
        manager.create_job(
            client=f"ScaleClient-{i}",
            description=f"High scale performance testing job {i}",
            budget_pln=1000.0 + (i * 10),
        )
    create_duration = time.perf_counter() - t0

    # 50 jobs should be created quickly even under CI virtualization
    assert create_duration < 5.0

    t1 = time.perf_counter()
    jobs = manager.list_jobs(include_finished=False)
    list_duration = time.perf_counter() - t1

    assert len(jobs) == 50
    # Listing 50 jobs should take less than 2.0 seconds across various OS drives
    assert list_duration < 2.0


def test_time_tracking_scale(tmp_path: Path) -> None:
    """Ensure time-log tracking appends and reads efficiently across 100 sessions."""
    job_dir = tmp_path / "active" / "JOB-001"
    job_dir.mkdir(parents=True, exist_ok=True)
    timer = WorkTimer()

    t0 = time.perf_counter()
    for i in range(50):
        timer.start_timer(job_dir, "JOB-001", activity=f"Task {i}")
        timer.stop_timer(job_dir, "JOB-001")
    duration = time.perf_counter() - t0

    # 50 complete start/stop cycles (100 atomic disk flushes) should complete quickly
    assert duration < 5.0

    log = timer.get_time_log(job_dir, "JOB-001")
    assert len(log.entries) == 50
