from __future__ import annotations

from pathlib import Path

from algorithm_push.models import QuestionInput, QuestionPool
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector.config import SelectionConfig
from algorithm_push.validation import (
    check_readiness,
    render_readiness,
    render_registry_health,
    validate_registry,
)


def test_registry_health_reports_counts_without_errors(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        repository.upsert_question(
            QuestionInput(
                canonical_key="leetcode:1",
                title="1. 两数之和",
                url="https://leetcode.cn/problems/two-sum/",
                pool=QuestionPool.LEETCODE_HOT100,
                primary_tag="array_hash",
            )
        )

        report = validate_registry(repository)
        rendered = render_registry_health(report)

        assert report.total_questions == 1
        assert report.error_count == 0
        assert "leetcode_hot100: 1" in rendered


def test_registry_health_flags_invalid_primary_tag(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        repository.upsert_question(
            QuestionInput(
                canonical_key="interview:weird",
                title="奇怪题型",
                url="https://example.test/weird",
                pool=QuestionPool.INTERVIEW_MANUAL,
                primary_tag="not_a_real_tag",
            )
        )

        report = validate_registry(repository)

        assert report.error_count == 1
        assert report.issues[0].code == "invalid_primary_tag"


def test_registry_health_warns_duplicate_canonical_across_rows(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        repository.upsert_question(
            QuestionInput(
                canonical_key="leetcode:1",
                title="1. 两数之和",
                url="https://leetcode.cn/problems/two-sum/",
                pool=QuestionPool.LEETCODE_HOT100,
                primary_tag="array_hash",
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key="leetcode:1",
                title="LC 1 extra",
                url="https://example.test/two-sum",
                pool=QuestionPool.INTERVIEW_MANUAL,
                primary_tag="array_hash",
            )
        )

        report = validate_registry(repository)

        assert report.warning_count == 1
        assert report.issues[0].code == "canonical_in_multiple_rows"


def test_readiness_passes_with_enough_eligible_capacity(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_capacity_questions(repository, leetcode=6, nowcoder=6, interview=3)

        report = check_readiness(
            repository,
            config=SelectionConfig(),
            days=30,
        )

        assert report.ok is True
        assert "status: ready" in render_readiness(report)


def test_readiness_fails_when_interview_extra_capacity_is_missing(
    tmp_path: Path,
) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_capacity_questions(repository, leetcode=6, nowcoder=6, interview=0)

        report = check_readiness(
            repository,
            config=SelectionConfig(),
            days=30,
        )

        assert report.ok is False
        assert any(
            issue.code == "insufficient_interview_extra_capacity"
            for issue in report.issues
        )


def _seed_capacity_questions(
    repository: AlgorithmQuestionRepository,
    *,
    leetcode: int,
    nowcoder: int,
    interview: int,
) -> None:
    tags = ["array_hash", "linked_list", "binary_tree", "graph", "design"]
    for index in range(leetcode):
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"leetcode:ready-{index}",
                title=f"LC Ready {index}",
                url=f"https://leetcode.cn/problems/ready-{index}/",
                pool=QuestionPool.LEETCODE_HOT100,
                primary_tag=tags[index % len(tags)],
            )
        )
    for index in range(nowcoder):
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"nowcoder:ready-{index}",
                title=f"NC Ready {index}",
                url=f"https://www.nowcoder.com/ready/{index}",
                pool=QuestionPool.NOWCODER_HOT101,
                primary_tag=tags[(index + 1) % len(tags)],
            )
        )
    for index in range(interview):
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"interview:ready-{index}",
                title=f"Interview Ready {index}",
                url=f"https://example.test/ready/{index}",
                pool=QuestionPool.INTERVIEW_MANUAL,
                primary_tag=tags[(index + 2) % len(tags)],
            )
        )
