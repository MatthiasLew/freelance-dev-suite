"""Tests for interprocess/interthread serialization and monotonic ID generation."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from freelance_cli.config import Config
from packages.bugs.processor import BugProcessor
from packages.scope.detector import ScopeChangeDetector
from packages.storage_utils import storage_lock
from packages.tracking.timer import WorkTimer
from packages.work.storage import next_work_id
from packages.workspace.manager import WorkspaceManager


def test_concurrent_create_job_no_duplicate_ids(tmp_path: Path) -> None:
    """Concurrent threads creating jobs must never produce colliding job IDs."""
    cfg = Config(workspace_root=str(tmp_path))
    manager = WorkspaceManager(config=cfg)

    def worker(idx: int) -> str:
        job = manager.create_job(
            client=f"Client-{idx}",
            description=f"Task description for worker {idx}",
        )
        return job.id

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(12)]
        job_ids = [f.result() for f in futures]

    assert len(job_ids) == 12
    assert len(set(job_ids)) == 12  # All unique!
    assert all(jid.startswith("JOB-") for jid in job_ids)


def test_concurrent_bug_id_generation(tmp_path: Path) -> None:
    """Concurrent threads requesting next_bug_id must produce unique monotonic IDs."""
    job_dir = tmp_path / "active" / "JOB-001"
    job_dir.mkdir(parents=True, exist_ok=True)
    processor = BugProcessor()

    def create_worker(idx: int) -> str:
        with storage_lock(job_dir / "work" / ".bugs.lock"):
            bid = processor.next_bug_id(job_dir)
            bug = processor.parse_raw_report(
                bug_id=bid,
                job_id="JOB-001",
                raw_text=f"Concurrent bug report {idx}",
            )
            processor.save_bug(bug, job_dir)
            return bug.id

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(create_worker, i) for i in range(8)]
        created_ids = [f.result() for f in futures]

    assert len(created_ids) == 8
    assert len(set(created_ids)) == 8


def test_concurrent_scope_change_id_generation(tmp_path: Path) -> None:
    """Concurrent threads requesting scope change creation produce unique IDs."""
    job_dir = tmp_path / "active" / "JOB-001"
    job_dir.mkdir(parents=True, exist_ok=True)
    detector = ScopeChangeDetector()

    def create_change(idx: int) -> str:
        with storage_lock(job_dir / "work" / ".scope.lock"):
            cid = detector.next_change_id(job_dir)
            item = detector.analyze_request(
                job_id="JOB-001",
                change_id=cid,
                requested_text=f"Please add extra feature {idx}",
                requirements_spec=None,
            )
            detector.save_change(item, job_dir)
            return item.id

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(create_change, i) for i in range(8)]
        change_ids = [f.result() for f in futures]

    assert len(change_ids) == 8
    assert len(set(change_ids)) == 8


def test_concurrent_work_id_generation(tmp_path: Path) -> None:
    """Concurrent next_work_id calls must stay sequential."""
    work_dir = tmp_path / "active" / "JOB-001" / "work" / "sessions"
    work_dir.mkdir(parents=True, exist_ok=True)

    def worker(idx: int) -> str:
        with storage_lock(tmp_path / ".locks" / "work.lock"):
            wid = next_work_id(tmp_path)
            # Touch file to simulate session creation
            (work_dir / f"{wid}.json").write_text("{}", encoding="utf-8")
            return wid

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker, i) for i in range(8)]
        work_ids = [f.result() for f in futures]

    assert len(work_ids) == 8
    assert len(set(work_ids)) == 8


def test_concurrent_timer_session_ids(tmp_path: Path) -> None:
    """Concurrent start_timer calls produce unique session IDs."""
    job_dir = tmp_path / "active" / "JOB-001"
    job_dir.mkdir(parents=True, exist_ok=True)
    timer = WorkTimer()

    def timer_worker(idx: int) -> str:
        entry = timer.start_timer(job_dir, "JOB-001", activity=f"Task {idx}")
        timer.stop_timer(job_dir, "JOB-001")
        return entry.id

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(timer_worker, i) for i in range(6)]
        entry_ids = [f.result() for f in futures]

    assert len(entry_ids) == 6
    assert len(set(entry_ids)) == 6
