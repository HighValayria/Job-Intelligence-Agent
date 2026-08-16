from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecencyConfig:
    hard_exclude_days: int = 2
    penalty: dict[int, float] = field(
        default_factory=lambda: {
            3: 0.25,
            4: 0.50,
            5: 0.75,
        }
    )


@dataclass(frozen=True)
class TopicConstraintConfig:
    min_distinct_primary_tags: int = 3
    max_per_primary_tag: int = 2
    recent_window_days: int = 7
    underrepresented_bonus: float = 0.15


@dataclass(frozen=True)
class SelectionConfig:
    leetcode_count: int = 2
    nowcoder_count: int = 2
    interview_extra_count: int = 1
    max_attempts: int = 500
    recency: RecencyConfig = field(default_factory=RecencyConfig)
    topics: TopicConstraintConfig = field(default_factory=TopicConstraintConfig)
