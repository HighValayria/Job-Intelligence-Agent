from __future__ import annotations

from dataclasses import dataclass, field

from llm.base import ExtractedResult, LLMProvider
from llm.classifier import classify_content
from llm.extractor import extract_content
from llm.normalizer import normalize_extracted
from models.classification import ClassificationResult
from models.raw_post import RawPost
from models.unified_content import UnifiedContent
from pipeline_errors import PipelineErrorRecord, PipelineStage
from processing.content_builder import ContentBuilder
from validation.schema_validator import validate_classification, validate_extraction


@dataclass
class ProcessedPost:
    raw_post: RawPost
    content: UnifiedContent | None = None
    classification: ClassificationResult | None = None
    extracted: ExtractedResult = None
    normalized: ExtractedResult = None
    validated: ExtractedResult = None
    errors: list[PipelineErrorRecord] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.content is not None and self.classification is not None


def process_raw_post(
    raw_post: RawPost,
    *,
    content_builder: ContentBuilder,
    llm_provider: LLMProvider,
) -> ProcessedPost:
    result = ProcessedPost(raw_post=raw_post)
    try:
        result.content = content_builder.build(raw_post)
    except Exception as exc:
        result.errors.append(_error(raw_post, PipelineStage.OCR_ERROR, "ocr", exc))
        return result

    for ocr_result in result.content.ocr_results:
        if ocr_result.get("status") == "error":
            result.errors.append(
                PipelineErrorRecord(
                    sample_id=raw_post.metadata.get("sample_id"),
                    post_id=raw_post.post_id,
                    platform=raw_post.platform,
                    stage=PipelineStage.OCR_ERROR,
                    provider=ocr_result.get("provider"),
                    error=str(ocr_result.get("error") or "OCR failed"),
                )
            )

    try:
        result.classification = validate_classification(
            classify_content(llm_provider, result.content)
        )
    except Exception as exc:
        stage = (
            PipelineStage.API_ERROR
            if llm_provider.__class__.__name__ == "RealLLMProvider"
            else PipelineStage.CLASSIFICATION_ERROR
        )
        result.errors.append(_error(raw_post, stage, llm_provider.__class__.__name__, exc))
        return result

    try:
        result.extracted = extract_content(
            llm_provider, result.content, result.classification.primary_type
        )
    except Exception as exc:
        stage = (
            PipelineStage.API_ERROR
            if llm_provider.__class__.__name__ == "RealLLMProvider"
            else PipelineStage.EXTRACTION_ERROR
        )
        result.errors.append(_error(raw_post, stage, llm_provider.__class__.__name__, exc))
        return result

    try:
        result.normalized = normalize_extracted(llm_provider, result.extracted)
    except Exception as exc:
        result.errors.append(
            _error(raw_post, PipelineStage.NORMALIZATION_ERROR, llm_provider.__class__.__name__, exc)
        )
        return result

    try:
        result.validated = validate_extraction(
            result.classification.primary_type, result.normalized
        )
    except Exception as exc:
        result.errors.append(
            _error(raw_post, PipelineStage.VALIDATION_ERROR, "pydantic", exc)
        )
    return result


def _error(
    raw_post: RawPost, stage: PipelineStage, provider: str, exc: Exception
) -> PipelineErrorRecord:
    return PipelineErrorRecord(
        sample_id=raw_post.metadata.get("sample_id"),
        post_id=raw_post.post_id,
        platform=raw_post.platform,
        stage=stage,
        provider=provider,
        error=str(exc),
    )
