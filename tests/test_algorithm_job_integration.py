from __future__ import annotations

from pathlib import Path

from algorithm_push.ingestion import interview_algorithm_candidates
from algorithm_push.models import QuestionPool
from algorithm_push.registry import AlgorithmQuestionRepository
from models.interview import Interview, InterviewRound
from models.raw_post import RawPost
from scheduler.runner import PipelineRunner


def test_interview_algorithm_candidates_include_round_context() -> None:
    raw_post = RawPost(
        post_id="interview-1",
        platform="mock",
        url="https://example.test/post/1",
        title="面经",
        text="一面手撕 LRU",
    )
    interview = Interview(
        post_id="interview-1",
        company="示例公司",
        job_title="后端",
        job_family="后端",
        rounds=[
            InterviewRound(
                round_number=1,
                round_type="一面",
                coding_questions=["手撕 LRU"],
                algorithm_questions=["Top K https://example.test/top-k"],
            )
        ],
    )

    candidates = interview_algorithm_candidates(interview, raw_post=raw_post)

    assert [candidate.normalized_title for candidate in candidates] == [
        "手撕 LRU",
        "Top K",
    ]
    assert candidates[0].source_post_url == raw_post.url
    assert candidates[0].interview_round == "一面"
    assert candidates[0].primary_tag == "design"
    assert candidates[1].url == "https://example.test/top-k"


def test_pipeline_optionally_ingests_interview_algorithm_questions(
    tmp_path: Path,
) -> None:
    job_db_path = tmp_path / "job.sqlite3"
    excel_path = tmp_path / "job.xlsx"
    algorithm_db_path = tmp_path / "algorithm.sqlite3"

    stats = PipelineRunner(
        db_path=job_db_path,
        excel_path=excel_path,
        ingest_algorithm_questions=True,
        algorithm_db_path=algorithm_db_path,
    ).run()

    assert stats.inserted_count == 4
    assert stats.algorithm_mentions_seen == 5
    assert stats.algorithm_questions_saved == 2
    assert stats.algorithm_questions_linked_to_hot_pool == 3
    assert stats.algorithm_questions_pending_without_url == 2

    with AlgorithmQuestionRepository(algorithm_db_path) as repository:
        repository.initialize()
        questions = repository.list_questions(pool=QuestionPool.INTERVIEW_EXTRACTED)
        assert len(questions) == 2
        assert all(question.enabled is False for question in questions)
        assert repository.count_rows("question_mentions") == 5
