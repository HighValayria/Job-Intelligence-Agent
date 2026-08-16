from __future__ import annotations

from collections import Counter

from algorithm_push.models import Question
from algorithm_push.selector.config import TopicConstraintConfig


def satisfies_daily_topic_constraints(
    questions: list[Question],
    config: TopicConstraintConfig,
) -> bool:
    counts = Counter(question.primary_tag for question in questions)
    if len(counts) < config.min_distinct_primary_tags:
        return False
    return all(count <= config.max_per_primary_tag for count in counts.values())
