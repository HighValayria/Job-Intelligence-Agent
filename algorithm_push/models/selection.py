from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from algorithm_push.models.question import AlgorithmPushModel, Question


class SelectionItem(AlgorithmPushModel):
    question: Question
    slot: str
    selected_score: float = Field(ge=0)


class DailySelection(AlgorithmPushModel):
    selection_date: date
    items: list[SelectionItem]
    created_at: datetime | None = None

    @property
    def questions(self) -> list[Question]:
        return [item.question for item in self.items]
