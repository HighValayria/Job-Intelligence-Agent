from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from models.common import JobIntelModel


class ContentSegment(JobIntelModel):
    source: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnifiedContent(JobIntelModel):
    post_id: str
    platform: str
    title: str
    text: str
    ocr_text: str = ""
    full_content: str
    source_images: list[str] = Field(default_factory=list)
    segments: list[ContentSegment] = Field(default_factory=list)
    ocr_results: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("post_id", "platform")
    @classmethod
    def non_empty_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identifier fields cannot be empty")
        return cleaned
