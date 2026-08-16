from __future__ import annotations

from pathlib import Path

from algorithm_push.ingestion import import_default_questions, import_questions_file
from algorithm_push.ingestion.manual_loader import load_questions_file
from algorithm_push.models import InterviewQuestionCandidate, QuestionInput, QuestionPool
from algorithm_push.registry import AlgorithmQuestionRepository


def test_algorithm_registry_imports_seed_questions(tmp_path: Path) -> None:
    db_path = tmp_path / "algorithm.sqlite3"

    with AlgorithmQuestionRepository(db_path) as repository:
        repository.initialize()
        imported = import_questions_file(
            repository,
            Path("algorithm_push/data/leetcode_custom.yaml"),
            default_pool=QuestionPool.LEETCODE_CUSTOM,
        )

        assert len(imported) == 2
        questions = repository.list_questions(pool=QuestionPool.LEETCODE_CUSTOM)
        assert [question.canonical_key for question in questions] == [
            "leetcode:1094",
            "leetcode:47",
        ]
        assert all(question.pool == QuestionPool.LEETCODE_CUSTOM for question in questions)


def test_default_hot_pools_are_complete(tmp_path: Path) -> None:
    leetcode = load_questions_file(
        Path("algorithm_push/data/leetcode_hot100.yaml"),
        default_pool=QuestionPool.LEETCODE_HOT100,
    )
    nowcoder = load_questions_file(
        Path("algorithm_push/data/nowcoder_hot101.yaml"),
        default_pool=QuestionPool.NOWCODER_HOT101,
    )

    assert len(leetcode) == 100
    assert len(nowcoder) == 101

    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        total = import_default_questions(repository)

        assert total == 206
        assert len(repository.list_questions(pool=QuestionPool.LEETCODE_HOT100)) == 100
        assert len(repository.list_questions(pool=QuestionPool.NOWCODER_HOT101)) == 101


def test_alias_match_keeps_hot_problem_out_of_interview_extra_pool(tmp_path: Path) -> None:
    db_path = tmp_path / "algorithm.sqlite3"

    with AlgorithmQuestionRepository(db_path) as repository:
        repository.initialize()
        repository.upsert_question(
            QuestionInput(
                canonical_key="leetcode:200",
                title="200. 岛屿数量",
                url="https://leetcode.cn/problems/number-of-islands/",
                pool=QuestionPool.LEETCODE_HOT100,
                primary_tag="graph",
                aliases=["岛屿数量"],
            )
        )

        result = repository.upsert_interview_question(
            InterviewQuestionCandidate(
                raw_title="手撕岛屿数量",
                normalized_title="岛屿数量",
                source_post_url="https://example.test/post/1",
                company="mock",
                interview_round="一面",
            )
        )

        assert result.duplicate_of_hot_pool is True
        assert result.inserted_or_updated is False
        assert repository.count_rows("questions") == 1
        assert repository.count_rows("question_mentions") == 1


def test_pending_interview_question_without_url_is_not_active_candidate(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "algorithm.sqlite3"

    with AlgorithmQuestionRepository(db_path) as repository:
        repository.initialize()
        result = repository.upsert_interview_question(
            InterviewQuestionCandidate(
                raw_title="一道区间 DP",
                context="候选人提到一道区间 DP，没有标准题目链接。",
                primary_tag="dynamic_programming",
            )
        )

        assert result.inserted_or_updated is True
        all_questions = repository.list_questions(pool=QuestionPool.INTERVIEW_EXTRACTED)
        active_questions = repository.list_questions(
            pool=QuestionPool.INTERVIEW_EXTRACTED,
            active_only=True,
        )
        assert len(all_questions) == 1
        assert all_questions[0].enabled is False
        assert all_questions[0].status.value == "pending"
        assert active_questions == []
