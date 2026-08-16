from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from algorithm_push.models import DailySelection, QuestionPool
from algorithm_push.selector.config import SelectionConfig


@dataclass(frozen=True)
class SimulationViolation:
    selection_date: str
    code: str
    message: str


@dataclass(frozen=True)
class SimulationAudit:
    days: int
    violations: list[SimulationViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def audit_simulation(
    selections: list[DailySelection],
    *,
    config: SelectionConfig,
) -> SimulationAudit:
    violations: list[SimulationViolation] = []
    last_selected: dict[str, date] = {}

    for selection in selections:
        date_text = selection.selection_date.isoformat()
        questions = selection.questions
        pools = Counter(question.pool for question in questions)
        tags = Counter(question.primary_tag for question in questions)
        canonicals = [question.canonical_key for question in questions]

        expected_total = (
            config.leetcode_count + config.nowcoder_count + config.interview_extra_count
        )
        if len(questions) != expected_total:
            violations.append(
                SimulationViolation(
                    date_text,
                    "wrong_total_count",
                    f"expected {expected_total} questions, got {len(questions)}",
                )
            )

        leetcode_count = (
            pools[QuestionPool.LEETCODE_HOT100] + pools[QuestionPool.LEETCODE_CUSTOM]
        )
        if leetcode_count != config.leetcode_count:
            violations.append(
                SimulationViolation(
                    date_text,
                    "wrong_leetcode_count",
                    f"expected {config.leetcode_count} LeetCode questions, got {leetcode_count}",
                )
            )
        if pools[QuestionPool.NOWCODER_HOT101] != config.nowcoder_count:
            violations.append(
                SimulationViolation(
                    date_text,
                    "wrong_nowcoder_count",
                    "expected "
                    f"{config.nowcoder_count} NowCoder questions, "
                    f"got {pools[QuestionPool.NOWCODER_HOT101]}",
                )
            )
        interview_count = (
            pools[QuestionPool.INTERVIEW_EXTRACTED] + pools[QuestionPool.INTERVIEW_MANUAL]
        )
        if interview_count != config.interview_extra_count:
            violations.append(
                SimulationViolation(
                    date_text,
                    "wrong_interview_extra_count",
                    "expected "
                    f"{config.interview_extra_count} interview extra questions, "
                    f"got {interview_count}",
                )
            )

        duplicate_count = len(canonicals) - len(set(canonicals))
        if duplicate_count:
            violations.append(
                SimulationViolation(
                    date_text,
                    "duplicate_canonical_same_day",
                    f"{duplicate_count} duplicate canonical keys in one selection",
                )
            )

        if len(tags) < config.topics.min_distinct_primary_tags:
            violations.append(
                SimulationViolation(
                    date_text,
                    "too_few_primary_tags",
                    "expected at least "
                    f"{config.topics.min_distinct_primary_tags} distinct tags, got {len(tags)}",
                )
            )
        if tags and max(tags.values()) > config.topics.max_per_primary_tag:
            tag, count = tags.most_common(1)[0]
            violations.append(
                SimulationViolation(
                    date_text,
                    "too_many_same_primary_tag",
                    f"{tag} appears {count} times",
                )
            )

        for canonical in set(canonicals):
            previous = last_selected.get(canonical)
            if previous is not None:
                days_since = (selection.selection_date - previous).days
                if days_since <= config.recency.hard_exclude_days:
                    violations.append(
                        SimulationViolation(
                            date_text,
                            "hard_recency_violation",
                            f"{canonical} repeated after {days_since} day(s)",
                        )
                    )
            last_selected[canonical] = selection.selection_date

    return SimulationAudit(days=len(selections), violations=violations)


def render_simulation_audit(audit: SimulationAudit) -> str:
    lines = [
        "Simulation audit",
        f"days: {audit.days}",
        f"status: {'passed' if audit.ok else 'failed'}",
        f"violations: {len(audit.violations)}",
    ]
    for violation in audit.violations:
        lines.append(
            f"- {violation.selection_date} [{violation.code}] {violation.message}"
        )
    return "\n".join(lines)
