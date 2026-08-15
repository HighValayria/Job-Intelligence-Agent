from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from collectors.real_fixture import RealSampleLoader, sample_to_raw_post
from llm.base import LLMProvider
from models.classification import PostType
from models.real_sample import RealSample
from processing.content_builder import ContentBuilder
from processing.ocr import OCRProvider
from scheduler.processor import process_raw_post


@dataclass
class DraftGoldSummary:
    written: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def draft_gold(
    samples_root: Path | str,
    *,
    llm_provider: LLMProvider,
    ocr_provider: OCRProvider,
    sample_dir: Path | str | None = None,
    output_name: str = "gold_draft.json",
    overwrite: bool = False,
    include_existing_gold: bool = False,
) -> DraftGoldSummary:
    loader = RealSampleLoader(samples_root)
    samples = (
        [loader.load_sample(sample_dir)]
        if sample_dir is not None
        else loader.load_all(include_empty=False)
    )
    summary = DraftGoldSummary()
    builder = ContentBuilder(ocr_provider)
    for sample in samples:
        output_path = sample.sample_dir / output_name
        gold_path = sample.sample_dir / "gold.json"
        if gold_path.exists() and not include_existing_gold:
            summary.skipped[sample.sample_id] = "gold_exists"
            continue
        if output_path.exists() and not overwrite:
            summary.skipped[sample.sample_id] = f"{output_name}_exists"
            continue
        try:
            processed = process_raw_post(
                sample_to_raw_post(sample),
                content_builder=builder,
                llm_provider=llm_provider,
            )
            draft = _draft_from_processed(sample, processed)
            output_path.write_text(
                json.dumps(draft, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary.written.append(sample.sample_id)
        except Exception as exc:
            summary.errors[sample.sample_id] = str(exc)
    return summary


def promote_gold(
    samples_root: Path | str,
    *,
    sample_dir: Path | str | None = None,
    draft_name: str = "gold_draft.json",
    overwrite: bool = False,
) -> DraftGoldSummary:
    loader = RealSampleLoader(samples_root)
    samples = (
        [loader.load_sample(sample_dir)]
        if sample_dir is not None
        else loader.load_all(include_empty=False)
    )
    summary = DraftGoldSummary()
    for sample in samples:
        draft_path = sample.sample_dir / draft_name
        gold_path = sample.sample_dir / "gold.json"
        if not draft_path.exists():
            summary.skipped[sample.sample_id] = f"{draft_name}_missing"
            continue
        if gold_path.exists() and not overwrite:
            summary.skipped[sample.sample_id] = "gold_exists"
            continue
        try:
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            gold = _strip_draft_metadata(draft)
            gold_path.write_text(
                json.dumps(gold, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary.written.append(sample.sample_id)
        except Exception as exc:
            summary.errors[sample.sample_id] = str(exc)
    return summary


def render_draft_summary(summary: DraftGoldSummary) -> str:
    lines = [
        f"written: {len(summary.written)}",
        f"skipped: {len(summary.skipped)}",
        f"errors: {len(summary.errors)}",
    ]
    if summary.written:
        lines.append("written_samples:")
        lines.extend(f"- {sample_id}" for sample_id in summary.written)
    if summary.skipped:
        lines.append("skipped_samples:")
        lines.extend(
            f"- {sample_id}: {reason}"
            for sample_id, reason in summary.skipped.items()
        )
    if summary.errors:
        lines.append("errors:")
        lines.extend(
            f"- {sample_id}: {error}" for sample_id, error in summary.errors.items()
        )
    return "\n".join(lines)


def _draft_from_processed(sample: RealSample, processed: Any) -> dict[str, Any]:
    classification = processed.classification
    predicted_type = (
        classification.primary_type if classification else sample.expected_type
    )
    draft: dict[str, Any] = {
        "_draft": {
            "status": "needs_human_review",
            "sample_id": sample.sample_id,
            "generated_by": "Job Intelligence Agent",
            "source": "pipeline_prediction",
            "note": "Review this file, then run promote-gold to create gold.json.",
        }
    }
    if predicted_type is not None:
        draft["primary_type"] = predicted_type.value

    payload = (
        processed.validated.model_dump(mode="json")
        if processed.validated is not None
        else {}
    )
    if predicted_type == PostType.RECRUITMENT:
        draft.update(_select(payload, _RECRUITMENT_FIELDS))
    elif predicted_type == PostType.INTERVIEW:
        draft.update(_select(payload, _INTERVIEW_FIELDS))
        rounds = payload.get("rounds")
        if rounds:
            draft["rounds"] = [_compact_round(round_data) for round_data in rounds]
    elif predicted_type == PostType.OFFER:
        draft.update(_select(payload, _OFFER_FIELDS))
    elif predicted_type in {PostType.INFORMATION_GAP, PostType.WORK_CONDITION}:
        draft.update(_select(payload, _INFORMATION_GAP_FIELDS))

    return _remove_empty(draft)


def _select(payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: payload.get(field) for field in fields}


def _compact_round(round_data: dict[str, Any]) -> dict[str, Any]:
    return _remove_empty(
        {
            "round_number": round_data.get("round_number"),
            "round_type": round_data.get("round_type"),
            "algorithm_questions": round_data.get("algorithm_questions"),
            "basic_questions": round_data.get("basic_questions"),
            "coding_questions": round_data.get("coding_questions"),
            "system_design_questions": round_data.get("system_design_questions"),
            "scenario_questions": round_data.get("scenario_questions"),
            "behavior_questions": round_data.get("behavior_questions"),
        }
    )


def _remove_empty(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {
            key: _remove_empty(item)
            for key, item in value.items()
            if item is not None and item != "" and item != []
        }
        return {key: item for key, item in cleaned.items() if item != {}}
    if isinstance(value, list):
        return [_remove_empty(item) for item in value if item is not None and item != {}]
    return value


def _strip_draft_metadata(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _strip_draft_metadata(item) if isinstance(item, dict) else item
        for key, item in value.items()
        if not key.startswith("_")
    }


_RECRUITMENT_FIELDS = (
    "company",
    "job_title",
    "job_family",
    "job_type",
    "recruitment_batch",
    "graduation_year",
    "city",
    "application_deadline",
    "application_method",
    "source_url",
    "official_url",
    "referral_code",
)

_INTERVIEW_FIELDS = (
    "company",
    "department",
    "job_title",
    "job_family",
    "recruitment_type",
    "interview_date",
)

_OFFER_FIELDS = (
    "company",
    "job_title",
    "job_family",
    "city",
    "base_monthly",
    "salary_months",
    "annual_base",
    "sign_on_bonus",
    "stock",
    "salary_raw",
    "deadline",
)

_INFORMATION_GAP_FIELDS = (
    "company",
    "department",
    "job_title",
    "job_family",
    "city",
    "topics",
    "salary_raw",
    "base_monthly",
    "salary_months",
    "annual_total_comp",
    "work_hours_raw",
    "headcount_status",
    "conversion_rate",
    "pros",
    "cons",
    "warnings",
    "raw_information",
)
