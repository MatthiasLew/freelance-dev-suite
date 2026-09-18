"""Comprehensive, reproducible, and deterministic performance benchmark suite.

Measures operations with time.perf_counter(), statistical summaries
(median, p95, min, max, ops/sec), across configurable scale factors.
Supports baseline recording, post-optimization benchmarking, and comparison.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class MetricResult:
    scenario: str
    scale: int | str
    iterations: int
    median_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    ops_per_sec: float | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_metrics(
    scenario: str,
    scale: int | str,
    timings_sec: list[float],
    batch_size: int = 1,
    extra: dict[str, Any] | None = None,
) -> MetricResult:
    timings_ms = [t * 1000.0 for t in timings_sec]
    timings_sorted = sorted(timings_ms)
    n = len(timings_sorted)
    med = statistics.median(timings_sorted)
    p95_idx = int(round(0.95 * (n - 1)))
    p95 = timings_sorted[p95_idx]
    min_val = timings_sorted[0]
    max_val = timings_sorted[-1]

    ops_per_sec = None
    time_per_op_sec = (med / 1000.0) / batch_size if batch_size > 0 else None
    if time_per_op_sec and time_per_op_sec > 0:
        ops_per_sec = round(1.0 / time_per_op_sec, 2)

    return MetricResult(
        scenario=scenario,
        scale=scale,
        iterations=n,
        median_ms=round(med, 3),
        p95_ms=round(p95, 3),
        min_ms=round(min_val, 3),
        max_ms=round(max_val, 3),
        ops_per_sec=ops_per_sec,
        extra=extra,
    )


def time_repeat(
    fn: Callable[[], Any],
    warmup: int = 1,
    iterations: int = 5,
) -> list[float]:
    for _ in range(warmup):
        fn()
    durations: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        durations.append(t1 - t0)
    return durations


class BenchmarkSuite:
    def __init__(self, quick: bool = False) -> None:
        self.quick = quick
        self.results: list[MetricResult] = []

    def log(self, msg: str) -> None:
        print(f"[BENCH] {msg}", flush=True)

    # -------------------------------------------------------------------------
    # A. Workspace / jobs
    # -------------------------------------------------------------------------
    def bench_workspace_jobs(self) -> None:
        self.log("Running Suite A: Workspace / Jobs...")
        from freelance_cli.config import Config
        from packages.workspace.manager import WorkspaceManager

        scales = [10, 100, 1000] if not self.quick else [10, 50]

        for scale in scales:
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Config(workspace_root=tmp)
                mgr = WorkspaceManager(config=cfg)

                # 1. Create jobs batch
                job_ids: list[str] = []
                create_timings: list[float] = []
                for i in range(scale):
                    t0 = time.perf_counter()
                    j = mgr.create_job(
                        client=f"Client-{i}",
                        description=f"Job description {i}",
                        budget_pln=1000.0 + i,
                    )
                    t1 = time.perf_counter()
                    job_ids.append(j.id)
                    create_timings.append(t1 - t0)

                self.results.append(
                    calculate_metrics(
                        scenario="workspace:create_job",
                        scale=scale,
                        timings_sec=create_timings,
                        batch_size=1,
                    )
                )

                # 2. List jobs (25 iterations for high statistical accuracy)
                list_timings = time_repeat(
                    lambda m=mgr: m.list_jobs(include_finished=False),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="workspace:list_jobs",
                        scale=scale,
                        timings_sec=list_timings,
                        batch_size=1,
                    )
                )

                # 3. Get job by ID: first, mid, last, nonexistent
                first_id = job_ids[0]
                mid_id = job_ids[len(job_ids) // 2]
                last_id = job_ids[-1]
                nonexistent_id = "JOB-999999"

                for target_label, target_id in [
                    ("first", first_id),
                    ("mid", mid_id),
                    ("last", last_id),
                    ("nonexistent", nonexistent_id),
                ]:
                    get_timings = time_repeat(
                        lambda tid=target_id, m=mgr: m.get_job(tid),
                        warmup=2,
                        iterations=30,
                    )
                    self.results.append(
                        calculate_metrics(
                            scenario=f"workspace:get_job_{target_label}",
                            scale=scale,
                            timings_sec=get_timings,
                            batch_size=1,
                        )
                    )

                # 4. Get job dir: mid
                dir_timings = time_repeat(
                    lambda m=mgr, jid=mid_id: m.get_job_dir(jid),
                    warmup=2,
                    iterations=30,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="workspace:get_job_dir",
                        scale=scale,
                        timings_sec=dir_timings,
                        batch_size=1,
                    )
                )

                # 5. Update job status
                update_timings = time_repeat(
                    lambda m=mgr, jid=mid_id: m.update_job_status(
                        jid, "IN_PROGRESS", note="Bench update"
                    ),
                    warmup=1,
                    iterations=10,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="workspace:update_job",
                        scale=scale,
                        timings_sec=update_timings,
                        batch_size=1,
                    )
                )

                # 6. Archive job
                archive_timings = time_repeat(
                    lambda m=mgr, jid=last_id: m.archive_job(jid),
                    warmup=0,
                    iterations=1,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="workspace:archive_job",
                        scale=scale,
                        timings_sec=archive_timings,
                        batch_size=1,
                    )
                )

    # -------------------------------------------------------------------------
    # B. Timeline
    # -------------------------------------------------------------------------
    def bench_timeline(self) -> None:
        self.log("Running Suite B: Timeline...")
        from packages.timeline.manager import TimelineManager

        scales = [10, 100, 1000] if not self.quick else [10, 100]

        for scale in scales:
            with tempfile.TemporaryDirectory() as tmp:
                job_dir = Path(tmp) / "active" / "JOB-001"
                job_dir.mkdir(parents=True, exist_ok=True)
                mgr = TimelineManager()

                # Record scale events, measuring each append
                append_timings: list[float] = []
                for i in range(scale):
                    t0 = time.perf_counter()
                    mgr.record_event(
                        job_dir,
                        "JOB-001",
                        "status_update",
                        metadata={"step": i},
                    )
                    t1 = time.perf_counter()
                    append_timings.append(t1 - t0)

                self.results.append(
                    calculate_metrics(
                        scenario="timeline:record_event",
                        scale=scale,
                        timings_sec=append_timings,
                        batch_size=1,
                    )
                )

                # Measure append on an already-populated history
                tail_append_timings = time_repeat(
                    lambda m=mgr, jd=job_dir: m.record_event(
                        jd, "JOB-001", "tail_event", metadata={"bench": True}
                    ),
                    warmup=1,
                    iterations=10,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="timeline:record_event_tail",
                        scale=scale,
                        timings_sec=tail_append_timings,
                        batch_size=1,
                    )
                )

                # Measure reading full event log
                read_timings = time_repeat(
                    lambda m=mgr, jd=job_dir: m.list_events(jd),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="timeline:list_events",
                        scale=scale,
                        timings_sec=read_timings,
                        batch_size=1,
                    )
                )

    # -------------------------------------------------------------------------
    # C. Timer
    # -------------------------------------------------------------------------
    def bench_timer(self) -> None:
        self.log("Running Suite C: Timer...")
        from packages.tracking.timer import WorkTimer

        scales = [10, 50, 200] if not self.quick else [10, 50]

        for scale in scales:
            with tempfile.TemporaryDirectory() as tmp:
                job_dir = Path(tmp) / "active" / "JOB-001"
                job_dir.mkdir(parents=True, exist_ok=True)
                timer = WorkTimer()

                cycle_timings: list[float] = []
                for i in range(scale):
                    t0 = time.perf_counter()
                    timer.start_timer(job_dir, "JOB-001", activity=f"Task {i}")
                    timer.stop_timer(job_dir, "JOB-001", note=f"Finished {i}")
                    t1 = time.perf_counter()
                    cycle_timings.append(t1 - t0)

                self.results.append(
                    calculate_metrics(
                        scenario="timer:start_stop_cycle",
                        scale=scale,
                        timings_sec=cycle_timings,
                        batch_size=1,
                    )
                )

                # Tail start & stop
                def start_stop_once(t=timer, jd=job_dir) -> None:
                    t.start_timer(jd, "JOB-001", activity="Bench task")
                    t.stop_timer(jd, "JOB-001", note="Bench stop")

                tail_cycle_timings = time_repeat(start_stop_once, warmup=1, iterations=10)
                self.results.append(
                    calculate_metrics(
                        scenario="timer:start_stop_tail",
                        scale=scale,
                        timings_sec=tail_cycle_timings,
                        batch_size=1,
                    )
                )

                # Read full time log
                log_read_timings = time_repeat(
                    lambda t=timer, jd=job_dir: t.get_time_log(jd, "JOB-001"),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="timer:get_time_log",
                        scale=scale,
                        timings_sec=log_read_timings,
                        batch_size=1,
                    )
                )

    # -------------------------------------------------------------------------
    # D. Work Sessions
    # -------------------------------------------------------------------------
    def bench_work_sessions(self) -> None:
        self.log("Running Suite D: Work Sessions...")
        from packages.work.models import WorkSession
        from packages.work.storage import (
            find_work_session,
            list_work_sessions,
            next_work_id,
            save_work_session,
        )

        scales = [10, 50, 150] if not self.quick else [10, 30]

        for scale in scales:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                job_dir = root / "active" / "JOB-001"
                job_dir.mkdir(parents=True, exist_ok=True)

                saved_ids: list[str] = []
                create_timings: list[float] = []
                for i in range(scale):
                    t0 = time.perf_counter()
                    wid = next_work_id(root)
                    session = WorkSession(
                        id=wid,
                        job_id="JOB-001",
                        task=f"Dev step {i}",
                        repository="repo",
                        started_at=datetime.now().astimezone().isoformat(),
                    )
                    save_work_session(session, job_dir)
                    t1 = time.perf_counter()
                    saved_ids.append(wid)
                    create_timings.append(t1 - t0)

                self.results.append(
                    calculate_metrics(
                        scenario="work_session:create",
                        scale=scale,
                        timings_sec=create_timings,
                        batch_size=1,
                    )
                )

                list_timings = time_repeat(
                    lambda jd=job_dir: list_work_sessions(jd),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="work_session:list",
                        scale=scale,
                        timings_sec=list_timings,
                        batch_size=1,
                    )
                )

                target_id = saved_ids[len(saved_ids) // 2]
                find_timings = time_repeat(
                    lambda r=root, tid=target_id: find_work_session(r, tid),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="work_session:find_by_id",
                        scale=scale,
                        timings_sec=find_timings,
                        batch_size=1,
                    )
                )

                next_id_timings = time_repeat(
                    lambda r=root: next_work_id(r),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="work_session:next_id",
                        scale=scale,
                        timings_sec=next_id_timings,
                        batch_size=1,
                    )
                )

    # -------------------------------------------------------------------------
    # E. Bugs and Scope Changes
    # -------------------------------------------------------------------------
    def bench_bugs_and_scope(self) -> None:
        self.log("Running Suite E: Bugs & Scope Changes...")
        from packages.bugs.models import BugReport
        from packages.bugs.processor import BugProcessor
        from packages.scope.detector import ScopeChangeDetector
        from packages.scope.models import ScopeChangeItem

        scales = [10, 50, 100] if not self.quick else [10, 30]

        for scale in scales:
            with tempfile.TemporaryDirectory() as tmp:
                job_dir = Path(tmp) / "active" / "JOB-001"
                job_dir.mkdir(parents=True, exist_ok=True)
                bug_proc = BugProcessor()
                scope_det = ScopeChangeDetector()

                # --- Bugs ---
                bug_ids: list[str] = []
                save_bug_timings: list[float] = []
                for i in range(scale):
                    bid = bug_proc.next_bug_id(job_dir)
                    bug_ids.append(bid)
                    rep = BugReport(
                        id=bid,
                        job_id="JOB-001",
                        title=f"Bug title {i}",
                        raw_description=f"Raw text error {i}",
                    )
                    t0 = time.perf_counter()
                    bug_proc.save_bug(rep, job_dir)
                    t1 = time.perf_counter()
                    save_bug_timings.append(t1 - t0)

                self.results.append(
                    calculate_metrics(
                        scenario="bugs:save_bug",
                        scale=scale,
                        timings_sec=save_bug_timings,
                        batch_size=1,
                    )
                )

                next_bug_timings = time_repeat(
                    lambda bp=bug_proc, jd=job_dir: bp.next_bug_id(jd),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="bugs:next_id",
                        scale=scale,
                        timings_sec=next_bug_timings,
                        batch_size=1,
                    )
                )

                list_bugs_timings = time_repeat(
                    lambda bp=bug_proc, jd=job_dir: bp.list_bugs(jd),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="bugs:list_bugs",
                        scale=scale,
                        timings_sec=list_bugs_timings,
                        batch_size=1,
                    )
                )

                mid_bid = bug_ids[len(bug_ids) // 2]
                load_bug_timings = time_repeat(
                    lambda bp=bug_proc, jd=job_dir, bid=mid_bid: bp.load_bug(jd, bid),
                    warmup=2,
                    iterations=30,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="bugs:load_bug",
                        scale=scale,
                        timings_sec=load_bug_timings,
                        batch_size=1,
                    )
                )

                # --- Scope changes ---
                change_ids: list[str] = []
                save_scope_timings: list[float] = []
                for i in range(scale):
                    cid = scope_det.next_change_id(job_dir)
                    change_ids.append(cid)
                    item = ScopeChangeItem(
                        id=cid,
                        job_id="JOB-001",
                        requested_text=f"Client wants additional feature {i}",
                    )
                    t0 = time.perf_counter()
                    scope_det.save_change(item, job_dir)
                    t1 = time.perf_counter()
                    save_scope_timings.append(t1 - t0)

                self.results.append(
                    calculate_metrics(
                        scenario="scope:save_change",
                        scale=scale,
                        timings_sec=save_scope_timings,
                        batch_size=1,
                    )
                )

                next_change_timings = time_repeat(
                    lambda sd=scope_det, jd=job_dir: sd.next_change_id(jd),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="scope:next_id",
                        scale=scale,
                        timings_sec=next_change_timings,
                        batch_size=1,
                    )
                )

                list_changes_timings = time_repeat(
                    lambda sd=scope_det, jd=job_dir: sd.list_changes(jd),
                    warmup=2,
                    iterations=25,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="scope:list_changes",
                        scale=scale,
                        timings_sec=list_changes_timings,
                        batch_size=1,
                    )
                )

                mid_cid = change_ids[len(change_ids) // 2]
                load_change_timings = time_repeat(
                    lambda sd=scope_det, jd=job_dir, cid=mid_cid: sd.load_change(jd, cid),
                    warmup=2,
                    iterations=30,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="scope:load_change",
                        scale=scale,
                        timings_sec=load_change_timings,
                        batch_size=1,
                    )
                )

    # -------------------------------------------------------------------------
    # F. MCP Latency
    # -------------------------------------------------------------------------
    def bench_mcp(self) -> None:
        self.log("Running Suite F: MCP Latency...")
        from freelance_cli.config import Config
        from packages.mcp.server import FreelanceMcpServer
        from packages.timeline.manager import TimelineManager
        from packages.tracking.timer import WorkTimer
        from packages.work.models import WorkSession
        from packages.work.storage import save_work_session
        from packages.workspace.manager import WorkspaceManager

        workspace_sizes = [10, 100] if not self.quick else [5, 20]

        for size in workspace_sizes:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cfg = Config(workspace_root=str(root))
                mgr = WorkspaceManager(config=cfg)

                for i in range(size):
                    j = mgr.create_job(
                        client=f"Client-{i}",
                        description=f"Description {i}",
                        budget_pln=5000.0,
                    )
                    j_dir = mgr.get_job_dir(j.id)
                    if j_dir and i == 0:
                        TimelineManager().record_event(j_dir, j.id, "job_started")
                        timer = WorkTimer()
                        timer.start_timer(j_dir, j.id, activity="Initial dev")
                        timer.stop_timer(j_dir, j.id, note="Done")
                        save_work_session(
                            WorkSession(
                                id="WORK-0001",
                                job_id=j.id,
                                task="Setup",
                                repository="repo",
                                started_at=datetime.now().astimezone().isoformat(),
                            ),
                            j_dir,
                        )

                server = FreelanceMcpServer(workspace_root=root)

                calls = [
                    (
                        "mcp:initialize",
                        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    ),
                    (
                        "mcp:tools/list",
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    ),
                    (
                        "mcp:list_jobs",
                        {
                            "jsonrpc": "2.0",
                            "id": 3,
                            "method": "tools/call",
                            "params": {"name": "list_jobs", "arguments": {}},
                        },
                    ),
                    (
                        "mcp:get_job_status",
                        {
                            "jsonrpc": "2.0",
                            "id": 4,
                            "method": "tools/call",
                            "params": {
                                "name": "get_job_status",
                                "arguments": {"job_id": "JOB-001"},
                            },
                        },
                    ),
                    (
                        "mcp:get_timeline",
                        {
                            "jsonrpc": "2.0",
                            "id": 5,
                            "method": "tools/call",
                            "params": {
                                "name": "get_timeline",
                                "arguments": {"job_id": "JOB-001"},
                            },
                        },
                    ),
                    (
                        "mcp:get_work_sessions",
                        {
                            "jsonrpc": "2.0",
                            "id": 6,
                            "method": "tools/call",
                            "params": {
                                "name": "get_work_sessions",
                                "arguments": {"job_id": "JOB-001"},
                            },
                        },
                    ),
                    (
                        "mcp:get_profitability",
                        {
                            "jsonrpc": "2.0",
                            "id": 7,
                            "method": "tools/call",
                            "params": {
                                "name": "get_profitability",
                                "arguments": {"job_id": "JOB-001"},
                            },
                        },
                    ),
                ]

                for scenario, msg in calls:
                    timings = time_repeat(
                        lambda s=server, m=msg: s.handle(m),
                        warmup=3,
                        iterations=25,
                    )
                    self.results.append(
                        calculate_metrics(
                            scenario=scenario,
                            scale=f"{size}_jobs",
                            timings_sec=timings,
                            batch_size=1,
                        )
                    )

    # -------------------------------------------------------------------------
    # G. Archive
    # -------------------------------------------------------------------------
    def bench_archive(self) -> None:
        self.log("Running Suite G: Archive...")
        from freelance_cli.models.job import Job
        from packages.archive.manager import ArchiveManager

        datasets = (
            [
                ("small_1MB", 10, 100 * 1024),  # ~1 MB
                ("medium_10MB", 20, 500 * 1024),  # ~10 MB
                ("large_30MB", 30, 1024 * 1024),  # ~30 MB
            ]
            if not self.quick
            else [("small_1MB", 5, 200 * 1024)]
        )

        for label, file_count, file_size in datasets:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                job_dir = root / "active" / "JOB-001-test-job"
                job_dir.mkdir(parents=True, exist_ok=True)
                (job_dir / "work").mkdir(exist_ok=True)

                chunk = b"A" * 1024
                for i in range(file_count):
                    fpath = job_dir / "work" / f"data_{i}.bin"
                    with open(fpath, "wb") as f:
                        for _ in range(file_size // 1024):
                            f.write(chunk)

                job = Job(id="JOB-001", client="TestClient", description="Test job for archive")
                (job_dir / "job.json").write_text(
                    json.dumps(job.to_dict(), indent=2), encoding="utf-8"
                )
                archive_mgr = ArchiveManager()
                archive_path = root / "JOB-001-export.tar.gz"

                # 1. Export
                export_timings = time_repeat(
                    lambda am=archive_mgr, j=job, jd=job_dir, ap=archive_path: am.export_job(
                        j, jd, output_archive=ap
                    ),
                    warmup=1,
                    iterations=5,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="archive:export",
                        scale=label,
                        timings_sec=export_timings,
                        batch_size=1,
                    )
                )

                # 2. Validate
                validate_timings = time_repeat(
                    lambda am=archive_mgr, ap=archive_path: am.validate_archive(ap),
                    warmup=1,
                    iterations=5,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="archive:validate",
                        scale=label,
                        timings_sec=validate_timings,
                        batch_size=1,
                    )
                )

                # 3. Import
                def do_import(am=archive_mgr, ap=archive_path, r=root) -> None:
                    import_root = r / f"import_ws_{time.perf_counter_ns()}"
                    am.import_job(ap, import_root, force=True)

                import_timings = time_repeat(
                    do_import,
                    warmup=1,
                    iterations=5,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="archive:import",
                        scale=label,
                        timings_sec=import_timings,
                        batch_size=1,
                    )
                )

    # -------------------------------------------------------------------------
    # H. Handoff Packaging
    # -------------------------------------------------------------------------
    def bench_handoff(self) -> None:
        self.log("Running Suite H: Handoff Packaging...")
        from freelance_cli.models.job import Job
        from packages.handoff.packager import HandoffPackager

        scales = [100, 500] if not self.quick else [50, 100]

        for file_count in scales:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                project_dir = root / "project"
                project_dir.mkdir(parents=True, exist_ok=True)
                output_dir = root / "handoff_out"

                for i in range(file_count):
                    sub = project_dir / f"module_{i % 10}"
                    sub.mkdir(exist_ok=True)
                    fpath = sub / f"file_{i}.py"
                    fpath.write_text(f"# Python source file {i}\ndef fn_{i}(): return {i}\n")

                job = Job(id="JOB-001", client="Acme", description="Handoff test project")
                packager = HandoffPackager()

                pkg_timings = time_repeat(
                    lambda p=packager, j=job, pd=project_dir, od=output_dir: p.create_package(
                        j,
                        pd,
                        od,
                        create_archive=True,
                    ),
                    warmup=1,
                    iterations=5,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="handoff:create_package_full",
                        scale=f"{file_count}_files",
                        timings_sec=pkg_timings,
                        batch_size=1,
                    )
                )

                zip_dest = root / "release.zip"
                zip_timings = time_repeat(
                    lambda p=packager, pd=project_dir, zd=zip_dest: p._build_release_zip(pd, zd),
                    warmup=1,
                    iterations=5,
                )
                self.results.append(
                    calculate_metrics(
                        scenario="handoff:build_release_zip",
                        scale=f"{file_count}_files",
                        timings_sec=zip_timings,
                        batch_size=1,
                    )
                )

    # -------------------------------------------------------------------------
    # I. CLI Startup & Import Time
    # -------------------------------------------------------------------------
    def bench_cli_startup(self) -> None:
        self.log("Running Suite I: CLI Startup...")
        python_exe = sys.executable

        commands = [
            ("cli:version", ["-m", "freelance_cli", "--version"]),
            ("cli:help", ["-m", "freelance_cli", "--help"]),
            ("cli:doctor", ["-m", "freelance_cli", "doctor"]),
            ("cli:jobs", ["-m", "freelance_cli", "jobs"]),
        ]

        for label, args in commands:
            cmd = [python_exe] + args
            t0 = time.perf_counter()
            subprocess.run(cmd, capture_output=True, text=True)
            cold_sec = time.perf_counter() - t0

            warm_timings: list[float] = [cold_sec]
            for _ in range(5):
                t0 = time.perf_counter()
                subprocess.run(cmd, capture_output=True, text=True)
                t1 = time.perf_counter()
                warm_timings.append(t1 - t0)

            self.results.append(
                calculate_metrics(
                    scenario=label,
                    scale="process_startup",
                    timings_sec=warm_timings,
                    batch_size=1,
                )
            )

        import_cmd = [python_exe, "-X", "importtime", "-m", "freelance_cli", "--version"]
        res = subprocess.run(import_cmd, capture_output=True, text=True)
        lines = res.stderr.splitlines()
        cli_import_us = 0
        for line in lines:
            if "freelance_cli" in line:
                parts = line.split("|")
                if len(parts) >= 2:
                    with contextlib.suppress(ValueError):
                        cli_import_us = int(parts[1].strip())
                        break

        self.results.append(
            MetricResult(
                scenario="cli:importtime_total",
                scale="importtime",
                iterations=1,
                median_ms=round(cli_import_us / 1000.0, 2),
                p95_ms=round(cli_import_us / 1000.0, 2),
                min_ms=round(cli_import_us / 1000.0, 2),
                max_ms=round(cli_import_us / 1000.0, 2),
                ops_per_sec=None,
            )
        )

    def run_all(self) -> list[MetricResult]:
        self.results.clear()
        self.bench_workspace_jobs()
        self.bench_timeline()
        self.bench_timer()
        self.bench_work_sessions()
        self.bench_bugs_and_scope()
        self.bench_mcp()
        self.bench_archive()
        self.bench_handoff()
        self.bench_cli_startup()
        return self.results


def get_system_metadata() -> dict[str, Any]:
    commit_sha = "unknown"
    with contextlib.suppress(Exception):
        commit_sha = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )

    return {
        "timestamp": datetime.now().astimezone().isoformat(),
        "python_version": sys.version.replace("\n", " "),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": platform.processor() or platform.machine(),
        "commit_sha": commit_sha,
    }


def save_report(
    results: list[MetricResult],
    json_path: Path,
    md_path: Path,
    title: str = "Benchmark Results",
) -> None:
    meta = get_system_metadata()
    data = {
        "metadata": meta,
        "results": [r.to_dict() for r in results],
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    header_cols = (
        "| Scenario | Scale | Iterations | Median (ms) | p95 (ms) | Min (ms) | Max (ms) | Ops/sec |"
    )
    separator_cols = "|---|---|---|---|---|---|---|---|"
    md_lines = [
        f"# {title}",
        "",
        f"**Date:** {meta['timestamp']}  ",
        f"**Commit:** `{meta['commit_sha']}`  ",
        f"**Python:** {meta['python_version']}  ",
        f"**OS:** {meta['os']}  ",
        f"**CPU:** {meta['cpu']}  ",
        "",
        header_cols,
        separator_cols,
    ]
    for r in results:
        ops_str = f"{r.ops_per_sec:,.1f}" if r.ops_per_sec is not None else "-"
        row = (
            f"| `{r.scenario}` | {r.scale} | {r.iterations} | "
            f"{r.median_ms:.2f} | {r.p95_ms:.2f} | {r.min_ms:.2f} | "
            f"{r.max_ms:.2f} | {ops_str} |"
        )
        md_lines.append(row)
    md_lines.append("")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(md_lines), encoding="utf-8")


def generate_comparison(
    baseline_json: Path,
    optimized_json: Path,
    comparison_md: Path,
) -> None:
    if not baseline_json.exists() or not optimized_json.exists():
        print("Both baseline.json and optimized.json must exist to generate comparison.")
        return

    base_data = json.loads(baseline_json.read_text(encoding="utf-8"))
    opt_data = json.loads(optimized_json.read_text(encoding="utf-8"))

    base_map = {(r["scenario"], str(r["scale"])): r for r in base_data["results"]}
    opt_map = {(r["scenario"], str(r["scale"])): r for r in opt_data["results"]}

    env_desc = f"{base_data['metadata']['python_version']} on {base_data['metadata']['os']}"
    header_cols = (
        "| Scenario | Scale | Baseline Med (ms) | Optimized Med (ms) | "
        "Diff (%) | Speedup | Base p95 (ms) | Opt p95 (ms) |"
    )
    separator_cols = "|---|---|---|---|---|---|---|---|"

    table_rows = [
        header_cols,
        separator_cols,
    ]

    improvements: list[float] = []
    speedups: list[float] = []

    for key, base_r in base_map.items():
        if key not in opt_map:
            continue
        opt_r = opt_map[key]
        scenario, scale = key

        b_med = base_r["median_ms"]
        o_med = opt_r["median_ms"]
        b_p95 = base_r["p95_ms"]
        o_p95 = opt_r["p95_ms"]

        if b_med > 0:
            diff_pct = ((o_med - b_med) / b_med) * 100.0
            speedup = b_med / o_med if o_med > 0 else float("inf")
        else:
            diff_pct = 0.0
            speedup = 1.0

        improvements.append(diff_pct)
        if speedup != float("inf"):
            speedups.append(speedup)

        sign = "+" if diff_pct > 0 else ""
        diff_str = f"{sign}{diff_pct:.1f}%"
        speedup_str = f"{speedup:.2f}x" if speedup >= 1.0 else f"{speedup:.2f}x (slower)"

        row = (
            f"| `{scenario}` | {scale} | {b_med:.2f} | {o_med:.2f} | "
            f"**{diff_str}** | **{speedup_str}** | {b_p95:.2f} | {o_p95:.2f} |"
        )
        table_rows.append(row)

    med_imp = statistics.median(improvements) if improvements else 0.0
    best_speedup = max(speedups) if speedups else 1.0

    table_section = "\n".join(table_rows)

    # Check if existing COMPARISON.md has narrative sections to preserve
    existing_text = ""
    if comparison_md.exists():
        existing_text = comparison_md.read_text(encoding="utf-8")

    if "## 1. Podsumowanie zmian" in existing_text and "## 3. Profiling" in existing_text:
        # Update Section 2 in-place
        sec2_idx = existing_text.find("## 2. Tabela porównawcza: Baseline vs. Optimized")
        sec3_idx = existing_text.find("## 3. Profiling Breakdown")

        if sec2_idx != -1 and sec3_idx != -1:
            header_and_sec1 = existing_text[:sec2_idx]
            sec3_and_rest = existing_text[sec3_idx:]
            new_sec2 = (
                "## 2. Tabela porównawcza: Baseline vs. Optimized\n\n"
                f"{table_section}\n\n"
                "### Podsumowanie statystyczne:\n"
                f"- **Mediana zmiany opóźnień (wszystkie {len(improvements)} scenariuszy):** "
                f"**{med_imp:+.1f}%**\n"
                f"- **Maksymalne przyspieszenie punktowe:** **{best_speedup:.2f}x**\n\n"
            )
            full_content = header_and_sec1 + new_sec2 + sec3_and_rest
            comparison_md.write_text(full_content, encoding="utf-8")
            print(f"Comparison report updated in {comparison_md}")
            return

    # Fallback to standard full comparison document
    lines = [
        "# Performance Comparison: Baseline vs. Optimized (Pure Python)",
        "",
        f"**Baseline Commit:** `{base_data['metadata']['commit_sha']}`  ",
        f"**Optimized Commit:** `{opt_data['metadata']['commit_sha']}`  ",
        f"**Environment:** {env_desc}  ",
        "",
        table_section,
        "",
        "## Summary Statistics",
        f"- **Median Latency Change:** {med_imp:+.1f}%",
        f"- **Peak Speedup:** {best_speedup:.2f}x",
        "",
    ]
    comparison_md.parent.mkdir(parents=True, exist_ok=True)
    comparison_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Comparison report written to {comparison_md}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Freelance Dev Suite Performance Benchmarks")
    parser.add_argument("--baseline", action="store_true", help="Record baseline benchmark")
    parser.add_argument(
        "--optimized", action="store_true", help="Record post-optimization benchmark"
    )
    parser.add_argument("--compare", action="store_true", help="Generate comparison report")
    parser.add_argument(
        "--quick", action="store_true", help="Run with reduced scales for quick check"
    )
    args = parser.parse_args()

    bench_dir = Path("benchmarks")

    if args.compare:
        generate_comparison(
            bench_dir / "baseline.json",
            bench_dir / "optimized.json",
            bench_dir / "COMPARISON.md",
        )
        return

    suite = BenchmarkSuite(quick=args.quick)
    results = suite.run_all()

    if args.baseline:
        save_report(
            results,
            bench_dir / "baseline.json",
            bench_dir / "BASELINE.md",
            title="Performance Baseline (Pre-Optimization)",
        )
        print("Baseline recorded to benchmarks/baseline.json and benchmarks/BASELINE.md")
    elif args.optimized:
        save_report(
            results,
            bench_dir / "optimized.json",
            bench_dir / "OPTIMIZED.md",
            title="Performance Optimized (Post-Optimization)",
        )
        print(
            "Optimized benchmark recorded to benchmarks/optimized.json and benchmarks/OPTIMIZED.md"
        )
        generate_comparison(
            bench_dir / "baseline.json",
            bench_dir / "optimized.json",
            bench_dir / "COMPARISON.md",
        )
    else:
        for r in results:
            print(r)


if __name__ == "__main__":
    main()
