"""Tests for time tracking and profitability calculation modules."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from packages.tracking import (
    ProfitabilityCalculator,
    ProfitabilityReport,
    TimeEntry,
    TimeLog,
    TimeTracker,
)


class TestTrackingModels:
    """Test TimeEntry, TimeLog, and ProfitabilityReport models."""

    def test_time_entry_and_log_serialization(self) -> None:
        entry = TimeEntry(
            id="SESSION-001",
            job_id="JOB-001",
            activity="development",
            duration_minutes=90.0,
            note="Implemented auth endpoints",
        )
        assert entry.id == "SESSION-001"
        data = entry.to_dict()
        assert data["duration_minutes"] == 90.0

        restored = TimeEntry.from_dict(data)
        assert restored.id == entry.id
        assert restored.duration_minutes == 90.0

        t_log = TimeLog(job_id="JOB-001", entries=[entry])
        assert t_log.total_duration_minutes == 90.0
        assert t_log.total_duration_hours == 1.5

        log_data = t_log.to_dict()
        assert log_data["total_duration_hours"] == 1.5
        restored_log = TimeLog.from_dict(log_data)
        assert len(restored_log.entries) == 1

    def test_profitability_report_serialization(self) -> None:
        report = ProfitabilityReport(
            job_id="JOB-001",
            client="Cyberdyne",
            quote_price_pln=3000.0,
            total_tracked_hours=10.0,
            effective_hourly_rate_pln=295.0,
            estimated_hours=12.0,
            hours_variance_percent=-16.7,
            ai_costs_pln=50.0,
            net_profit_pln=2950.0,
            profit_margin_percent=98.3,
        )

        data = report.to_dict()
        assert data["net_profit_pln"] == 2950.0

        restored = ProfitabilityReport.from_dict(data)
        assert restored.client == "Cyberdyne"
        assert restored.effective_hourly_rate_pln == 295.0

        md = report.to_markdown()
        assert "PROFITABILITY REPORT" in md.upper()
        assert "2950.00 PLN" in md
        assert report.summary()


class TestTimeTrackerAndProfitability:
    """Test TimeTracker recording and ProfitabilityCalculator."""

    def test_timer_lifecycle(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "active" / "JOB-001-timer"
        job_dir.mkdir(parents=True, exist_ok=True)

        tracker = TimeTracker()

        # 1. Start timer
        entry1 = tracker.start_timer(job_dir, "JOB-001", activity="research")
        assert entry1.id == "SESSION-001"
        assert entry1.activity == "research"

        # Calling start again while active returns same entry
        entry1_dup = tracker.start_timer(job_dir, "JOB-001", activity="development")
        assert entry1_dup.id == entry1.id

        # 2. Stop timer
        stopped = tracker.stop_timer(job_dir, "JOB-001", note="Researched API specs")
        assert stopped.id == "SESSION-001"
        assert stopped.end_time is not None

        # Verify stopped in log
        t_log = tracker.get_time_log(job_dir, "JOB-001")
        assert t_log.active_entry is None
        assert len(t_log.entries) == 1

        # Stopping when no active timer raises error
        try:
            tracker.stop_timer(job_dir, "JOB-001")
            raise AssertionError("Expected ValueError when stopping inactive timer")
        except ValueError as exc:
            assert "No active timer" in str(exc)

    def test_profitability_calculation(self, tmp_path: Path) -> None:
        job_dir = tmp_path / "active" / "JOB-001-profit"
        job_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        work_dir = job_dir / "work"
        work_dir.mkdir(parents=True, exist_ok=True)

        # Write mock files
        (job_dir / "job.json").write_text(
            json.dumps({"id": "JOB-001", "client": "Wayne Enterprises"}),
            encoding="utf-8",
        )
        (analysis_dir / "estimate.json").write_text(
            json.dumps({"price_pln": 2000.0, "hours": 10.0}),
            encoding="utf-8",
        )
        (analysis_dir / "ai-cost.json").write_text(
            json.dumps({"estimated_cost_pln": 40.0}),
            encoding="utf-8",
        )
        (work_dir / "time-log.json").write_text(
            json.dumps({
                "job_id": "JOB-001",
                "entries": [
                    {
                        "id": "SESSION-001",
                        "job_id": "JOB-001",
                        "duration_minutes": 300.0,
                    },
                    {
                        "id": "SESSION-002",
                        "job_id": "JOB-001",
                        "duration_minutes": 180.0,
                    },
                ],
            }),
            encoding="utf-8",
        )

        calc = ProfitabilityCalculator()
        report = calc.calculate("JOB-001", job_dir)

        assert report.client == "Wayne Enterprises"
        assert report.quote_price_pln == 2000.0
        assert report.total_tracked_hours == 8.0  # 480 min = 8h
        assert report.ai_costs_pln == 40.0
        assert report.net_profit_pln == 1960.0
        assert report.effective_hourly_rate_pln == 245.0  # 1960 / 8
        assert report.hours_variance_percent == -20.0  # (8 - 10)/10 * 100

        assert (analysis_dir / "profitability.json").exists()
        assert (analysis_dir / "profitability-report.md").exists()


class TestTrackingCLI:
    """Test CLI commands: freelance timer start, stop, status, log, and freelance stats."""

    def test_cli_timer_lifecycle_and_stats(self, cli_runner: CliRunner) -> None:
        # 1. Create job
        cli_runner.invoke(
            main,
            [
                "job",
                "new",
                "--client",
                "Acme Corp",
                "--description",
                "Analytics Portal",
                "--source",
                "Direct",
            ],
        )
        job_id = "JOB-001"

        # 2. Timer status when empty
        status_empty = cli_runner.invoke(main, ["timer", "status", job_id])
        assert status_empty.exit_code == 0
        assert "No active timer" in status_empty.output

        # 3. Start timer
        start_res = cli_runner.invoke(
            main,
            ["timer", "start", job_id, "--activity", "development"],
        )
        assert start_res.exit_code == 0
        assert f"Timer started for {job_id}" in start_res.output

        # 4. Timer status active
        status_act = cli_runner.invoke(main, ["timer", "status"])
        assert status_act.exit_code == 0
        assert f"Timer ACTIVE for {job_id}" in status_act.output

        # 5. Stop timer
        stop_res = cli_runner.invoke(
            main,
            ["timer", "stop", job_id, "--note", "Scaffolded project"],
        )
        assert stop_res.exit_code == 0
        assert f"Timer stopped for {job_id}" in stop_res.output

        # 6. Timer log
        log_res = cli_runner.invoke(main, ["timer", "log", job_id])
        assert log_res.exit_code == 0
        assert "TIME LOG — JOB-001" in log_res.output
        assert "SESSION-001" in log_res.output

        # 7. Timer log JSON
        log_json = cli_runner.invoke(main, ["timer", "log", job_id, "--json"])
        assert log_json.exit_code == 0
        data = json.loads(log_json.output)
        assert data["job_id"] == "JOB-001"

        # 8. Stats / Profitability command
        stats_res = cli_runner.invoke(main, ["stats", job_id])
        assert stats_res.exit_code == 0
        assert "PROFITABILITY SUMMARY — JOB-001" in stats_res.output

        stats_json = cli_runner.invoke(main, ["stats", job_id, "--json"])
        assert stats_json.exit_code == 0
        s_data = json.loads(stats_json.output)
        assert s_data["job_id"] == "JOB-001"
