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
