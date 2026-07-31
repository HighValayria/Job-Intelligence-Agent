from __future__ import annotations

from pathlib import Path

from dedup.content_dedup import content_fingerprint
from llm.mock import MockLLMProvider
from models.raw_post import RawPost
from processing.content_builder import ContentBuilder
from processing.ocr import MockOCRProvider
from storage.repository import Repository


def test_repository_writes_post_and_business_table(tmp_path: Path) -> None:
    raw_post = RawPost(
        post_id="repo_001",
        platform="mock",
        url="https://mock.local/repo/001",
        title="美团后端 offer",
        text="美团到店后端开发 offer，北京，薪资 raw：28×15，2w sign。",
    )
    content = ContentBuilder(MockOCRProvider()).build(raw_post)
    llm = MockLLMProvider()
    classification = llm.classify(content)
    extracted = llm.normalize(llm.extract(content, classification.primary_type))

    with Repository(tmp_path / "test.sqlite3") as repository:
        repository.initialize()
        result = repository.save_processed_post(
            raw_post=raw_post,
            content=content,
            classification=classification,
            extracted=extracted,
            content_fingerprint=content_fingerprint(content.full_content),
        )

        assert result.inserted is True
        assert repository.count_rows("posts") == 1
        assert repository.count_rows("offers") == 1


def test_repository_post_id_dedup(tmp_path: Path) -> None:
    raw_post = RawPost(
        post_id="dup_001",
        platform="mock",
        url="https://mock.local/dup/001",
        title="美团后端 offer",
        text="美团到店后端开发 offer，北京，薪资 raw：28×15，2w sign。",
    )
    content = ContentBuilder(MockOCRProvider()).build(raw_post)
    llm = MockLLMProvider()
    classification = llm.classify(content)
    extracted = llm.normalize(llm.extract(content, classification.primary_type))
    fingerprint = content_fingerprint(content.full_content)

    with Repository(tmp_path / "test.sqlite3") as repository:
        repository.initialize()
        first = repository.save_processed_post(
            raw_post=raw_post,
            content=content,
            classification=classification,
            extracted=extracted,
            content_fingerprint=fingerprint,
        )
        second = repository.save_processed_post(
            raw_post=raw_post,
            content=content,
            classification=classification,
            extracted=extracted,
            content_fingerprint=fingerprint,
        )

        assert first.inserted is True
        assert second.inserted is False
        assert second.reason == "duplicate_post_id"
        assert repository.count_rows("posts") == 1

