from __future__ import annotations

import json
from pathlib import Path

from annotation import draft_gold, promote_gold
from collectors.real_fixture import RealFixtureCollector, RealSampleLoader
from evaluation import evaluate_samples, render_report
from evaluation.evaluator import _check_field, _values_equal
from inspection import inspect_sample
from llm.mock import MockLLMProvider
from processing.ocr import MockOCRProvider


def test_real_sample_loader_maps_infodiff_to_information_gap(tmp_path: Path) -> None:
    sample_dir = tmp_path / "real_samples" / "infodiff" / "001"
    sample_dir.mkdir(parents=True)
    (sample_dir / "metadata.json").write_text(
        json.dumps(
            {
                "platform": "xiaohongshu",
                "url": "https://example.com/xhs/1",
                "title": "某部门信息差",
                "text": "听说这个组 WLB 一般，HC 有点紧。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sample_dir / "image_01.jpg").write_bytes(b"fake")

    loader = RealSampleLoader(tmp_path / "real_samples")
    inventory = loader.inventory()
    sample = loader.load_sample(sample_dir)
    posts = RealFixtureCollector(tmp_path / "real_samples").collect()

    assert inventory["by_type"] == {"information_gap": 1}
    assert inventory["with_images"] == 1
    assert sample.expected_type and sample.expected_type.value == "information_gap"
    assert posts[0].post_id == "infodiff/001"
    assert posts[0].metadata["expected_type"] == "information_gap"


def test_evaluation_supports_partial_gold(tmp_path: Path) -> None:
    sample_dir = tmp_path / "real_samples" / "recruitment" / "001"
    sample_dir.mkdir(parents=True)
    (sample_dir / "metadata.json").write_text(
        json.dumps(
            {
                "platform": "nowcoder",
                "url": "https://example.com/recruitment/1",
                "title": "字节跳动校招内推",
                "text": "字节跳动 2026 校招推荐算法工程师招聘，欢迎投递。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (sample_dir / "gold.json").write_text(
        json.dumps(
            {
                "primary_type": "recruitment",
                "company": "字节跳动",
                "job_family": "推荐算法",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = evaluate_samples(
        tmp_path / "real_samples",
        llm_provider=MockLLMProvider(
            taxonomy={"job_families": ["推荐算法"], "aliases": {}}
        ),
        ocr_provider=MockOCRProvider(),
    )

    assert report.gold_count == 1
    assert report.failed_count == 0
    assert "PASS" in render_report(report)


def test_evaluation_matches_list_items_without_index_lockstep() -> None:
    actual = {
        "rounds": [
            {
                "coding_questions": [
                    "手撕：Merge K sorted lists",
                    "Reverse linked list",
                ]
            }
        ]
    }

    matched_value, passed = _check_field(
        actual,
        ("rounds", "0", "coding_questions", "0"),
        "Merge K sorted lists",
    )

    assert passed is True
    assert matched_value == "手撕：Merge K sorted lists"
    assert _values_equal("Java/Python backend roles", "backend roles")
    assert _values_equal(
        "毕业时间在2026年9月1日至2027年8月31日",
        "毕业时间为 2026年9月1日 至 2027年8月31日。",
    )
    assert _values_equal(
        "问平时怎么使用AI的，讲讲遇到的问题和坑以及怎么解决",
        "平时怎么使用 AI，讲讲遇到的问题、坑以及如何解决。",
    )
    assert not _values_equal("AI", "BI")
    assert not _values_equal(
        "总行岗位竞争最激烈、要求最高；分行岗位压力较小",
        "春招岗位少、竞争大。",
    )


def test_inspect_sample_outputs_intermediate_sections(tmp_path: Path) -> None:
    sample_dir = tmp_path / "real_samples" / "interview" / "001"
    sample_dir.mkdir(parents=True)
    (sample_dir / "metadata.json").write_text(
        json.dumps(
            {
                "platform": "nowcoder",
                "url": "https://example.com/interview/1",
                "title": "美团推荐算法一面面经",
                "text": "一面：自我介绍，手撕 LRU。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = inspect_sample(
        sample_dir,
        llm_provider=MockLLMProvider(),
        ocr_provider=MockOCRProvider(),
    )

    assert "## UnifiedContent" in output
    assert "## Classification" in output
    assert "## Final Structured Result" in output


def test_draft_gold_and_promote_keep_review_boundary(tmp_path: Path) -> None:
    sample_dir = tmp_path / "real_samples" / "recruitment" / "001"
    sample_dir.mkdir(parents=True)
    (sample_dir / "metadata.json").write_text(
        json.dumps(
            {
                "platform": "nowcoder",
                "url": "https://example.com/recruitment/1",
                "title": "字节跳动校招内推",
                "text": "字节跳动 2026 校招推荐算法工程师招聘，欢迎投递。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    draft_summary = draft_gold(
        tmp_path / "real_samples",
        llm_provider=MockLLMProvider(
            taxonomy={"job_families": ["推荐算法"], "aliases": {}}
        ),
        ocr_provider=MockOCRProvider(),
    )

    draft_path = sample_dir / "gold_draft.json"
    gold_path = sample_dir / "gold.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))

    assert draft_summary.written == ["recruitment/001"]
    assert draft["_draft"]["status"] == "needs_human_review"
    assert draft["primary_type"] == "recruitment"
    assert not gold_path.exists()

    promote_summary = promote_gold(tmp_path / "real_samples")
    gold = json.loads(gold_path.read_text(encoding="utf-8"))

    assert promote_summary.written == ["recruitment/001"]
    assert "_draft" not in gold
    assert gold["primary_type"] == "recruitment"
