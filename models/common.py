from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobIntelModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceValue(JobIntelModel):
    raw_value: Any | None = None
    normalized_value: Any | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str | None = None


class ExtractedRecord(JobIntelModel):
    post_id: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_review: bool = False
    field_evidence: dict[str, EvidenceValue] = Field(default_factory=dict)

