"""Estimator calibration and heuristic learning from historical jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from packages.workspace.manager import WorkspaceManager


class EstimatorCalibrator:
    """Calibrates baseline estimation multipliers based on tracked job history."""

    def calibrate(self, manager: WorkspaceManager) -> dict[str, Any]:
        """Analyze estimation vs actual hours across active and finished jobs."""
        workspace_path = manager.config.workspace_path
        all_dirs: list[Path] = []

        active_dir = workspace_path / "active"
        if active_dir.exists():
            all_dirs.extend([p for p in active_dir.iterdir() if p.is_dir()])

        finished_dir = workspace_path / "finished"
        if finished_dir.exists():
            all_dirs.extend([p for p in finished_dir.iterdir() if p.is_dir()])

        samples: list[dict[str, Any]] = []
        total_est = 0.0
        total_act = 0.0

        for j_dir in all_dirs:
            est_file = j_dir / "analysis" / "estimate.json"
            time_file = j_dir / "work" / "time-log.json"

            if not est_file.exists() or not time_file.exists():
                continue

            try:
                with open(est_file, encoding="utf-8") as f:
                    est_data = json.load(f)
                with open(time_file, encoding="utf-8") as f:
                    time_data = json.load(f)

                est_h = float(est_data.get("hours", 0.0))
                act_h = float(time_data.get("total_duration_hours", 0.0))

                if est_h > 0 and act_h > 0:
                    samples.append({
                        "job_dir": j_dir.name,
                        "estimated_hours": est_h,
                        "actual_hours": act_h,
                        "ratio": round(act_h / est_h, 2),
                    })
                    total_est += est_h
                    total_act += act_h
            except (OSError, json.JSONDecodeError):
                continue

        if not samples:
            return {
                "jobs_analyzed": 0,
                "calibration_multiplier": 1.0,
                "average_variance_percent": 0.0,
                "total_estimated_hours": 0.0,
                "total_actual_hours": 0.0,
                "recommendation": (
                    "Not enough historical tracked data yet. "
                    "Log work with 'freelance timer'."
                ),
                "samples": [],
            }

        multiplier = round(total_act / total_est, 2)
        variance_pct = round(((total_act - total_est) / total_est) * 100.0, 1)

        if multiplier > 1.2:
            rec = (
                f"Historically jobs take {multiplier}x longer than quoted. "
                "Consider increasing baseline hours."
            )
        elif multiplier < 0.8:
            rec = (
                f"Historically jobs finish {multiplier}x faster than quoted. "
                "Opportunity for competitive pricing."
            )
        else:
            rec = (
                f"Estimations are well-calibrated "
                f"({multiplier}x multiplier, {variance_pct:+.1f}% variance)."
            )

        return {
            "jobs_analyzed": len(samples),
            "calibration_multiplier": multiplier,
            "average_variance_percent": variance_pct,
            "total_estimated_hours": round(total_est, 2),
            "total_actual_hours": round(total_act, 2),
            "recommendation": rec,
            "samples": samples,
        }
