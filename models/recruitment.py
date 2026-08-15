from __future__ import annotations

from datetime import date

from models.common import ExtractedRecord


class Recruitment(ExtractedRecord):
    company: str | None = None
    company_type: str | None = None
    department: str | None = None
    job_title: str | None = None
    job_family: str | None = None
    job_type: str | None = None
    recruitment_batch: str | None = None
    graduation_year: int | None = None
    education_requirement: str | None = None
    major_requirement: str | None = None
    city: str | None = None
    skills: list[str] | None = None
    responsibilities: list[str] | None = None
    requirements: list[str] | None = None
    headcount: int | None = None
    application_start: date | None = None
    application_deadline: date | None = None
    application_method: str | None = None
    source_url: str | None = None
    official_url: str | None = None
    referral_code: str | None = None
