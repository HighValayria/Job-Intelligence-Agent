from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator

from models.common import JobIntelModel


class RawPost(JobIntelModel):
    post_id: str
    platform: str
    url: str
    title: str = ""
    author: str | None = None
    publish_time: datetime | None = None
    crawl_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    text: str = ""
    images: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("post_id", "platform")
    @classmethod
    def non_empty_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("identifier fields cannot be empty")
        return cleaned

