from __future__ import annotations

from llm.base import ExtractedResult, LLMProvider
from models.classification import PostType
from models.unified_content import UnifiedContent


def extract_content(
    provider: LLMProvider, content: UnifiedContent, post_type: PostType
) -> ExtractedResult:
    return provider.extract(content, post_type)

