from __future__ import annotations

from llm.base import ExtractedResult
from models.classification import ClassificationResult

DEFAULT_REVIEW_THRESHOLD = 0.8


def combined_confidence(
    classification: ClassificationResult, extracted: ExtractedResult
) -> float:
    if extracted is None:
        return min(classification.confidence, 0.0)
    return min(classification.confidence, extracted.confidence)


def needs_review(
    classification: ClassificationResult,
    extracted: ExtractedResult,
    *,
    threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> bool:
    return (
        classification.needs_review
        or extracted is None
        or extracted.needs_review
        or combined_confidence(classification, extracted) < threshold
    )

