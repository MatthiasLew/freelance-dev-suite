"""Profitability analysis and effective rate calculation."""

from __future__ import annotations

from pathlib import Path

from packages.storage_utils import (
    StateError,
    atomic_write_json,
    atomic_write_text,
    safe_read_json,
)

from .models import ProfitabilityReport, TimeLog


class ProfitabilityCalculator:
    """Calculates profitability, margins, and effective hourly rate for a job."""

    def calculate(self, job_id: str, job_dir: Path) -> ProfitabilityReport:
        """Compute financial performance metrics for a job."""
        client = ""
        job_file = job_dir / "job.json"
        if job_file.exists():
            try:
                job_data = safe_read_json(job_file)
                client = str(job_data.get("client", ""))
            except (OSError, StateError, ValueError):
                pass

        # 1. Quote / Revenue & Estimated Hours from estimate.json
        quote_price = 0.0
        estimated_hours = 0.0
        estimate_file = job_dir / "analysis" / "estimate.json"
        if estimate_file.exists():
            try:
                est_data = safe_read_json(estimate_file)
                quote_price = float(est_data.get("price_pln", 0.0))
                estimated_hours = float(est_data.get("hours", 0.0))
            except (OSError, StateError, ValueError):
                pass

        # 2. Prefer measured work-session costs. Fall back to the intake estimate
        # only for jobs that do not have work-session telemetry yet.
        session_files = list((job_dir / "work" / "sessions").glob("WORK-*.json"))
        ai_costs = 0.0
        if session_files:
            for session_file in session_files:
                try:
                    session_data = safe_read_json(session_file)
                    ai_costs += float(session_data.get("ai_cost_pln", 0.0))
                except (OSError, StateError, ValueError, TypeError):
                    continue
        else:
            ai_cost_file = job_dir / "analysis" / "ai-cost.json"
            try:
                if ai_cost_file.exists():
                    cost_data = safe_read_json(ai_cost_file)
                    ai_costs = float(cost_data.get("estimated_cost_pln", 0.0))
            except (OSError, StateError, ValueError, TypeError):
                ai_costs = 0.0

        # 3. Tracked Time from time-log.json
        time_log_file = job_dir / "work" / "time-log.json"
        tracked_hours = 0.0
        if time_log_file.exists():
            try:
                log_data = safe_read_json(time_log_file)
                t_log = TimeLog.from_dict(log_data)
                tracked_hours = t_log.total_duration_hours
            except (OSError, StateError, ValueError):
                pass

        # 4. Metrics calculation
        net_profit = quote_price - ai_costs
        profit_margin = (net_profit / quote_price * 100.0) if quote_price > 0 else 0.0
        effective_rate = (net_profit / tracked_hours) if tracked_hours > 0 else 0.0
        variance = (
            ((tracked_hours - estimated_hours) / estimated_hours * 100.0)
            if estimated_hours > 0
            else 0.0
        )

        report = ProfitabilityReport(
            job_id=job_id,
            client=client,
            quote_price_pln=quote_price,
            total_tracked_hours=tracked_hours,
            effective_hourly_rate_pln=round(effective_rate, 2),
            estimated_hours=estimated_hours,
            hours_variance_percent=round(variance, 1),
            ai_costs_pln=round(ai_costs, 2),
            net_profit_pln=round(net_profit, 2),
            profit_margin_percent=round(profit_margin, 1),
        )

        # 5. Persist artifacts
        self.save_report(report, job_dir)
        return report

    def save_report(self, report: ProfitabilityReport, job_dir: Path) -> dict[str, Path]:
        """Save report JSON and Markdown in analysis directory."""
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        json_path = analysis_dir / "profitability.json"
        atomic_write_json(json_path, report.to_dict())

        md_path = analysis_dir / "profitability-report.md"
        atomic_write_text(md_path, report.to_markdown())

        return {"json": json_path, "report": md_path}
