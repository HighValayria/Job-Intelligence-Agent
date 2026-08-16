from __future__ import annotations

from pathlib import Path

from algorithm_push.cli.commands import _export_questions_csv
from algorithm_push.models import InterviewQuestionCandidate, QuestionPool
from algorithm_push.registry import AlgorithmQuestionRepository


def test_review_pending_and_resolve_question(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        result = repository.upsert_interview_question(
            InterviewQuestionCandidate(
                raw_title="手撕 LRU",
                normalized_title="手撕 LRU",
                source_post_url="https://example.test/post/1",
                company="示例公司",
                interview_round="一面",
                context="示例公司 / 一面",
                primary_tag="design",
            )
        )

        pending_rows = repository.review_rows()
        assert len(pending_rows) == 1
        assert pending_rows[0]["question_id"] == result.question_id
        assert pending_rows[0]["mention_count"] == 1

        resolved = repository.resolve_pending_question(
            question_id=result.question_id or "",
            canonical_key="leetcode:146",
            title="146. LRU 缓存",
            url="https://leetcode.cn/problems/lru-cache/",
            primary_tag="design",
            aliases=["手撕 LRU", "LRU"],
        )

        assert resolved.status.value == "active"
        assert resolved.enabled is True
        assert resolved.canonical_key == "leetcode:146"
        assert resolved.url == "https://leetcode.cn/problems/lru-cache/"
        assert repository.review_rows() == []
        assert repository.list_questions(
            pool=QuestionPool.INTERVIEW_EXTRACTED,
            active_only=True,
        )[0].question_id == resolved.question_id


def test_export_questions_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "questions.csv"
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        result = repository.upsert_interview_question(
            InterviewQuestionCandidate(
                raw_title="Top K https://example.test/top-k",
                normalized_title="Top K",
                url="https://example.test/top-k",
                primary_tag="heap",
            )
        )

        questions = repository.list_questions()
        _export_questions_csv(questions, output_path)

    text = output_path.read_text(encoding="utf-8-sig")
    assert "question_id,canonical_key,title,url,pool" in text
    assert "Top K" in text
    assert result.question_id in text
