from __future__ import annotations

from datetime import date

from models.common import ExtractedRecord


class Offer(ExtractedRecord):
    company: str | None = None
    department: str | None = None
    job_title: str | None = None
    job_family: str | None = None
    city: str | None = None
    offer_level: str | None = None
    offer_tier: str | None = None
    base_monthly: int | None = None
    salary_months: int | None = None
    annual_base: int | None = None
    performance_bonus: int | None = None
    sign_on_bonus: int | None = None
    stock: str | None = None
    allowance: str | None = None
    estimated_total_comp: int | None = None
    probation_salary: str | None = None
    probation_period: str | None = None
    housing: str | None = None
    meal: str | None = None
    transport: str | None = None
    insurance: str | None = None
    provident_fund: str | None = None
    annual_leave: str | None = None
    offer_date: date | None = None
    deadline: date | None = None
    accepted: bool | None = None
    salary_raw: str | None = None
    benefit_raw: str | None = None

