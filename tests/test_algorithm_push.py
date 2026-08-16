from __future__ import annotations

from datetime import date
from pathlib import Path

from algorithm_push.models import PushResult, PushStatus, QuestionInput, QuestionPool
from algorithm_push.push import PushAdapter, PushService, format_daily_questions
from algorithm_push.cli.commands import _render_status
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector import DailySelector


class FailingAdapter(PushAdapter):
    def send_daily_questions(self, message: str) -> PushResult:
        return PushResult(status=PushStatus.FAILED, error="mock failure")


class CapturingAdapter(PushAdapter):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_daily_questions(self, message: str) -> PushResult:
        self.messages.append(message)
        return PushResult(status=PushStatus.SENT, message="captured")


def test_formatter_outputs_plain_text_sections(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_push_questions(repository)
        selection = DailySelector(repository).select(date(2026, 8, 15), seed=42)

        message = format_daily_questions(selection)

        assert "【今日算法题 · 2026-08-15】" in message
        assert "LeetCode" in message
        assert "NowCoder" in message
        assert "面试补充" in message
        assert "https://" in message


def test_push_records_history_for_existing_selection(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_push_questions(repository)
        selection = DailySelector(repository).select(
            date(2026, 8, 15), seed=42, persist=True
        )
        adapter = CapturingAdapter()

        result = PushService(repository, adapter).push_existing_selection(
            selection.selection_date
        )

        assert result.ok is True
        assert len(adapter.messages) == 1
        assert repository.count_rows("push_history") == 5
        assert repository.latest_push_status(selection.selection_date) == "sent"


def test_push_retry_uses_same_selection_and_increments_attempt(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_push_questions(repository)
        selector = DailySelector(repository)
        first = selector.select(date(2026, 8, 15), seed=1, persist=True)

        failed = PushService(repository, FailingAdapter()).push_existing_selection(
            first.selection_date
        )
        second = selector.select(date(2026, 8, 15), seed=999, persist=True)
        sent = PushService(repository, CapturingAdapter()).push_existing_selection(
            first.selection_date
        )

        assert failed.status == PushStatus.FAILED
        assert sent.status == PushStatus.SENT
        assert [item.question.question_id for item in first.items] == [
            item.question.question_id for item in second.items
        ]
        assert repository.count_rows("push_history") == 10
        assert repository.next_push_attempt(first.selection_date) == 3


def test_status_renders_selection_and_recent_push_history(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_push_questions(repository)
        selection = DailySelector(repository).select(
            date(2026, 8, 15), seed=42, persist=True
        )
        PushService(repository, CapturingAdapter()).push_existing_selection(
            selection.selection_date
        )

        class Args:
            date = selection.selection_date
            recent = 7
            config = Path("algorithm_push/config/algorithm_push.yaml")
            taxonomy = Path("algorithm_push/config/tag_taxonomy.yaml")

        rendered = _render_status(repository, Args())

        assert "readiness: ready" in rendered
        assert "selection: created" in rendered
        assert "push: sent" in rendered
        assert "Recent pushes" in rendered
        assert "2026-08-15 attempt=1 status=sent questions=5" in rendered


def _seed_push_questions(repository: AlgorithmQuestionRepository) -> None:
    tags = ["array_hash", "linked_list", "binary_tree", "graph", "heap", "design"]
    for index in range(6):
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"leetcode:push-{index}",
                title=f"LC Push {index}",
                url=f"https://leetcode.cn/problems/push-{index}/",
                pool=QuestionPool.LEETCODE_HOT100,
                primary_tag=tags[index % len(tags)],
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"nowcoder:push-{index}",
                title=f"NC Push {index}",
                url=f"https://www.nowcoder.com/push/{index}",
                pool=QuestionPool.NOWCODER_HOT101,
                primary_tag=tags[(index + 2) % len(tags)],
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"interview:push-{index}",
                title=f"Interview Push {index}",
                url=f"https://example.test/push/{index}",
                pool=QuestionPool.INTERVIEW_MANUAL,
                primary_tag=tags[(index + 4) % len(tags)],
            )
        )
