"""Tests for estimator learning and historical calibration."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from freelance_cli.cli import main
from freelance_cli.config import Config
from packages.estimator.calibration import EstimatorCalibrator
from packages.workspace.manager import WorkspaceManager


class TestEstimatorCalibration:
    """Test EstimatorCalibrator heuristics and CLI."""

    def test_calibrator_empty_history(self, tmp_path: Path) -> None:
        cfg = Config(workspace_root=str(tmp_path))
        mgr = WorkspaceManager(config=cfg)

        calibrator = EstimatorCalibrator()
        res = calibrator.calibrate(mgr)
        assert res["jobs_analyzed"] == 0
        assert res["calibration_multiplier"] == 1.0
        assert "Not enough" in res["recommendation"]

    def test_calibrator_with_historical_jobs(self, tmp_path: Path) -> None:
        cfg = Config(workspace_root=str(tmp_path))
        mgr = WorkspaceManager(config=cfg)

        # Create 2 mock completed jobs in active and finished
        job1_dir = tmp_path / "active" / "JOB-001-mock"
        job1_dir.mkdir(parents=True, exist_ok=True)
        (job1_dir / "analysis").mkdir()
        (job1_dir / "work").mkdir()
        (job1_dir / "analysis" / "estimate.json").write_text(
            json.dumps({"hours": 10.0}), encoding="utf-8"
        )
        (job1_dir / "work" / "time-log.json").write_text(
            json.dumps({"total_duration_hours": 12.0}), encoding="utf-8"
        )

        job2_dir = tmp_path / "finished" / "JOB-002-mock"
        job2_dir.mkdir(parents=True, exist_ok=True)
        (job2_dir / "analysis").mkdir()
        (job2_dir / "work").mkdir()
        (job2_dir / "analysis" / "estimate.json").write_text(
            json.dumps({"hours": 20.0}), encoding="utf-8"
        )
        (job2_dir / "work" / "time-log.json").write_text(
            json.dumps({"total_duration_hours": 24.0}), encoding="utf-8"
        )

        calibrator = EstimatorCalibrator()
        res = calibrator.calibrate(mgr)

        assert res["jobs_analyzed"] == 2
        assert res["total_estimated_hours"] == 30.0
        assert res["total_actual_hours"] == 36.0
        assert res["calibration_multiplier"] == 1.2
        assert res["average_variance_percent"] == 20.0

    def test_calibration_cli(self, cli_runner: CliRunner) -> None:
        res = cli_runner.invoke(main, ["calibrate"])
        assert res.exit_code == 0
        assert "ESTIMATOR CALIBRATION & HISTORICAL ACCURACY" in res.output

        res_json = cli_runner.invoke(main, ["calibrate", "--json"])
        assert res_json.exit_code == 0
        data = json.loads(res_json.output)
        assert "jobs_analyzed" in data
