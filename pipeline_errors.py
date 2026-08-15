from __future__ import annotations

from enum import Enum

from models.common import JobIntelModel


class PipelineStage(str, Enum):
    OCR_ERROR = "OCR_ERROR"
    CLASSIFICATION_ERROR = "CLASSIFICATION_ERROR"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
    NORMALIZATION_ERROR = "NORMALIZATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    API_ERROR = "API_ERROR"


class PipelineErrorRecord(JobIntelModel):
    sample_id: str | None = None
    post_id: str | None = None
    platform: str | None = None
    stage: PipelineStage
    provider: str | None = None
    error: str
