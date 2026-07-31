from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from models.raw_post import RawPost


class Collector(ABC):
    @abstractmethod
    def collect(self, queries: Sequence[dict[str, Any]] | None = None) -> list[RawPost]:
        """Return platform posts converted into the unified RawPost model."""

