from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from algorithm_push.models import Question
from algorithm_push.registry import AlgorithmQuestionRepository


Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class RegistryHealthIssue:
    severity: Severity
    code: str
    question_id: str | None
    message: str


@dataclass(frozen=True)
class RegistryHealthReport:
    total_questions: int
    pool_counts: dict[str, int]
    status_counts: dict[str, int]
    primary_tag_counts: dict[str, int]
    issues: list[RegistryHealthIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")


def validate_registry(
    repository: AlgorithmQuestionRepository,
    *,
    taxonomy_path: Path | str | None = None,
) -> RegistryHealthReport:
    questions = repository.list_questions()
    allowed_tags = _load_primary_tags(taxonomy_path)
    issues: list[RegistryHealthIssue] = []

    by_canonical: dict[str, list[Question]] = defaultdict(list)
    for question in questions:
        by_canonical[question.canonical_key].append(question)
        if allowed_tags and question.primary_tag not in allowed_tags:
            issues.append(
                RegistryHealthIssue(
                    severity="error",
                    code="invalid_primary_tag",
                    question_id=question.question_id,
                    message=(
                        f"{question.title} uses unsupported primary_tag "
                        f"{question.primary_tag}"
                    ),
                )
            )
        if question.enabled and question.status.value == "active" and not question.url:
            issues.append(
                RegistryHealthIssue(
                    severity="error",
                    code="active_missing_url",
                    question_id=question.question_id,
                    message=f"{question.title} is active but has no URL",
                )
            )
        if question.status.value == "active" and not question.enabled:
            issues.append(
                RegistryHealthIssue(
                    severity="warning",
                    code="active_disabled",
                    question_id=question.question_id,
                    message=f"{question.title} is active but disabled",
                )
            )
        if question.status.value == "pending" and question.url:
            issues.append(
                RegistryHealthIssue(
                    severity="warning",
                    code="pending_has_url",
                    question_id=question.question_id,
                    message=f"{question.title} is pending but already has a URL",
                )
            )

    for canonical_key, canonical_questions in sorted(by_canonical.items()):
        question_ids = {question.question_id for question in canonical_questions}
        pools = {question.pool.value for question in canonical_questions}
        if len(question_ids) > 1:
            issues.append(
                RegistryHealthIssue(
                    severity="warning",
                    code="canonical_in_multiple_rows",
                    question_id=None,
                    message=(
                        f"{canonical_key} appears in {len(question_ids)} rows "
                        f"across pools {', '.join(sorted(pools))}"
                    ),
                )
            )

    return RegistryHealthReport(
        total_questions=len(questions),
        pool_counts=dict(sorted(Counter(q.pool.value for q in questions).items())),
        status_counts=dict(sorted(Counter(q.status.value for q in questions).items())),
        primary_tag_counts=dict(
            sorted(Counter(q.primary_tag for q in questions).items())
        ),
        issues=issues,
    )


def render_registry_health(report: RegistryHealthReport) -> str:
    lines = [
        "Algorithm registry health",
        f"total_questions: {report.total_questions}",
        f"errors: {report.error_count}",
        f"warnings: {report.warning_count}",
        "",
        "Pool counts",
    ]
    lines.extend(_render_counts(report.pool_counts))
    lines.append("")
    lines.append("Status counts")
    lines.extend(_render_counts(report.status_counts))
    lines.append("")
    lines.append("Primary tag counts")
    lines.extend(_render_counts(report.primary_tag_counts))
    if report.issues:
        lines.append("")
        lines.append("Issues")
        for issue in report.issues:
            question = issue.question_id or "-"
            lines.append(
                f"[{issue.severity}] {issue.code} question_id={question}: "
                f"{issue.message}"
            )
    return "\n".join(lines)


def _render_counts(counts: dict[str, int]) -> list[str]:
    if not counts:
        return ["  none"]
    return [f"  {key}: {value}" for key, value in counts.items()]


def _load_primary_tags(path: Path | str | None) -> set[str]:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "tag_taxonomy.yaml"
    file_path = Path(path)
    if not file_path.exists():
        return set()
    payload = _load_yaml(file_path)
    values = payload.get("primary_tags", [])
    return {str(value).strip() for value in values if str(value).strip()}


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        return _load_simple_list_yaml(text)
    return yaml.safe_load(text) or {}


def _load_simple_list_yaml(text: str) -> dict[str, Any]:
    result: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith(":"):
            current_key = stripped[:-1]
            result[current_key] = []
            continue
        if current_key and stripped.startswith("- "):
            result[current_key].append(stripped[2:].strip())
    return result
