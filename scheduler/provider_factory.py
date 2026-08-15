from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.base import Collector
from collectors.html_snapshot import HtmlSnapshotCollector
from collectors.mock import MockCollector
from collectors.real_fixture import RealFixtureCollector
from llm.base import LLMProvider
from llm.mock import MockLLMProvider
from llm.real import RealLLMProvider
from processing.ocr import MockOCRProvider, OCRProvider, PaddleOCRProvider


def create_collector(
    source: str,
    *,
    samples_root: Path | str = "real_samples",
    inbox_dir: Path | str = "data/inbox/html",
) -> Collector:
    if source == "mock":
        return MockCollector()
    if source == "real":
        return RealFixtureCollector(samples_root)
    if source in {"html", "html-snapshot"}:
        return HtmlSnapshotCollector(inbox_dir)
    raise ValueError(f"unsupported collector source: {source}")


def create_ocr_provider(name: str) -> OCRProvider:
    if name == "mock":
        return MockOCRProvider()
    if name == "paddle":
        return PaddleOCRProvider()
    raise ValueError(f"unsupported OCR provider: {name}")


def create_llm_provider(name: str, config: dict[str, Any]) -> LLMProvider:
    companies = config.get("companies", {}).get("companies", [])
    taxonomy = config.get("taxonomy", {})
    if name == "mock":
        return MockLLMProvider(companies=companies, taxonomy=taxonomy)
    if name == "real":
        return RealLLMProvider(config.get("llm", {}))
    raise ValueError(f"unsupported LLM provider: {name}")
