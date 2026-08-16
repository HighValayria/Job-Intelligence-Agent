from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from algorithm_push.models import DailySelection, QuestionInput, QuestionPool, SelectionItem
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector import DailySelector
from algorithm_push.selector.config import SelectionConfig
from algorithm_push.selector.simulation import audit_simulation


def test_selector_enforces_source_ratio_and_daily_topic_constraints(
    tmp_path: Path,
) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_selector_questions(repository)

        selection = DailySelector(repository).select(date(2026, 8, 15), seed=42)

        pools = Counter(question.pool for question in selection.questions)
        tags = Counter(question.primary_tag for question in selection.questions)
        assert pools[QuestionPool.LEETCODE_HOT100] + pools[QuestionPool.LEETCODE_CUSTOM] == 2
        assert pools[QuestionPool.NOWCODER_HOT101] == 2
        assert (
            pools[QuestionPool.INTERVIEW_EXTRACTED]
            + pools[QuestionPool.INTERVIEW_MANUAL]
            == 1
        )
        assert len(tags) >= 3
        assert max(tags.values()) <= 2
        assert len({question.canonical_key for question in selection.questions}) == 5


def test_selector_reuses_persisted_selection_for_same_date(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_selector_questions(repository)
        selector = DailySelector(repository)

        first = selector.select(date(2026, 8, 15), seed=1, persist=True)
        second = selector.select(date(2026, 8, 15), seed=999, persist=True)

        assert [item.question.question_id for item in first.items] == [
            item.question.question_id for item in second.items
        ]


def test_selector_hard_recency_uses_saved_daily_selection(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_selector_questions(repository)
        selector = DailySelector(repository)

        first = selector.select(date(2026, 8, 15), seed=1, persist=True)
        second = selector.select(date(2026, 8, 16), seed=1, persist=True)
        first_keys = {question.canonical_key for question in first.questions}
        second_keys = {question.canonical_key for question in second.questions}

        assert first_keys.isdisjoint(second_keys)


def test_selector_simulates_thirty_days_without_topic_violations(
    tmp_path: Path,
) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_selector_questions(repository, per_group=18)
        selector = DailySelector(repository)

        for offset in range(30):
            selection = selector.select(
                date(2026, 8, 1) + timedelta(days=offset),
                seed=42 + offset,
                persist=True,
            )
            tags = Counter(question.primary_tag for question in selection.questions)
            assert len(tags) >= 3
            assert max(tags.values()) <= 2


def test_simulation_audit_accepts_valid_selector_output(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_selector_questions(repository, per_group=18)
        selector = DailySelector(repository)
        selections = [
            selector.select(
                date(2026, 8, 1) + timedelta(days=offset),
                seed=42 + offset,
                persist=True,
            )
            for offset in range(30)
        ]

        report = audit_simulation(selections, config=SelectionConfig())

        assert report.ok is True
        assert report.violations == []


def test_simulation_audit_flags_hard_recency_violation(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_selector_questions(repository)
        selection = DailySelector(repository).select(date(2026, 8, 15), seed=42)
        repeated = DailySelection(
            selection_date=date(2026, 8, 16),
            items=[
                SelectionItem(
                    question=item.question,
                    slot=item.slot,
                    selected_score=item.selected_score,
                )
                for item in selection.items
            ],
        )

        report = audit_simulation([selection, repeated], config=SelectionConfig())

        assert report.ok is False
        assert any(
            violation.code == "hard_recency_violation"
            for violation in report.violations
        )


def _seed_selector_questions(
    repository: AlgorithmQuestionRepository,
    *,
    per_group: int = 8,
) -> None:
    tags = [
        "array_hash",
        "linked_list",
        "binary_tree",
        "graph",
        "dynamic_programming",
        "backtracking",
        "greedy",
        "string",
        "heap",
        "binary_search",
    ]
    for index in range(per_group):
        tag = tags[index % len(tags)]
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"leetcode:stageb-{index}",
                title=f"LC StageB {index}",
                url=f"https://leetcode.cn/problems/stageb-{index}/",
                pool=QuestionPool.LEETCODE_HOT100
                if index % 2 == 0
                else QuestionPool.LEETCODE_CUSTOM,
                primary_tag=tag,
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"nowcoder:stageb-{index}",
                title=f"NC StageB {index}",
                url=f"https://www.nowcoder.com/stageb/{index}",
                pool=QuestionPool.NOWCODER_HOT101,
                primary_tag=tags[(index + 2) % len(tags)],
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"interview:stageb-{index}",
                title=f"Interview StageB {index}",
                url=f"https://example.test/interview/{index}",
                pool=QuestionPool.INTERVIEW_MANUAL,
                primary_tag=tags[(index + 4) % len(tags)],
            )
        )
