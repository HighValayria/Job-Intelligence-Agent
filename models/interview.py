from __future__ import annotations

from datetime import date

from models.common import ExtractedRecord, JobIntelModel


class InterviewRound(JobIntelModel):
    round_number: int | None = None
    round_type: str | None = None
    duration: str | None = None
    self_intro: bool | None = None
    project_questions: list[str] | None = None
    basic_questions: list[str] | None = None
    system_design_questions: list[str] | None = None
    coding_questions: list[str] | None = None
    algorithm_questions: list[str] | None = None
    scenario_questions: list[str] | None = None
    behavior_questions: list[str] | None = None
    interviewer_focus: list[str] | None = None
    difficulty: str | None = None
    result: str | None = None


class Interview(ExtractedRecord):
    company: str | None = None
    department: str | None = None
    job_title: str | None = None
    job_family: str | None = None
    recruitment_type: str | None = None
    interview_date: date | None = None
    rounds: list[InterviewRound] | None = None
