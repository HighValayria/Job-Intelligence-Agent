from __future__ import annotations

from datetime import datetime
from pathlib import Path

from algorithm_push.models import PushResult, PushStatus, QuestionInput, QuestionPool
from algorithm_push.push import PushAdapter
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.scheduler import (
    DailyScheduler,
    SchedulerConfig,
    SchedulerRunStatus,
    load_scheduler_config,
)
from algorithm_push.selector.config import SelectionConfig


class CapturingAdapter(PushAdapter):
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send_daily_questions(self, message: str) -> PushResult:
        self.messages.append(message)
        return PushResult(status=PushStatus.SENT, message="captured")


def test_scheduler_skips_when_disabled(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_scheduler_questions(repository)
        adapter = CapturingAdapter()
        scheduler = DailyScheduler(
            repository,
            selection_config=SelectionConfig(),
            scheduler_config=SchedulerConfig(push_enabled=False),
            adapter=adapter,
        )

        result = scheduler.run_once(now=datetime(2026, 8, 15, 9, 0), seed=42)

        assert result.status == SchedulerRunStatus.SKIPPED_DISABLED
        assert adapter.messages == []
        assert repository.count_rows("daily_selections") == 0


def test_scheduler_skips_before_due_time(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_scheduler_questions(repository)
        scheduler = DailyScheduler(
            repository,
            selection_config=SelectionConfig(),
            scheduler_config=SchedulerConfig(push_enabled=True),
            adapter=CapturingAdapter(),
        )

        result = scheduler.run_once(now=datetime(2026, 8, 15, 8, 59), seed=42)

        assert result.status == SchedulerRunStatus.SKIPPED_NOT_DUE
        assert repository.count_rows("daily_selections") == 0


def test_scheduler_sends_once_and_skips_already_sent(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_scheduler_questions(repository)
        adapter = CapturingAdapter()
        scheduler = DailyScheduler(
            repository,
            selection_config=SelectionConfig(),
            scheduler_config=SchedulerConfig(push_enabled=True),
            adapter=adapter,
        )

        first = scheduler.run_once(now=datetime(2026, 8, 15, 9, 0), seed=42)
        second = scheduler.run_once(now=datetime(2026, 8, 15, 9, 5), seed=999)

        assert first.status == SchedulerRunStatus.SENT
        assert second.status == SchedulerRunStatus.SKIPPED_ALREADY_SENT
        assert len(adapter.messages) == 1
        assert repository.count_rows("daily_selections") == 5
        assert repository.count_rows("push_history") == 5


def test_scheduler_force_bypasses_disabled_and_due_time(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_scheduler_questions(repository)
        adapter = CapturingAdapter()
        scheduler = DailyScheduler(
            repository,
            selection_config=SelectionConfig(),
            scheduler_config=SchedulerConfig(push_enabled=False),
            adapter=adapter,
        )

        result = scheduler.run_once(
            now=datetime(2026, 8, 15, 8, 0),
            seed=42,
            force=True,
        )

        assert result.status == SchedulerRunStatus.SENT
        assert len(adapter.messages) == 1


def test_scheduler_config_reads_environment_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "algorithm_push.yaml"
    config_path.write_text(
        "push:\n  enabled: false\n  time: \"09:00\"\n  timezone: Asia/Shanghai\n",
        encoding="utf-8",
    )
    previous = {
        "PUSH_ENABLED": None,
        "PUSH_TIME": None,
        "TIMEZONE": None,
    }
    import os

    for key in previous:
        previous[key] = os.environ.get(key)
    try:
        os.environ["PUSH_ENABLED"] = "true"
        os.environ["PUSH_TIME"] = "10:30"
        os.environ["TIMEZONE"] = "UTC"

        config = load_scheduler_config(config_path)

        assert config.push_enabled is True
        assert config.push_time.hour == 10
        assert config.push_time.minute == 30
        assert config.timezone == "UTC"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _seed_scheduler_questions(repository: AlgorithmQuestionRepository) -> None:
    tags = ["array_hash", "linked_list", "binary_tree", "graph", "heap", "design"]
    for index in range(6):
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"leetcode:scheduler-{index}",
                title=f"LC Scheduler {index}",
                url=f"https://leetcode.cn/problems/scheduler-{index}/",
                pool=QuestionPool.LEETCODE_HOT100,
                primary_tag=tags[index % len(tags)],
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"nowcoder:scheduler-{index}",
                title=f"NC Scheduler {index}",
                url=f"https://www.nowcoder.com/scheduler/{index}",
                pool=QuestionPool.NOWCODER_HOT101,
                primary_tag=tags[(index + 2) % len(tags)],
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"interview:scheduler-{index}",
                title=f"Interview Scheduler {index}",
                url=f"https://example.test/scheduler/{index}",
                pool=QuestionPool.INTERVIEW_MANUAL,
                primary_tag=tags[(index + 4) % len(tags)],
            )
        )
