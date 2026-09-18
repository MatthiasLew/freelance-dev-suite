"""Tests for business event timeline and freelance history command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.timeline.manager import TimelineManager


def test_timeline_record_and_list_events(tmp_path: Path) -> None:
    job_dir = tmp_path / "active" / "JOB-001"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()

    e1 = timeline.record_event(job_dir, "JOB-001", "job_created", metadata={"source": "Direct"})
    e2 = timeline.record_event(job_dir, "JOB-001", "analysis_performed", metadata={"loc": 1200})
    e3 = timeline.record_event(job_dir, "JOB-001", "scope_changed", related_id="CHANGE-001")

    assert e1.event_id == "EVT-0001"
    assert e2.event_id == "EVT-0002"
    assert e3.event_id == "EVT-0003"

    events = timeline.list_events(job_dir)
    assert len(events) == 3
    assert events[0].event_type == "job_created"
    assert events[1].event_type == "analysis_performed"
    assert events[2].related_id == "CHANGE-001"


def test_history_cli(cli_runner: CliRunner) -> None:
    cli_runner.invoke(
        main,
        [
            "job",
            "new",
            "--client",
            "TimelineClient",
            "--description",
            "History testing",
            "--source",
            "Direct",
        ],
    )

    # Check human-readable history
    res = cli_runner.invoke(main, ["history", "JOB-001"])
    assert res.exit_code == 0
    assert "BUSINESS EVENT TIMELINE — JOB-001" in res.output
    assert "job_created" in res.output

    # Check JSON history
    res_json = cli_runner.invoke(main, ["history", "JOB-001", "--json"])
    assert res_json.exit_code == 0
    payload = json.loads(res_json.output)
    assert payload["command"] == "history"
    data = payload["data"]
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["event_type"] == "job_created"


def test_history_not_found(cli_runner: CliRunner) -> None:
    res = cli_runner.invoke(main, ["history", "JOB-999"])
    assert res.exit_code != 0
    assert "not found" in res.output.lower()


def test_timeline_sequential_and_fallback(tmp_path: Path) -> None:
    job_dir = tmp_path / "active" / "JOB-002"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()

    # Append 25 events and verify IDs are strictly sequential
    for i in range(1, 26):
        evt = timeline.record_event(job_dir, "JOB-002", f"evt_{i}")
        assert evt.event_id == f"EVT-{i:04d}"

    # Verify fallback if trailing line is malformed
    hfile = timeline.history_file(job_dir)
    with open(hfile, "a", encoding="utf-8") as f:
        f.write("corrupted-non-json-line\n")

    next_evt = timeline.record_event(job_dir, "JOB-002", "after_corrupted")
    assert next_evt.event_id == "EVT-0026"


def test_timeline_empty_file(tmp_path: Path) -> None:
    """Empty events.jsonl file correctly assigns EVT-0001."""
    job_dir = tmp_path / "active" / "JOB-EMPTY"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()
    hfile = timeline.history_file(job_dir)
    hfile.parent.mkdir(parents=True, exist_ok=True)
    hfile.touch()

    evt = timeline.record_event(job_dir, "JOB-EMPTY", "first_event")
    assert evt.event_id == "EVT-0001"


def test_timeline_missing_trailing_newline(tmp_path: Path) -> None:
    """Appending when file lacks trailing newline does not clobber previous event."""
    job_dir = tmp_path / "active" / "JOB-NONL"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()
    hfile = timeline.history_file(job_dir)
    hfile.parent.mkdir(parents=True, exist_ok=True)

    # Write a valid event without a trailing newline
    raw_event = json.dumps({"event_id": "EVT-0001", "event_type": "legacy", "job_id": "JOB-NONL"})
    hfile.write_text(raw_event, encoding="utf-8")

    # Record next event: must prepend newline and create EVT-0002
    evt2 = timeline.record_event(job_dir, "JOB-NONL", "second_event")
    assert evt2.event_id == "EVT-0002"

    # Both events must be cleanly parseable
    raw_lines = hfile.read_text(encoding="utf-8").splitlines()
    lines = [line.strip() for line in raw_lines if line.strip()]
    assert len(lines) == 2
    parsed0 = json.loads(lines[0])
    parsed1 = json.loads(lines[1])
    assert parsed0["event_id"] == "EVT-0001"
    assert parsed1["event_id"] == "EVT-0002"


def test_timeline_multiple_corrupted_lines_at_end(tmp_path: Path) -> None:
    """Multiple corrupted lines at end never cause ID collision."""
    job_dir = tmp_path / "active" / "JOB-CORRUPT"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()
    hfile = timeline.history_file(job_dir)
    hfile.parent.mkdir(parents=True, exist_ok=True)

    timeline.record_event(job_dir, "JOB-CORRUPT", "evt_1")
    timeline.record_event(job_dir, "JOB-CORRUPT", "evt_2")

    # Corrupt with multiple partial/broken lines
    with open(hfile, "a", encoding="utf-8") as f:
        f.write("{broken json line\n")
        f.write("another partial line without close\n")
        f.write("!!!\n")

    next_evt = timeline.record_event(job_dir, "JOB-CORRUPT", "recovered_evt")
    # Next ID must be > 2 (and account for lines: 2 valid + 3 corrupted = 5 -> EVT-0006)
    evt_num = int(next_evt.event_id.replace("EVT-", ""))
    assert evt_num >= 3
    assert next_evt.event_id not in {"EVT-0001", "EVT-0002"}


def test_timeline_large_event_json(tmp_path: Path) -> None:
    """Events with payloads larger than 8KB are correctly parsed by fallback."""
    job_dir = tmp_path / "active" / "JOB-LARGE"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()

    large_payload = "x" * 16384  # 16 KB payload
    e1 = timeline.record_event(
        job_dir, "JOB-LARGE", "large_event", metadata={"blob": large_payload}
    )
    assert e1.event_id == "EVT-0001"

    e2 = timeline.record_event(job_dir, "JOB-LARGE", "subsequent_event")
    assert e2.event_id == "EVT-0002"


def test_timeline_gaps_in_event_ids(tmp_path: Path) -> None:
    """Gaps in historical event IDs still produce monotonic next ID."""
    job_dir = tmp_path / "active" / "JOB-GAP"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()
    hfile = timeline.history_file(job_dir)
    hfile.parent.mkdir(parents=True, exist_ok=True)

    e1 = {"event_id": "EVT-0005", "event_type": "t1", "job_id": "JOB-GAP"}
    e2 = {"event_id": "EVT-0100", "event_type": "t2", "job_id": "JOB-GAP"}
    hfile.write_text(json.dumps(e1) + "\n" + json.dumps(e2) + "\n", encoding="utf-8")

    next_evt = timeline.record_event(job_dir, "JOB-GAP", "t3")
    assert next_evt.event_id == "EVT-0101"


def test_timeline_concurrent_appends(tmp_path: Path) -> None:
    """Concurrent appends under storage_lock assign distinct IDs."""
    import gc
    from concurrent.futures import ThreadPoolExecutor

    job_dir = tmp_path / "active" / "JOB-CONCURRENT"
    job_dir.mkdir(parents=True, exist_ok=True)
    timeline = TimelineManager()

    def append_event(i: int) -> str:
        evt = timeline.record_event(job_dir, "JOB-CONCURRENT", f"concurrent_{i}")
        return evt.event_id

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(append_event, range(12)))

    assert len(ids) == 12
    assert len(set(ids)) == 12
    gc.collect()
