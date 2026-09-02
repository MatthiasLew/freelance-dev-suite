"""Profitability analysis and effective rate calculation."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ProfitabilityReport, TimeLog


class ProfitabilityCalculator:
    """Calculates profitability, margins, and effective hourly rate for a job."""

    def calculate(self, job_id: str, job_dir: Path) -> ProfitabilityReport:
        """Compute financial performance metrics for a job."""
        client = ""
        job_file = job_dir / "job.json"
        if job_file.exists():
            try:
                with open(job_file, encoding="utf-8") as f:
                    job_data = json.load(f)
                client = str(job_data.get("client", ""))
            except (OSError, json.JSONDecodeError):
                pass

        # 1. Quote / Revenue & Estimated Hours from estimate.json
        quote_price = 0.0
        estimated_hours = 0.0
        estimate_file = job_dir / "analysis" / "estimate.json"
        if estimate_file.exists():
            try:
                with open(estimate_file, encoding="utf-8") as f:
                    est_data = json.load(f)
                quote_price = float(est_data.get("price_pln", 0.0))
                estimated_hours = float(est_data.get("hours", 0.0))
            except (OSError, json.JSONDecodeError):
                pass

        # 2. AI Costs from ai-cost.json
        ai_costs = 0.0
        ai_cost_file = job_dir / "analysis" / "ai-cost.json"
        if ai_cost_file.exists():
            try:
                with open(ai_cost_file, encoding="utf-8") as f:
                    cost_data = json.load(f)
                ai_costs = float(cost_data.get("estimated_cost_pln", 0.0))
            except (OSError, json.JSONDecodeError):
                pass

        # 3. Tracked Time from time-log.json
        time_log_file = job_dir / "work" / "time-log.json"
        tracked_hours = 0.0
        if time_log_file.exists():
            try:
                with open(time_log_file, encoding="utf-8") as f:
                    log_data = json.load(f)
                t_log = TimeLog.from_dict(log_data)
                tracked_hours = t_log.total_duration_hours
            except (OSError, json.JSONDecodeError):
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
            ai_costs_pln=ai_costs,
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
        json_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        md_path = analysis_dir / "profitability-report.md"
        md_path.write_text(report.to_markdown(), encoding="utf-8")

        return {"json": json_path, "report": md_path}
