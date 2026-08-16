from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from algorithm_push.models import Question, QuestionPool
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector.config import SelectionConfig
from algorithm_push.validation.registry_health import (
    RegistryHealthReport,
    validate_registry,
)


Severity = Literal["error", "warning"]

LEETCODE_POOLS = {QuestionPool.LEETCODE_HOT100, QuestionPool.LEETCODE_CUSTOM}
NOWCODER_POOLS = {QuestionPool.NOWCODER_HOT101}
INTERVIEW_POOLS = {QuestionPool.INTERVIEW_EXTRACTED, QuestionPool.INTERVIEW_MANUAL}


@dataclass(frozen=True)
class ReadinessIssue:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True)
class CapacityCheck:
    name: str
    active_count: int
    required_minimum: int

    @property
    def ok(self) -> bool:
        return self.active_count >= self.required_minimum


@dataclass(frozen=True)
class ReadinessReport:
    registry: RegistryHealthReport
    days: int
    capacity_checks: list[CapacityCheck]
    eligible_interview_extra_count: int
    excluded_interview_hot_duplicates: int
    eligible_primary_tag_count: int
    issues: list[ReadinessIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        registry_errors = self.registry.error_count
        readiness_errors = sum(1 for issue in self.issues if issue.severity == "error")
        return registry_errors + readiness_errors

    @property
    def warning_count(self) -> int:
        registry_warnings = self.registry.warning_count
        readiness_warnings = sum(
            1 for issue in self.issues if issue.severity == "warning"
        )
        return registry_warnings + readiness_warnings

    @property
    def ok(self) -> bool:
        return self.error_count == 0


def check_readiness(
    repository: AlgorithmQuestionRepository,
    *,
    config: SelectionConfig,
    days: int = 30,
    taxonomy_path: Path | str | None = None,
) -> ReadinessReport:
    if days <= 0:
        raise ValueError("days must be positive")

    registry = validate_registry(repository, taxonomy_path=taxonomy_path)
    active_questions = repository.list_questions(active_only=True)
    active_by_pool = {
        pool: [question for question in active_questions if question.pool == pool]
        for pool in QuestionPool
    }
    leetcode = _questions_in_pools(active_by_pool, LEETCODE_POOLS)
    nowcoder = _questions_in_pools(active_by_pool, NOWCODER_POOLS)
    interview = _questions_in_pools(active_by_pool, INTERVIEW_POOLS)
    eligible_interview = [
        question
        for question in interview
        if not repository.canonical_has_hot_pool(question.canonical_key)
    ]

    capacity_window = min(days, config.recency.hard_exclude_days + 1)
    capacity_checks = [
        CapacityCheck(
            name="leetcode",
            active_count=len(leetcode),
            required_minimum=config.leetcode_count * capacity_window,
        ),
        CapacityCheck(
            name="nowcoder",
            active_count=len(nowcoder),
            required_minimum=config.nowcoder_count * capacity_window,
        ),
        CapacityCheck(
            name="interview_extra",
            active_count=len(eligible_interview),
            required_minimum=config.interview_extra_count * capacity_window,
        ),
    ]

    issues: list[ReadinessIssue] = []
    for check in capacity_checks:
        if not check.ok:
            issues.append(
                ReadinessIssue(
                    severity="error",
                    code=f"insufficient_{check.name}_capacity",
                    message=(
                        f"{check.name} has {check.active_count} active eligible questions; "
                        f"needs at least {check.required_minimum} for {days} day(s) "
                        f"with hard recency {config.recency.hard_exclude_days}"
                    ),
                )
            )

    eligible_questions = [*leetcode, *nowcoder, *eligible_interview]
    eligible_tags = {
        question.primary_tag for question in eligible_questions if question.primary_tag
    }
    if len(eligible_tags) < config.topics.min_distinct_primary_tags:
        issues.append(
            ReadinessIssue(
                severity="error",
                code="insufficient_topic_diversity",
                message=(
                    "eligible active questions cover "
                    f"{len(eligible_tags)} primary tag(s); needs at least "
                    f"{config.topics.min_distinct_primary_tags}"
                ),
            )
        )
    if not eligible_interview and interview:
        issues.append(
            ReadinessIssue(
                severity="warning",
                code="interview_pool_only_hot_duplicates",
                message="all active interview questions are duplicates of HOT pools",
            )
        )

    return ReadinessReport(
        registry=registry,
        days=days,
        capacity_checks=capacity_checks,
        eligible_interview_extra_count=len(eligible_interview),
        excluded_interview_hot_duplicates=len(interview) - len(eligible_interview),
        eligible_primary_tag_count=len(eligible_tags),
        issues=issues,
    )


def render_readiness(report: ReadinessReport) -> str:
    lines = [
        "Algorithm push readiness",
        f"days: {report.days}",
        f"status: {'ready' if report.ok else 'not_ready'}",
        f"errors: {report.error_count}",
        f"warnings: {report.warning_count}",
        "",
        "Capacity",
    ]
    for check in report.capacity_checks:
        state = "ok" if check.ok else "missing"
        lines.append(
            f"  {check.name}: {check.active_count}/{check.required_minimum} {state}"
        )
    lines.extend(
        [
            "",
            "Eligibility",
            f"  interview_extra_eligible: {report.eligible_interview_extra_count}",
            "  interview_hot_duplicates_excluded: "
            f"{report.excluded_interview_hot_duplicates}",
            f"  eligible_primary_tags: {report.eligible_primary_tag_count}",
        ]
    )
    if report.registry.issues or report.issues:
        lines.append("")
        lines.append("Issues")
        for issue in report.registry.issues:
            question = issue.question_id or "-"
            lines.append(
                f"[{issue.severity}] {issue.code} question_id={question}: "
                f"{issue.message}"
            )
        for issue in report.issues:
            lines.append(f"[{issue.severity}] {issue.code}: {issue.message}")
    return "\n".join(lines)


def _questions_in_pools(
    active_by_pool: dict[QuestionPool, list[Question]],
    pools: set[QuestionPool],
) -> list[Question]:
    questions: list[Question] = []
    for pool in pools:
        questions.extend(active_by_pool.get(pool, []))
    return questions
