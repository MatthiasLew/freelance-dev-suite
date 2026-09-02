"""Data models for time tracking and profitability calculations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TimeEntry:
    """Individual work session entry."""

    id: str
    job_id: str
    activity: str = "development"
    start_time: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )
    end_time: str | None = None
    duration_minutes: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimeEntry:
        return cls(
            id=str(data["id"]),
            job_id=str(data["job_id"]),
            activity=str(data.get("activity", "development")),
            start_time=str(data.get("start_time", "")),
            end_time=data.get("end_time"),
            duration_minutes=float(data.get("duration_minutes", 0.0)),
            note=str(data.get("note", "")),
        )


@dataclass
class TimeLog:
    """Time log container for a job."""

    job_id: str
    entries: list[TimeEntry] = field(default_factory=list)
    active_entry: TimeEntry | None = None

    @property
    def total_duration_minutes(self) -> float:
        return sum(e.duration_minutes for e in self.entries)

    @property
    def total_duration_hours(self) -> float:
        return round(self.total_duration_minutes / 60.0, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "total_duration_minutes": self.total_duration_minutes,
            "total_duration_hours": self.total_duration_hours,
            "active_entry": self.active_entry.to_dict() if self.active_entry else None,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimeLog:
        active = None
        if data.get("active_entry"):
            active = TimeEntry.from_dict(data["active_entry"])
        entries = [TimeEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            job_id=str(data["job_id"]),
            entries=entries,
            active_entry=active,
        )


@dataclass
class ProfitabilityReport:
    """Financial & effort metrics analysis for a job."""

    job_id: str
    client: str
    quote_price_pln: float
    total_tracked_hours: float
    effective_hourly_rate_pln: float
    estimated_hours: float
    hours_variance_percent: float
    ai_costs_pln: float
    net_profit_pln: float
    profit_margin_percent: float
    created_at: str = field(
        default_factory=lambda: datetime.now().astimezone().isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfitabilityReport:
        return cls(
            job_id=str(data["job_id"]),
            client=str(data.get("client", "")),
            quote_price_pln=float(data.get("quote_price_pln", 0.0)),
            total_tracked_hours=float(data.get("total_tracked_hours", 0.0)),
            effective_hourly_rate_pln=float(data.get("effective_hourly_rate_pln", 0.0)),
            estimated_hours=float(data.get("estimated_hours", 0.0)),
            hours_variance_percent=float(data.get("hours_variance_percent", 0.0)),
            ai_costs_pln=float(data.get("ai_costs_pln", 0.0)),
            net_profit_pln=float(data.get("net_profit_pln", 0.0)),
            profit_margin_percent=float(data.get("profit_margin_percent", 0.0)),
            created_at=str(data.get("created_at", datetime.now().astimezone().isoformat())),
        )

    def to_markdown(self) -> str:
        """Render markdown profitability report."""
        lines = [
            f"# Profitability Report: {self.job_id}",
            "",
            f"**Client:** {self.client}  ",
            f"**Report Date:** {self.created_at}  ",
            "",
            "## Summary Metrics",
            f"- **Quote Price:** {self.quote_price_pln:.2f} PLN",
            f"- **AI & Tooling Costs:** {self.ai_costs_pln:.2f} PLN",
            f"- **Net Profit:** {self.net_profit_pln:.2f} PLN",
            f"- **Profit Margin:** {self.profit_margin_percent:.1f}%",
            "",
            "## Time & Rates",
            f"- **Tracked Hours:** {self.total_tracked_hours:.2f}h",
            f"- **Estimated Hours:** {self.estimated_hours:.2f}h",
            f"- **Hours Variance:** {self.hours_variance_percent:+.1f}%",
            f"- **Effective Hourly Rate:** {self.effective_hourly_rate_pln:.2f} PLN/h",
            "",
        ]
        return "\n".join(lines)

    def summary(self) -> str:
        lines = [
            f"PROFITABILITY SUMMARY — {self.job_id} ({self.client})",
            f"  Revenue (Quote):        {self.quote_price_pln:.0f} PLN",
            f"  AI & Expenses:          {self.ai_costs_pln:.2f} PLN",
            (
                f"  Net Profit:             {self.net_profit_pln:.0f} PLN "
                f"({self.profit_margin_percent:.1f}%)"
            ),
            (
                f"  Time Tracked:           {self.total_tracked_hours:.2f}h "
                f"(Est: {self.estimated_hours:.1f}h)"
            ),
            f"  Effective Hourly Rate:  {self.effective_hourly_rate_pln:.0f} PLN/h",
        ]
        return "\n".join(lines)
