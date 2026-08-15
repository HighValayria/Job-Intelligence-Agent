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
from llm.mock import MockLLMProvider
from processing.content_builder import ContentBuilder
from processing.ocr import MockOCRProvider, OCRProvider
from scheduler.processor import process_raw_post
from storage.repository import Repository


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
            raw_posts = []

            try:
                raw_posts = self.collector.collect(queries)
                for raw_post in raw_posts:
                    if post_dedup.is_duplicate(raw_post):
                        _count(skipped_reasons, "duplicate_post_id")
                        continue

                    processed = process_raw_post(
                        raw_post,
                        content_builder=content_builder,
                        llm_provider=llm_provider,
                    )
                    repository.log_pipeline_errors(processed.errors)
                    if (
                        not processed.ok
                        or processed.content is None
                        or processed.classification is None
                    ):
                        _count(skipped_reasons, "processing_error")
                        continue

                    fingerprint = content_fingerprint(processed.content.full_content)
                    if content_dedup.is_duplicate(fingerprint):
                        _count(skipped_reasons, "duplicate_content")
                        continue

                    result = repository.save_processed_post(
                        raw_post=raw_post,
                        content=processed.content,
                        classification=processed.classification,
                        extracted=processed.validated,
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
