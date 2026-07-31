from __future__ import annotations

from pydantic import Field

from models.common import ExtractedRecord


class WorkCondition(ExtractedRecord):
    company: str | None = None
    department: str | None = None
    job_family: str | None = None
    city: str | None = None
    base_monthly: int | None = None
    annual_total_comp: int | None = None
    bonus: str | None = None
    stock: str | None = None
    start_time: str | None = None
    end_time_typical: str | None = None
    end_time_extreme: str | None = None
    work_hours_raw: str | None = None
    overtime_frequency: str | None = None
    weekend_work: str | None = None
    on_call: str | None = None
    annual_leave: str | None = None
    canteen: str | None = None
    meal_allowance: str | None = None
    housing: str | None = None
    transport: str | None = None
    management: str | None = None
    team_atmosphere: str | None = None
    promotion: str | None = None
    job_stability: str | None = None
    pros: list[str] | None = None
    cons: list[str] | None = None
    wlb_score: float | None = Field(default=None, ge=0.0, le=10.0)
    overall_sentiment: str | None = None

