from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from algorithm_push.models.question import AlgorithmPushModel


class PushStatus(StrEnum):
    SELECTED = "selected"
    SENT = "sent"
    FAILED = "failed"


class PushResult(AlgorithmPushModel):
    status: PushStatus
    message: str | None = None
    error: str | None = None
    pushed_at: datetime | None = None

    @property
    def ok(self) -> bool:
        return self.status == PushStatus.SENT
