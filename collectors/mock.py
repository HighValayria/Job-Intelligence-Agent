from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from collectors.base import Collector
from models.raw_post import RawPost


class MockCollector(Collector):
    def __init__(self, fixture_path: Path | str | None = None) -> None:
        self.fixture_path = Path(fixture_path) if fixture_path else _default_fixture()

    def collect(self, queries: Sequence[dict[str, Any]] | None = None) -> list[RawPost]:
        del queries
        raw_items = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return [RawPost.model_validate(item) for item in raw_items]


def _default_fixture() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "mock_posts.json"

