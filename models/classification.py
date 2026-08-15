from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator

from models.common import JobIntelModel


class PostType(str, Enum):
    RECRUITMENT = "recruitment"
    INTERVIEW = "interview"
    OFFER = "offer"
    INFORMATION_GAP = "information_gap"
    WORK_CONDITION = "work_condition"
    PROGRESS = "progress"
    OTHER = "other"


class ClassificationResult(JobIntelModel):
    primary_type: PostType
    secondary_tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    needs_review: bool = False

    @field_validator("primary_type", mode="before")
    @classmethod
    def normalize_primary_type(cls, value: str | PostType) -> str | PostType:
        if isinstance(value, str) and value in {"infodiff", "information_diff"}:
            return PostType.INFORMATION_GAP
        if value == "work_condition":
            return PostType.INFORMATION_GAP
        return value

    @field_validator("secondary_tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        return sorted({tag.strip() for tag in tags if tag.strip()})
