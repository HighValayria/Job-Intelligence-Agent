from __future__ import annotations

from datetime import datetime, timezone

from algorithm_push.models.push import PushResult, PushStatus
from algorithm_push.push.adapters import PushAdapter


class ConsoleAdapter(PushAdapter):
    def send_daily_questions(self, message: str) -> PushResult:
        print(message)
        return PushResult(
            status=PushStatus.SENT,
            message="printed to console",
            pushed_at=datetime.now(timezone.utc),
        )
