from __future__ import annotations

from datetime import date

from algorithm_push.models import Question
from algorithm_push.selector.config import RecencyConfig, TopicConstraintConfig


def recency_multiplier(
    *,
    question: Question,
    selection_date: date,
    last_selected_by_canonical: dict[str, date],
    config: RecencyConfig,
) -> float:
    last_date = last_selected_by_canonical.get(question.canonical_key)
    if last_date is None:
        return 1.0
    days_since = (selection_date - last_date).days
    if days_since <= config.hard_exclude_days:
        return 0.0
    return config.penalty.get(days_since, 1.0)


def topic_balance_multiplier(
    *,
    question: Question,
    recent_topic_counts: dict[str, int],
    config: TopicConstraintConfig,
) -> float:
    if not recent_topic_counts:
        return 1.0
    max_count = max(recent_topic_counts.values(), default=0)
    own_count = recent_topic_counts.get(question.primary_tag, 0)
    return 1.0 + max(0, max_count - own_count) * config.underrepresented_bonus


def candidate_score(
    *,
    question: Question,
    selection_date: date,
    last_selected_by_canonical: dict[str, date],
    recent_topic_counts: dict[str, int],
    recency_config: RecencyConfig,
    topic_config: TopicConstraintConfig,
) -> float:
    return (
        recency_multiplier(
            question=question,
            selection_date=selection_date,
            last_selected_by_canonical=last_selected_by_canonical,
            config=recency_config,
        )
        * topic_balance_multiplier(
            question=question,
            recent_topic_counts=recent_topic_counts,
            config=topic_config,
        )
        * question.priority
    )
