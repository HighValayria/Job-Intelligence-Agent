from __future__ import annotations

from datetime import date

from algorithm_push.models.push import PushResult
from algorithm_push.push.adapters import PushAdapter
from algorithm_push.push.formatter import format_daily_questions
from algorithm_push.registry import AlgorithmQuestionRepository


class PushService:
    def __init__(
        self,
        repository: AlgorithmQuestionRepository,
        adapter: PushAdapter,
    ) -> None:
        self.repository = repository
        self.adapter = adapter

    def push_existing_selection(self, selection_date: date) -> PushResult:
        selection = self.repository.get_daily_selection(selection_date)
        if selection is None:
            raise ValueError(
                f"no daily selection exists for {selection_date.isoformat()}; run select first"
            )
        message = format_daily_questions(selection)
        attempt = self.repository.next_push_attempt(selection_date)
        result = self.adapter.send_daily_questions(message)
        self.repository.record_push_result(
            selection=selection,
            attempt=attempt,
            result=result,
        )
        return result
