from __future__ import annotations

from pydantic import Field, field_validator

from models.common import JobIntelModel


class UnifiedContent(JobIntelModel):
    post_id: str
    platform: str
    title: str
    text: str
    ocr_text: str = ""
    full_content: str
    source_images: list[str] = Field(default_factory=list)

    @field_validator("post_id", "platform")
    @classmethod
    def non_empty_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identifier fields cannot be empty")
        return cleaned

