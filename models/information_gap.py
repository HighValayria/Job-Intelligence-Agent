from __future__ import annotations

from models.common import ExtractedRecord


class InformationGap(ExtractedRecord):
    company: str | None = None
    department: str | None = None
    job_title: str | None = None
    job_family: str | None = None
    city: str | None = None

    base_monthly: int | None = None
    salary_months: int | None = None
    annual_total_comp: int | None = None
    bonus: str | None = None
    stock: str | None = None
    salary_raw: str | None = None

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
    insurance: str | None = None
    provident_fund: str | None = None

    team_atmosphere: str | None = None
    management: str | None = None
    business_outlook: str | None = None
    promotion: str | None = None
    job_stability: str | None = None
    layoff_risk: str | None = None

    headcount_status: str | None = None
    headcount_estimate: int | None = None
    hiring_difficulty: str | None = None
    conversion_rate: str | None = None
    offer_approval: str | None = None
    hiring_process_status: str | None = None
    pool_status: str | None = None

    pros: list[str] | None = None
    cons: list[str] | None = None
    warnings: list[str] | None = None
    recommendation: str | None = None

    raw_information: str | None = None
    topics: list[str] | None = None

    # Backward-compatible fields from the first-stage work_condition schema.
    wlb_score: float | None = None
    overall_sentiment: str | None = None

