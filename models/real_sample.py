from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from models.classification import PostType
from models.common import JobIntelModel


class RealSample(JobIntelModel):
    sample_id: str
    sample_dir: Path
    type_dir: str
    platform: str
    url: str = ""
    title: str = ""
    text: str = ""
    images: list[str] = Field(default_factory=list)
    publish_time: str | None = None
    expected_type: PostType | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    gold: dict[str, Any] | None = None

    @property
    def has_content(self) -> bool:
        return bool(self.title or self.text or self.images)

    @property
    def has_gold(self) -> bool:
        return self.gold is not None

