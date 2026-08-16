from __future__ import annotations

from pathlib import Path
from typing import Any

from algorithm_push.selector.config import (
    RecencyConfig,
    SelectionConfig,
    TopicConstraintConfig,
)


def load_selection_config(path: Path | str | None = None) -> SelectionConfig:
    if path is None:
        return SelectionConfig()
    file_path = Path(path)
    if not file_path.exists():
        return SelectionConfig()
    payload = _load_yaml(file_path)
    selection = payload.get("selection", {})
    recency = payload.get("recency", {})

    source_slots = selection.get("source_slots", {})
    topic_constraints = selection.get("daily_topic_constraints", {})
    return SelectionConfig(
        leetcode_count=int(source_slots.get("leetcode", 2)),
        nowcoder_count=int(source_slots.get("nowcoder", 2)),
        interview_extra_count=int(source_slots.get("interview_extra", 1)),
        recency=RecencyConfig(
            hard_exclude_days=int(recency.get("hard_exclude_days", 2)),
            penalty={
                int(day): float(multiplier)
                for day, multiplier in recency.get(
                    "penalty",
                    {
                        3: 0.25,
                        4: 0.50,
                        5: 0.75,
                    },
                ).items()
            },
        ),
        topics=TopicConstraintConfig(
            min_distinct_primary_tags=int(
                topic_constraints.get("min_distinct_primary_tags", 3)
            ),
            max_per_primary_tag=int(topic_constraints.get("max_per_primary_tag", 2)),
            recent_window_days=int(selection.get("recent_topic_window_days", 7)),
            underrepresented_bonus=float(
                selection.get("topic_balance_underrepresented_bonus", 0.15)
            ),
        ),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError:
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
