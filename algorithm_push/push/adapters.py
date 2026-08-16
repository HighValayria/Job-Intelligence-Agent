from __future__ import annotations

from abc import ABC, abstractmethod

from algorithm_push.models.push import PushResult


class PushAdapter(ABC):
    @abstractmethod
    def send_daily_questions(self, message: str) -> PushResult:
        """Send a rendered daily question message."""
