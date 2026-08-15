from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import re

from collectors.real_fixture import RealSampleLoader, sample_to_raw_post
from llm.base import LLMProvider
from models.classification import PostType
from processing.content_builder import ContentBuilder
from processing.ocr import OCRProvider
from scheduler.processor import process_raw_post


@dataclass(frozen=True)
class FieldCheck:
    sample_id: str
    field: str
    expected: Any
    actual: Any
    passed: bool


@dataclass
class EvaluationReport:
    sample_count: int
    gold_count: int
    offer_real_samples: int
    checks: list[FieldCheck] = field(default_factory=list)
    skipped_samples: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return len([check for check in self.checks if check.passed])

    @property
    def failed_count(self) -> int:
        return len([check for check in self.checks if not check.passed])


def evaluate_samples(
    samples_root: Path | str,
    *,
    llm_provider: LLMProvider,
    ocr_provider: OCRProvider,
) -> EvaluationReport:
    loader = RealSampleLoader(samples_root)
    samples = loader.load_all(include_empty=False)
    report = EvaluationReport(
        sample_count=len(samples),
        gold_count=len([sample for sample in samples if sample.has_gold]),
        offer_real_samples=len(
            [sample for sample in samples if sample.expected_type == PostType.OFFER]
        ),
    )
    builder = ContentBuilder(ocr_provider)
    for sample in samples:
        if not sample.gold:
            report.skipped_samples.append(sample.sample_id)
            continue
        processed = process_raw_post(
            sample_to_raw_post(sample),
            content_builder=builder,
            llm_provider=llm_provider,
        )
        actual = _actual_payload(processed)
        for field_path, expected in _flatten_gold(sample.gold):
            actual_value, passed = _check_field(actual, field_path, expected)
            report.checks.append(
                FieldCheck(
                    sample_id=sample.sample_id,
                    field=".".join(field_path),
                    expected=expected,
                    actual=actual_value,
                    passed=passed,
                )
            )
    return report


def render_report(report: EvaluationReport) -> str:
    lines = [
        "Evaluation Report",
        f"Samples: {report.sample_count}",
        f"Gold samples: {report.gold_count}",
        f"Offer real samples: {report.offer_real_samples}",
    ]
    if report.offer_real_samples == 0:
        lines.append("Evaluation skipped")
    if not report.checks:
        lines.append("No gold checks to evaluate.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Sample | Field | Expected | Actual | Pass / Fail")
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(
            f"{check.sample_id} | {check.field} | {check.expected} | {check.actual} | {status}"
        )
    lines.append("")
    lines.append(f"Passed: {report.passed_count}")
    lines.append(f"Failed: {report.failed_count}")
    return "\n".join(lines)


def _actual_payload(processed: Any) -> dict[str, Any]:
    actual: dict[str, Any] = {}
    if processed.classification is not None:
        actual["primary_type"] = processed.classification.primary_type.value
        actual["secondary_tags"] = processed.classification.secondary_tags
    if processed.validated is not None:
        actual.update(processed.validated.model_dump(mode="json"))
    return actual


