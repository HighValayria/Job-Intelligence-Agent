from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from collectors.base import Collector
from collectors.mock import MockCollector
from config_loader import load_project_config
from dedup.content_dedup import ContentDeduplicator, content_fingerprint
from dedup.post_dedup import PostDeduplicator
from exporters.excel import ExcelExporter
from llm.base import LLMProvider
from llm.classifier import classify_content
from llm.extractor import extract_content
from llm.mock import MockLLMProvider
from llm.normalizer import normalize_extracted
from processing.content_builder import ContentBuilder
from processing.ocr import MockOCRProvider, OCRProvider
from storage.repository import Repository
from validation.schema_validator import validate_classification, validate_extraction


@dataclass(frozen=True)
class PipelineStats:
    run_id: str
    collected_count: int
    inserted_count: int
    skipped_count: int
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    db_path: Path = Path("data/job_intelligence.sqlite3")
    excel_path: Path = Path("data/job_intelligence.xlsx")


class PipelineRunner:
    def __init__(
        self,
        *,
        db_path: Path | str = Path("data/job_intelligence.sqlite3"),
        excel_path: Path | str = Path("data/job_intelligence.xlsx"),
        config_dir: Path | str = Path("config"),
        collector: Collector | None = None,
        ocr_provider: OCRProvider | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.excel_path = Path(excel_path)
        self.config_dir = Path(config_dir)
        self.collector = collector or MockCollector()
        self.ocr_provider = ocr_provider or MockOCRProvider()
        self._llm_provider = llm_provider

    def run(self) -> PipelineStats:
        config = load_project_config(self.config_dir)
        queries = config.get("queries", {}).get("queries", [])
        companies = config.get("companies", {}).get("companies", [])
        taxonomy = config.get("taxonomy", {})
        llm_provider = self._llm_provider or MockLLMProvider(
            companies=companies, taxonomy=taxonomy
        )

        with Repository(self.db_path) as repository:
            repository.initialize()
            repository.refresh_companies(companies)
            run_id = repository.start_crawl_run(self.collector.__class__.__name__)

            inserted_count = 0
            skipped_reasons: dict[str, int] = {}
            content_builder = ContentBuilder(self.ocr_provider)
            post_dedup = PostDeduplicator(repository)
            content_dedup = ContentDeduplicator(repository)

            try:
                raw_posts = self.collector.collect(queries)
                for raw_post in raw_posts:
                    if post_dedup.is_duplicate(raw_post):
                        _count(skipped_reasons, "duplicate_post_id")
                        continue

                    content = content_builder.build(raw_post)
                    fingerprint = content_fingerprint(content.full_content)
                    if content_dedup.is_duplicate(fingerprint):
                        _count(skipped_reasons, "duplicate_content")
                        continue

                    classification = validate_classification(
                        classify_content(llm_provider, content)
                    )
                    extracted = extract_content(
                        llm_provider, content, classification.primary_type
                    )
                    normalized = normalize_extracted(llm_provider, extracted)
                    validated = validate_extraction(
                        classification.primary_type, normalized
                    )

                    result = repository.save_processed_post(
                        raw_post=raw_post,
                        content=content,
                        classification=classification,
                        extracted=validated,
                        content_fingerprint=fingerprint,
                    )
                    if result.inserted:
                        inserted_count += 1
                    else:
                        _count(skipped_reasons, result.reason)

                ExcelExporter(repository).export(self.excel_path)
                skipped_count = sum(skipped_reasons.values())
                repository.finish_crawl_run(
                    run_id,
                    inserted_count=inserted_count,
                    skipped_count=skipped_count,
                )
            except Exception:
                skipped_count = sum(skipped_reasons.values())
                repository.finish_crawl_run(
                    run_id,
                    inserted_count=inserted_count,
                    skipped_count=skipped_count,
                    status="failed",
                )
                raise

        return PipelineStats(
            run_id=run_id,
            collected_count=len(raw_posts),
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            skipped_reasons=skipped_reasons,
            db_path=self.db_path,
            excel_path=self.excel_path,
        )


def _count(counter: dict[str, int], reason: str) -> None:
    counter[reason] = counter.get(reason, 0) + 1

