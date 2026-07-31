from __future__ import annotations

from llm.base import LLMProvider
from models.classification import ClassificationResult
from models.unified_content import UnifiedContent


def classify_content(
    provider: LLMProvider, content: UnifiedContent
) -> ClassificationResult:
    return provider.classify(content)