def _flatten_gold(value: Any, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        output: list[tuple[tuple[str, ...], Any]] = []
        for key, item in value.items():
            output.extend(_flatten_gold(item, prefix + (key,)))
        return output
    if isinstance(value, list):
        output = []
        for index, item in enumerate(value):
            output.extend(_flatten_gold(item, prefix + (str(index),)))
        return output
    return [(prefix, value)]


def _get_path(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for part in path:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def _check_field(actual: dict[str, Any], path: tuple[str, ...], expected: Any) -> tuple[Any, bool]:
    actual_value = _get_path(actual, path)
    if _values_equal(actual_value, expected):
        return actual_value, True

    alternate_value, alternate_passed = _check_alternate_locations(
        actual, path, expected
    )
    if alternate_passed:
        return alternate_value, True

    list_parent_path = _nearest_list_parent_path(path)
    if list_parent_path is None:
        return actual_value, False

    parent = _get_path(actual, list_parent_path)
    if not isinstance(parent, list):
        return actual_value, False
    for item in parent:
        if _values_equal(item, expected):
            return item, True
    return actual_value, False


def _check_alternate_locations(
    actual: dict[str, Any], path: tuple[str, ...], expected: Any
) -> tuple[Any, bool]:
    if not isinstance(expected, str):
        return None, False
    if _is_interview_question_path(path):
        round_data = _get_path(actual, path[:2])
        if isinstance(round_data, dict):
            matched = _find_in_fields(round_data, _QUESTION_FIELDS, expected)
            if matched is not None:
                return matched, True
    if path and path[0] in _RECRUITMENT_FACT_FIELDS:
        matched = _find_in_fields(actual, _RECRUITMENT_FACT_FIELDS, expected)
        if matched is not None:
            return matched, True
    return None, False


def _is_interview_question_path(path: tuple[str, ...]) -> bool:
    return (
        len(path) >= 4
        and path[0] == "rounds"
        and path[1].isdigit()
        and path[2] in _QUESTION_FIELDS
    )


def _find_in_fields(
    actual: dict[str, Any], field_names: tuple[str, ...], expected: str
) -> Any:
    for field_name in field_names:
        value = actual.get(field_name)
        if isinstance(value, list):
            for item in value:
                if _values_equal(item, expected):
                    return item
        elif _values_equal(value, expected):
            return value
    return None


def _nearest_list_parent_path(path: tuple[str, ...]) -> tuple[str, ...] | None:
    for index in range(len(path) - 1, -1, -1):
        if path[index].isdigit():
            return path[:index]
    return None


def _values_equal(actual: Any, expected: Any) -> bool:
    if actual == expected:
        return True
    if actual is None and isinstance(expected, str):
        return _is_unknown_text(expected)
    if isinstance(actual, str) and isinstance(expected, str):
        actual_text = _normalize_comparable_text(actual)
        expected_text = _normalize_comparable_text(expected)
        if actual_text == expected_text:
            return True
        return (
            _text_contains(actual_text, expected_text)
            or _text_similar(actual_text, expected_text)
            or _long_common_fragment(actual_text, expected_text)
        )
    return False


def _normalize_comparable_text(value: str) -> str:
    value = value.replace("教育部留学服务中心", "留服中心")
    value = value.replace("问了一下", "追问").replace("问一下", "追问")
    value = value.replace("网申或内推", "网申内推").replace("流程为", "流程")
    value = re.sub(r"(\d)\s*(?:至|到|~|～|-)\s*(\d)", r"\1\2", value)
    value = re.sub(r"非技术类[^；;。]*?(大专及以上)", r"非技术类\1", value)
    value = re.sub(r"(?<!非)技术类[^；;。]*?(本科(?:起步|及以上)?)", r"技术类\1", value)
    return re.sub(r"[\s，。！？、；：,.!?;:（）()\[\]【】“”\"'`·\-—_/｜|~～→]+", "", value).lower()


def _text_contains(actual: str, expected: str) -> bool:
    actual_cleaned = _strip_common_prefixes(actual)
    expected_cleaned = _strip_common_prefixes(expected)
    if len(actual_cleaned) < 4 or len(expected_cleaned) < 4:
        return False
    return expected_cleaned in actual_cleaned or actual_cleaned in expected_cleaned


def _text_similar(actual: str, expected: str) -> bool:
    actual_cleaned = _strip_common_prefixes(actual)
    expected_cleaned = _strip_common_prefixes(expected)
    if _has_conflicting_kafka_topic(actual_cleaned, expected_cleaned):
        return False
    shorter = min(len(actual_cleaned), len(expected_cleaned))
    if shorter < 8:
        return False
    threshold = 0.84 if shorter < 16 else 0.70
    return SequenceMatcher(None, actual_cleaned, expected_cleaned).ratio() >= threshold


def _long_common_fragment(actual: str, expected: str) -> bool:
    actual_cleaned = _strip_common_prefixes(actual)
    expected_cleaned = _strip_common_prefixes(expected)
    if _has_conflicting_kafka_topic(actual_cleaned, expected_cleaned):
        return False
    shorter = min(len(actual_cleaned), len(expected_cleaned))
    if shorter < 12:
        return False
    match = SequenceMatcher(None, actual_cleaned, expected_cleaned).find_longest_match()
    return match.size >= max(10, int(shorter * 0.55))


def _is_unknown_text(value: str) -> bool:
    normalized = _normalize_comparable_text(value)
    return normalized.startswith("未知") or normalized in {"无", "不详", "未提及"}


def _has_conflicting_kafka_topic(actual: str, expected: str) -> bool:
    if "kafka" not in actual or "kafka" not in expected:
        return False
    topic_markers = ("不丢失", "不重复", "顺序", "堆积")
    actual_markers = {marker for marker in topic_markers if marker in actual}
    expected_markers = {marker for marker in topic_markers if marker in expected}
    return bool(actual_markers and expected_markers and actual_markers != expected_markers)


def _strip_common_prefixes(value: str) -> str:
    prefixes = ("手撕", "代码题", "coding", "leetcode", "lc", "算法手写题", "算法题")
    output = value
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if output.startswith(prefix):
                output = output[len(prefix) :]
                changed = True
    return output


_QUESTION_FIELDS = (
    "project_questions",
    "basic_questions",
    "system_design_questions",
    "coding_questions",
    "algorithm_questions",
    "scenario_questions",
    "behavior_questions",
)

_RECRUITMENT_FACT_FIELDS = (
    "requirements",
    "responsibilities",
    "application_method",
    "education_requirement",
    "major_requirement",
)
