from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AlgorithmPushModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class QuestionPool(StrEnum):
    LEETCODE_HOT100 = "leetcode_hot100"
    LEETCODE_CUSTOM = "leetcode_custom"
    NOWCODER_HOT101 = "nowcoder_hot101"
    INTERVIEW_EXTRACTED = "interview_extracted"
    INTERVIEW_MANUAL = "interview_manual"


class Platform(StrEnum):
    LEETCODE = "leetcode"
    NOWCODER = "nowcoder"
    OTHER = "other"


class QuestionStatus(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    MANUAL_REVIEW = "manual_review"


class QuestionInput(AlgorithmPushModel):
    canonical_key: str | None = None
    title: str
    url: str | None = None
    pool: QuestionPool
    platform: Platform | None = None
    primary_tag: str = "other"
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: float = Field(default=1.0, gt=0)
    status: QuestionStatus = QuestionStatus.ACTIVE
    aliases: list[str] = Field(default_factory=list)

    @field_validator("title", "primary_tag")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("canonical_key")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for tag in value:
            stripped = tag.strip()
            if stripped and stripped not in normalized:
                normalized.append(stripped)
        return normalized

    @model_validator(mode="before")
    @classmethod
    def _fill_platform_and_tags(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        values = dict(data)
        pool = values.get("pool")
        pool_value = pool.value if isinstance(pool, QuestionPool) else pool
        if not values.get("platform"):
            if pool_value in {
                QuestionPool.LEETCODE_HOT100.value,
                QuestionPool.LEETCODE_CUSTOM.value,
            }:
                values["platform"] = Platform.LEETCODE.value
            elif pool_value == QuestionPool.NOWCODER_HOT101.value:
                values["platform"] = Platform.NOWCODER.value
            else:
                values["platform"] = Platform.OTHER.value

        primary_tag = values.get("primary_tag") or "other"
        tags = list(values.get("tags") or [])
        if primary_tag not in tags:
            tags.insert(0, primary_tag)
        values["tags"] = tags

        if not values.get("url"):
            values["enabled"] = False
            status = values.get("status", QuestionStatus.ACTIVE.value)
            status_value = status.value if isinstance(status, QuestionStatus) else status
            if status_value == QuestionStatus.ACTIVE.value:
                values["status"] = QuestionStatus.PENDING.value
        return values


class Question(QuestionInput):
    question_id: str
    created_at: datetime
    updated_at: datetime


class InterviewQuestionCandidate(AlgorithmPushModel):
    raw_title: str
    normalized_title: str | None = None
    url: str | None = None
    source_post_url: str | None = None
    company: str | None = None
    interview_round: str | None = None
    context: str | None = None
    canonical_key: str | None = None
    primary_tag: str = "other"
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    priority: float = Field(default=1.0, gt=0)
