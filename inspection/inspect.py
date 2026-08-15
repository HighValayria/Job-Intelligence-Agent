from __future__ import annotations

import json
from pathlib import Path

from collectors.real_fixture import RealSampleLoader, sample_to_raw_post
from llm.base import LLMProvider
from processing.content_builder import ContentBuilder
from processing.ocr import OCRProvider
from scheduler.processor import process_raw_post


def inspect_sample(
    sample_dir: Path | str,
    *,
    llm_provider: LLMProvider,
    ocr_provider: OCRProvider,
) -> str:
    sample = RealSampleLoader(Path(sample_dir).parents[1]).load_sample(sample_dir)
    raw_post = sample_to_raw_post(sample)
    processed = process_raw_post(
        raw_post,
        content_builder=ContentBuilder(ocr_provider),
        llm_provider=llm_provider,
    )
    lines = [
        f"# Inspect {sample.sample_id}",
        "",
        "## Metadata",
        _json(sample.metadata),
        "",
        "## Original",
        f"Title: {sample.title}",
        "",
        sample.text or "",
        "",
        "## Images",
        "\n".join(sample.images) if sample.images else "(none)",
        "",
        "## OCR",
        _json(processed.content.ocr_results if processed.content else []),
        "",
        "## UnifiedContent",
        processed.content.full_content if processed.content else "(content build failed)",
        "",
        "## Classification",
        _json(
            processed.classification.model_dump(mode="json")
            if processed.classification
            else None
        ),
        "",
        "## Extractor Raw Output",
        _json(processed.extracted.model_dump(mode="json") if processed.extracted else None),
        "",
        "## Normalized Output",
        _json(processed.normalized.model_dump(mode="json") if processed.normalized else None),
        "",
        "## Validation",
        "valid" if processed.validated else "not valid or not applicable",
        "",
        "## Final Structured Result",
        _json(processed.validated.model_dump(mode="json") if processed.validated else None),
        "",
        "## Errors",
        _json([error.model_dump(mode="json") for error in processed.errors]),
    ]
    if sample.gold:
        lines.extend(["", "## Gold Expected", _json(sample.gold)])
    return "\n".join(lines)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
