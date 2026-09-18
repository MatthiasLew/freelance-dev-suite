"""Targeted cProfile profiling script to analyze time breakdown on hotspots."""

from __future__ import annotations

import cProfile
import json
import pstats
import tempfile
import time
from io import StringIO
from pathlib import Path

from freelance_cli.config import Config
from freelance_cli.models.job import Job
from packages.archive.manager import ArchiveManager
from packages.handoff.packager import HandoffPackager
from packages.timeline.manager import TimelineManager
from packages.workspace.manager import WorkspaceManager


def profile_scenario(name: str, fn) -> None:
    print("\n========================================================")
    print(f"PROFILING: {name}")
    print("========================================================")
    pr = cProfile.Profile()
    pr.enable()
    t0 = time.perf_counter()
    fn()
    wall_sec = time.perf_counter() - t0
    pr.disable()

    s = StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(30)
    print(f"Wall time: {wall_sec:.3f}s")
    print(s.getvalue())


def run_profiles() -> None:
    # 1. Timeline append hotspot
    def run_timeline() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "active" / "JOB-001"
            job_dir.mkdir(parents=True, exist_ok=True)
            mgr = TimelineManager()
            for i in range(500):
                mgr.record_event(job_dir, "JOB-001", "test_event", metadata={"i": i})

    profile_scenario("Timeline: 500 Appends", run_timeline)

    # 2. Workspace: Job creation and listing (300 jobs)
    def run_workspace() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(workspace_root=tmp)
            mgr = WorkspaceManager(config=cfg)
            for i in range(300):
                mgr.create_job(client=f"Client-{i}", description=f"Desc {i}")
            mgr.list_jobs(include_finished=False)
            mgr.get_job("JOB-150")
            mgr.get_job("JOB-9999")

    profile_scenario("Workspace: 300 Jobs Create & Lookup", run_workspace)

    # 3. Archive: Export & Import (10MB)
    def run_archive() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_dir = root / "active" / "JOB-001"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "work").mkdir(exist_ok=True)
            job = Job(id="JOB-001", client="TestClient", description="Test job")
            (job_dir / "job.json").write_text(json.dumps(job.to_dict(), indent=2))
            chunk = b"X" * 1024
            for i in range(10):
                with open(job_dir / "work" / f"data_{i}.bin", "wb") as f:
                    for _ in range(1024):
                        f.write(chunk)
            archive_mgr = ArchiveManager()
            tar_path = root / "export.tar.gz"
            archive_mgr.export_job(job, job_dir, tar_path)
            archive_mgr.validate_archive(tar_path)
            archive_mgr.import_job(tar_path, root / "imported", force=True)

    profile_scenario("Archive: 10MB Export, Validate & Import", run_archive)

    # 4. Handoff: 200 files
    def run_handoff() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir(parents=True, exist_ok=True)
            for i in range(200):
                sub = project_dir / f"mod_{i % 5}"
                sub.mkdir(exist_ok=True)
                (sub / f"f_{i}.py").write_text(f"def foo_{i}(): pass\n")
            job = Job(id="JOB-001", client="Acme", description="Handoff")
            packager = HandoffPackager()
            packager.create_package(job, project_dir, root / "out", create_archive=True)

    profile_scenario("Handoff: 200 files Packaging", run_handoff)


if __name__ == "__main__":
    run_profiles()
