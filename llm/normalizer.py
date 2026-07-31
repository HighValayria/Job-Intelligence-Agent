from __future__ import annotations

from llm.base import ExtractedResult, LLMProvider


def normalize_extracted(provider: LLMProvider, result: ExtractedResult) -> ExtractedResult:
    return provider.normalize(result)

