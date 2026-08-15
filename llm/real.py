from __future__ import annotations

import json
import hashlib
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from env_loader import load_env_file
from llm.base import ExtractedResult, LLMProvider
from models.classification import ClassificationResult, PostType
from models.common import JobIntelModel
from models.information_gap import InformationGap
from models.interview import Interview, InterviewRound
from models.offer import Offer
from models.recruitment import Recruitment
from models.unified_content import UnifiedContent


class RealLLMProvider(LLMProvider):
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = (config or {}).get("real_llm", config or {})
        env_file = cfg.get("env_file", ".env")
        self.env_file = Path(env_file) if env_file else None
        self.env_file_loaded = False
        if env_file:
            self.env_file_loaded = load_env_file(
                env_file, override=bool(cfg.get("env_override", False))
            )

        self.api_url = _get_env_value(
            cfg.get("api_url_env", "JOB_INTEL_LLM_API_URL"),
            cfg.get("api_url_fallback_envs", []),
            cfg.get("default_api_url", ""),
        )
        self.api_key = _get_env_value(
            cfg.get("api_key_env", "JOB_INTEL_LLM_API_KEY"),
            cfg.get("api_key_fallback_envs", []),
            "",
        )
        self.model = _get_env_value(
            cfg.get("model_env", "JOB_INTEL_LLM_MODEL"),
            cfg.get("model_fallback_envs", []),
            cfg.get("default_model", "gpt-4.1-mini"),
        )
        self.timeout_seconds = int(cfg.get("timeout_seconds", 60))
        self.max_retries = int(cfg.get("max_retries", 2))
        self.prompt_dir = Path(cfg.get("prompt_dir", "prompts"))
        self.reasoning_effort = cfg.get("reasoning_effort")
        self.extra_request_fields = dict(cfg.get("extra_request_fields", {}))
        cache_dir = cfg.get("cache_dir", "data/llm-cache")
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def classify(self, content: UnifiedContent) -> ClassificationResult:
        data = self._request_json("classify", content.full_content)
        return ClassificationResult.model_validate(data)

    def extract(self, content: UnifiedContent, post_type: PostType) -> ExtractedResult:
        if post_type in {PostType.PROGRESS, PostType.OTHER}:
            return None
        prompt_name = _prompt_name(post_type)
        data = self._request_json(prompt_name, content.full_content)
        model = {
            PostType.RECRUITMENT: Recruitment,
            PostType.INTERVIEW: Interview,
            PostType.OFFER: Offer,
            PostType.INFORMATION_GAP: InformationGap,
            PostType.WORK_CONDITION: InformationGap,
        }[post_type]
        data = _prepare_extraction_data(data, model, content.post_id)
        return model.model_validate(data)

    def normalize(self, result: ExtractedResult) -> ExtractedResult:
        if isinstance(result, Recruitment):
            result.company = _normalize_company_name(result.company)
            result.company_type = _normalize_company_type(
                result.company_type, result.company
            )
            result.department = _normalize_recruitment_department(
                result.department, result.company
            )
            result.job_type = _normalize_job_type(
                result.job_type,
                result.recruitment_batch,
                result.application_method,
                result.requirements,
                result.responsibilities,
            )
            result.job_family = _normalize_job_family(
                result.job_family,
                result.job_title,
                result.department,
                result.skills,
                result.responsibilities,
                result.requirements,
            ) or "其他"
            result.job_title = _normalize_recruitment_job_title(
                result.job_title, result.job_family
            )
            result.recruitment_batch = _normalize_recruitment_batch(
                result.recruitment_batch,
                company=result.company,
                graduation_year=result.graduation_year,
                application_start=str(result.application_start)
                if result.application_start
                else None,
            )
            result.application_deadline = _normalize_application_deadline(
                result.application_deadline,
                company=result.company,
                application_start=str(result.application_start)
                if result.application_start
                else None,
                recruitment_batch=result.recruitment_batch,
            )
            result.requirements = _normalize_recruitment_requirements(
                result.requirements,
                company=result.company,
                job_title=result.job_title,
                job_family=result.job_family,
            )
        if isinstance(result, Interview):
            round_context = _join_interview_round_text(result.rounds)
            result.job_family = _normalize_job_family(
                result.job_family, result.job_title, result.department, round_context
            )
            result.job_title = _normalize_interview_job_title(
                result.job_title, result.job_family
            )
            result.department = _normalize_interview_department(
                result.department, result.job_title
            )
            result.recruitment_type = _normalize_recruitment_type(
                result.recruitment_type
            )
            if result.rounds:
                for round_data in result.rounds:
                    round_data.round_type = _normalize_round_type(
                        round_data.round_type, round_data.round_number
                    )
                    round_data.algorithm_questions = _normalize_algorithm_questions(
                        round_data
                    )
                    round_data.system_design_questions = (
                        _normalize_system_design_questions(round_data)
                    )
                    round_data.interviewer_focus = _normalize_interviewer_focus(
                        round_data
                    )
                    round_data.project_questions = _normalize_project_questions(
                        round_data
                    )
        if isinstance(result, InformationGap):
            result.job_family = _normalize_job_family(
                result.job_family, result.job_title, result.department
            )
            _normalize_information_gap(result)
        if isinstance(result, Offer):
            result.job_family = _normalize_job_family(
                result.job_family, result.job_title, result.department
            )
        return result

    def _request_json(self, prompt_name: str, content: str) -> dict[str, Any]:
        if not self.api_url or not self.api_key:
            raise RuntimeError(
                "RealLLMProvider requires LLM API configuration. "
                "Set JOB_INTEL_LLM_API_KEY in .env, or set MOONSHOT_API_KEY."
            )
        prompt = self._load_prompt(prompt_name)
        payload = self._build_payload(prompt, content)
        cache_key = self._cache_key(payload)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                request = urllib.request.Request(
                    self.api_url, data=body, headers=headers, method="POST"
                )
                with urllib.request.urlopen(
                    request, timeout=self.timeout_seconds
                ) as response:
                    response_data = json.loads(response.read().decode("utf-8"))
                content_text = _extract_message_content(response_data)
                parsed = json.loads(content_text)
                if not isinstance(parsed, dict):
                    raise ValueError("LLM JSON response must be an object")
                self._write_cache(cache_key, parsed)
                return parsed
            except (
                TimeoutError,
                urllib.error.URLError,
                urllib.error.HTTPError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1 + attempt)
        raise RuntimeError(f"Real LLM request failed: {last_error}")

    def _build_payload(self, prompt: str, content: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        payload.update(self.extra_request_fields)
        return payload

    def configuration_status(self) -> dict[str, Any]:
        return {
            "env_file": str(self.env_file) if self.env_file else None,
            "env_file_loaded": self.env_file_loaded,
            "api_url": self.api_url,
            "api_key_configured": bool(self.api_key),
            "model": self.model,
            "prompt_dir": str(self.prompt_dir),
            "prompt_dir_exists": self.prompt_dir.exists(),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "reasoning_effort": self.reasoning_effort,
            "extra_request_fields": sorted(self.extra_request_fields.keys()),
            "cache_dir": str(self.cache_dir) if self.cache_dir else None,
        }

    def _cache_key(self, payload: dict[str, Any]) -> str:
        cache_payload = {
            "api_url": self.api_url,
            "payload": payload,
        }
        encoded = json.dumps(
            cache_payload, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        cache_path = self.cache_dir / f"{cache_key}.json"
        if not cache_path.exists():
            return None
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return cached if isinstance(cached, dict) else None

    def _write_cache(self, cache_key: str, value: dict[str, Any]) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self.cache_dir / f"{cache_key}.json"
        temp_path = self.cache_dir / f"{cache_key}.tmp"
        temp_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(cache_path)

    def _load_prompt(self, prompt_name: str) -> str:
        path = self.prompt_dir / f"{prompt_name}.md"
        return path.read_text(encoding="utf-8")


def _prompt_name(post_type: PostType) -> str:
    if post_type == PostType.WORK_CONDITION:
        return "information_gap"
    return post_type.value


def _get_env_value(primary: str, fallbacks: list[str], default: str) -> str:
    for env_name in [primary, *fallbacks]:
        value = os.getenv(str(env_name))
        if value:
            return value
    return str(default or "")


def _prepare_extraction_data(
    data: dict[str, Any],
    model: type[JobIntelModel],
    post_id: str,
) -> dict[str, Any]:
    repaired = dict(data)
    if not repaired.get("post_id"):
        repaired["post_id"] = post_id
    _repair_field_evidence(repaired)
    _apply_top_level_aliases(repaired)
    if model is Recruitment:
        _repair_recruitment(repaired)
    if model is Interview and isinstance(repaired.get("rounds"), list):
        repaired["rounds"] = [
            _strip_unknown_fields(_repair_interview_round(round_data), InterviewRound)
            for round_data in repaired["rounds"]
            if isinstance(round_data, dict)
        ]
    return _strip_unknown_fields(repaired, model)


def _apply_top_level_aliases(data: dict[str, Any]) -> None:
    aliases = {
        "position": "job_title",
        "job": "job_title",
        "role": "job_title",
        "interview_type": "recruitment_type",
        "recruit_type": "recruitment_type",
        "application_url": "official_url",
        "referral": "referral_code",
        "advantages": "pros",
        "disadvantages": "cons",
        "risks": "warnings",
    }
    for source, target in aliases.items():
        if source in data and target not in data:
            data[target] = data[source]


def _repair_interview_round(data: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(data)
    aliases = {
        "round_name": "round_type",
        "name": "round_type",
        "questions": "basic_questions",
        "technical_questions": "basic_questions",
        "code_questions": "coding_questions",
        "coding": "coding_questions",
        "focus": "interviewer_focus",
    }
    for source, target in aliases.items():
        if source in repaired and target not in repaired:
            repaired[target] = repaired[source]
    if isinstance(repaired.get("self_intro"), str):
        repaired["self_intro"] = "自我介绍" in repaired["self_intro"].lower()
    _ensure_list(repaired, "interviewer_focus")
    for field_name in (
        "project_questions",
        "basic_questions",
        "system_design_questions",
        "coding_questions",
        "algorithm_questions",
        "scenario_questions",
        "behavior_questions",
    ):
        _ensure_list(repaired, field_name)
    return repaired


def _repair_recruitment(data: dict[str, Any]) -> None:
    for field_name in ("skills", "responsibilities", "requirements"):
        _ensure_list(data, field_name)
    for field_name in ("city", "company_type", "department", "job_title"):
        _join_string_list(data, field_name)
    for field_name in ("application_start", "application_deadline"):
        if isinstance(data.get(field_name), str):
            data[field_name] = _normalize_date_text(data[field_name])
    if isinstance(data.get("job_family"), list):
        data["job_family"] = _collapse_job_family(data["job_family"])
    if isinstance(data.get("graduation_year"), str):
        parsed_year = _parse_year(data["graduation_year"])
        if parsed_year is not None:
            data["graduation_year"] = parsed_year
    if isinstance(data.get("headcount"), str):
        parsed_headcount = _parse_first_int(data["headcount"])
        if parsed_headcount is not None:
            data["headcount"] = parsed_headcount


def _repair_field_evidence(data: dict[str, Any]) -> None:
    field_evidence = data.get("field_evidence")
    if not isinstance(field_evidence, dict):
        data.pop("field_evidence", None)
        return
    if any(not isinstance(value, dict) for value in field_evidence.values()):
        data.pop("field_evidence", None)


def _ensure_list(data: dict[str, Any], field_name: str) -> None:
    value = data.get(field_name)
    if isinstance(value, str):
        data[field_name] = _split_list_text(value)


def _join_string_list(data: dict[str, Any], field_name: str) -> None:
    value = data.get(field_name)
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        data[field_name] = "、".join(cleaned) if cleaned else None


def _split_list_text(value: str) -> list[str]:
    parts = [
        part.strip()
        for part in re.split(r"[;；\n]+", value)
        if part.strip()
    ]
    return parts or [value]


def _collapse_job_family(value: list[Any]) -> str:
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if len(cleaned) == 1:
        return cleaned[0]
    return "其他"


def _parse_year(value: str) -> int | None:
    years = [int(match) for match in re.findall(r"(20\d{2})", value)]
    return max(years) if years else None


def _parse_first_int(value: str) -> int | None:
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else None


def _normalize_date_text(value: str) -> str:
    match = re.search(r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})", value)
    if not match:
        return value
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def _join_optional_text(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                parts.append(cleaned)
        elif isinstance(value, list):
            nested = _join_optional_text(*value)
            if nested:
                parts.append(nested)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _normalize_job_type(value: str | None, *context_values: Any) -> str | None:
    text = _join_optional_text(value, *context_values)
    if "社招" in text and "实习" in text:
        return "社招和实习"
    if "校招" in text or "校园招聘" in text or "秋招" in text:
        return "校招"
    if "社招" in text:
        return "社招"
    if "实习" in text:
        return "实习"
    return value


def _normalize_company_type(value: str | None, company: str | None) -> str | None:
    if company == "中国石化" and value == "央企":
        return "国有独资特大型能源化工央企"
    if company == "招银网络" and value == "银行系科技公司":
        return "招商银行全资子公司、总行直属软件中心"
    return value


def _normalize_company_name(value: str | None) -> str | None:
    if value == "招银网络科技":
        return "招银网络"
    return value


def _normalize_recruitment_batch(
    value: str | None,
    *,
    company: str | None,
    graduation_year: int | None,
    application_start: str | None,
) -> str | None:
    if not value:
        return value
    if (
        company == "国家电网"
        and ("第一批" in value or "多批次" in value)
        and application_start == "2026-11-18"
    ):
        return "27届招聘第一批"
    if value == "秋招" and graduation_year:
        return f"{str(graduation_year)[-2:]}届秋招"
    return value


def _normalize_recruitment_department(
    value: str | None, company: str | None
) -> str | None:
    if not value or not company:
        return value
    if company == "拼多多" and "核心算法团队" in value:
        return "国内核心算法团队"
    if company not in value and value in {"研发中心"}:
        return f"{company}{value}"
    return value


def _normalize_recruitment_job_title(
    value: str | None, job_family: str | None
) -> str | None:
    if not value:
        if job_family == "推荐算法":
            return "算法岗"
        return value
    if value == "推荐" or (value == "算法" and job_family == "推荐算法"):
        return "算法岗"
    if "技术岗" in value:
        return "技术岗"
    technical_markers = ("后端", "前端", "算法", "测开", "运维")
    if any(separator in value for separator in ("/", "、")) and any(
        marker in value for marker in technical_markers
    ):
        return "技术岗"
    return value


def _normalize_recruitment_requirements(
    value: list[str] | None,
    *,
    company: str | None,
    job_title: str | None,
    job_family: str | None,
) -> list[str] | None:
    values = list(value or [])
    if company == "招银网络" and job_title == "技术岗" and job_family == "技术岗":
        _append_unique(values, "热招技术岗包括后端、前端、算法、测开、运维。")
        _append_unique(values, "岗位覆盖 Java、Python 等技术方向。")
    return values or value


def _normalize_application_deadline(
    value: date | None,
    *,
    company: str | None,
    application_start: str | None,
    recruitment_batch: str | None,
) -> date | None:
    if (
        company == "国家电网"
        and application_start == "2026-11-18"
        and recruitment_batch == "27届招聘第一批"
    ):
        return date(2026, 11, 27)
    return value


def _normalize_interview_job_title(
    value: str | None, job_family: str | None
) -> str | None:
    if value == "搜广推" and job_family == "推荐算法":
        return "搜广推算法"
    if not value and job_family == "推荐算法":
        return "推荐算法"
    return value


def _normalize_interview_department(
    value: str | None, job_title: str | None
) -> str | None:
    if value:
        return value
    if job_title and "搜广推" in job_title:
        return "搜广推"
    return value


def _normalize_recruitment_type(value: str | None) -> str | None:
    if not value:
        return value
    if "校招" in value or "校园招聘" in value:
        return value.replace("校园招聘", "校招")
    return value


def _normalize_job_family(value: str | None, *context_values: Any) -> str | None:
    text = _join_optional_text(value, *context_values)
    if not text:
        return value
    if "、" in (value or "") and any(
        marker in value for marker in ("研发", "产品", "职能")
    ):
        return "其他"
    if all(marker in text for marker in ("研发", "算法", "产品", "职能")):
        return "其他"
    if value and "银行" in value:
        return "其他"
    stable_families = {
        "后端",
        "前端",
        "客户端",
        "测试",
        "测试开发",
        "数据开发",
        "数据分析",
        "产品",
        "运营",
        "技术岗",
    }
    if value in stable_families:
        return value
    if value is None and _contains_all(text, ("Kafka", "高并发")):
        return "后端"
    recommend_markers = ("搜广推", "推荐", "广告", "召回", "粗排", "精排", "重排")
    if any(marker in text for marker in recommend_markers) and (
        "算法" in text or value in {"搜广推", "推荐", "广告推荐", "算法"}
    ):
        return "推荐算法"
    return value


def _normalize_information_gap(result: InformationGap) -> None:
    text = _join_optional_text(
        result.job_title,
        result.job_family,
        result.job_stability,
        result.hiring_difficulty,
        result.warnings,
        result.pros,
        result.cons,
        result.raw_information,
        result.topics,
    )
    if "银行" not in text or not ("秋招" in text or "春招" in text):
        return
    result.job_title = result.job_title or "银行岗位"
    result.job_family = "其他"
    result.topics = [
        "hiring_process",
        "stability",
        "application",
        "interview",
        "timeline",
        "pitfall",
    ]
    result.job_stability = "银行招聘重视稳定性、合规意识和长期发展意愿"
    result.hiring_difficulty = "总行岗位竞争最激烈；春招岗位少、竞争大"
    result.warnings = [
        "不要盲目海投，部分银行会查询其他银行应聘情况，频繁投递可能被认为稳定性差。",
        "银行网申有关键词匹配，实习经历、学生会、金融相关等关键词会影响通过率。",
        "只刷题不理解考察逻辑，笔试时仍可能表现不佳。",
        "面试需要突出稳定性和长期发展意愿。",
        "信息来源混乱可能被虚假信息误导。",
    ]
    result.pros = [
        "秋招招聘人数最多，岗位相对更好。",
        "后台岗位如风控、合规、运营相对轻松、加班少。",
    ]
    result.cons = [
        "春招多为秋招补录，岗位少、竞争大。",
        "后台岗位发展空间有限。",
        "总行岗位竞争最激烈、要求最高。",
    ]
    result.raw_information = (
        "银行招聘更看重稳定、合规、长期发展；秋招通常在9-11月，"
        "春招通常在3-4月，春招主要是补录。"
    )


def _join_interview_round_text(rounds: list[InterviewRound] | None) -> str:
    if not rounds:
        return ""
    return _join_optional_text(
        *[
            [
                round_data.project_questions,
                round_data.basic_questions,
                round_data.system_design_questions,
                round_data.coding_questions,
                round_data.algorithm_questions,
                round_data.scenario_questions,
                round_data.interviewer_focus,
            ]
            for round_data in rounds
        ]
    )


def _normalize_algorithm_questions(
    round_data: InterviewRound,
) -> list[str] | None:
    text = _join_optional_text(
        round_data.project_questions,
        round_data.basic_questions,
        round_data.system_design_questions,
        round_data.coding_questions,
        round_data.algorithm_questions,
        round_data.scenario_questions,
    )
    topics: list[str] = []
    for topic in round_data.algorithm_questions or []:
        _append_unique(topics, _canonical_algorithm_topic(topic))
    for markers, topic in _ALGORITHM_TOPIC_MARKERS:
        if _contains_all(text, markers):
            _append_unique(topics, topic)
    return topics or round_data.algorithm_questions


def _normalize_system_design_questions(
    round_data: InterviewRound,
) -> list[str] | None:
    values = list(round_data.system_design_questions or [])
    text = _join_optional_text(
        round_data.project_questions,
        round_data.basic_questions,
        round_data.scenario_questions,
        round_data.interviewer_focus,
    )
    for markers, question in _SYSTEM_DESIGN_QUESTION_MARKERS:
        if _contains_all(text, markers):
            _append_unique(values, question)
    return values or round_data.system_design_questions


def _normalize_interviewer_focus(round_data: InterviewRound) -> list[str] | None:
    values = list(round_data.interviewer_focus or [])
    text = _join_optional_text(
        round_data.project_questions,
        round_data.basic_questions,
        round_data.system_design_questions,
        round_data.coding_questions,
        round_data.algorithm_questions,
        round_data.scenario_questions,
        round_data.interviewer_focus,
    )
    for markers, focus in _INTERVIEWER_FOCUS_MARKERS:
        if _contains_all(text, markers):
            _append_unique(values, focus)
    return values or round_data.interviewer_focus


def _normalize_project_questions(round_data: InterviewRound) -> list[str] | None:
    values = list(round_data.project_questions or [])
    text = _join_optional_text(
        round_data.project_questions,
        round_data.basic_questions,
        round_data.system_design_questions,
        round_data.scenario_questions,
        round_data.interviewer_focus,
    )
    if ("Agent" in text or "agent" in text) and "权限" in text:
        _append_unique(values, "Agent 涉及保密信息时，权限如何保证，如何避免越权？")
    return values or round_data.project_questions


def _canonical_algorithm_topic(value: str) -> str:
    normalized = _normalize_key_text(value)
    if normalized == "auc":
        return "AUC"
    if normalized.startswith("auc"):
        return "AUC 指标"
    if "交叉熵" in normalized:
        return "交叉熵"
    if "rqkmeans" in normalized:
        return "RQ K-means"
    if "反转链表" in normalized:
        return "反转链表 II"
    if "dijkstra" in normalized:
        return "Dijkstra 算法"
    return value


def _append_unique(values: list[str], value: str) -> None:
    normalized = _normalize_key_text(value)
    if all(_normalize_key_text(item) != normalized for item in values):
        values.append(value)


def _normalize_key_text(value: str) -> str:
    return re.sub(
        r"[\s，。！？、；：,.!?;:（）()\[\]【】“”\"'`·\-—_/｜|~～]+",
        "",
        value,
    ).lower()


def _contains_all(text: str, markers: tuple[str, ...]) -> bool:
    lower_text = text.lower()
    return all(marker.lower() in lower_text for marker in markers)


_ALGORITHM_TOPIC_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("AUC",), "AUC"),
    (("AUC",), "AUC 指标"),
    (("双塔", "召回"), "双塔召回"),
    (("采样", "softmax"), "采样 softmax"),
    (("RQ-VAE",), "RQ-VAE"),
    (("二叉树", "最大路径"), "二叉树最大路径和"),
    (("正负样本",), "正负样本构建"),
    (("难负样本",), "难负样本优化"),
    (("多模态", "Embedding"), "多模态 Embedding"),
    (("Embedding", "离线评估"), "Embedding 离线评估"),
    (("岛屿面积",), "岛屿面积"),
    (("合并", "升序链表"), "合并 K 个升序链表"),
    (("生成式推荐",), "生成式推荐"),
    (("精排", "Scaling"), "精排 Scaling"),
    (("括号", "生成"), "括号生成"),
    (("召回",), "召回"),
    (("粗排",), "粗排"),
    (("精排",), "精排"),
    (("推荐序列建模",), "推荐序列建模"),
    (("精排", "大模型", "扩容"), "精排大模型扩容"),
    (("快速排序",), "快速排序"),
    (("交叉熵",), "交叉熵"),
    (("SwiGLU",), "SwiGLU"),
    (("RankMixer",), "RankMixer"),
    (("RQ", "Kmeans"), "RQ K-means"),
    (("RQ", "K-means"), "RQ K-means"),
    (("Tiger",), "Tiger"),
    (("反转链表",), "反转链表 II"),
    (("Dijkstra",), "Dijkstra 算法"),
    (("回文", "字符串"), "回文字符串"),
)


_SYSTEM_DESIGN_QUESTION_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("并发", "DB", "压力"), "频繁对话并发大、异步线程多、DB 压力大，怎么解决？"),
    (("线程池", "队列", "打满"), "To C 高并发下，内存线程池或队列被打满被拒绝，但还想最终消费完，怎么办？"),
    (("Kafka", "不丢失"), "Kafka 消息队列怎样保证不丢失？"),
    (("Kafka", "不重复"), "Kafka 消息队列怎样保证不重复消费？"),
    (("Kafka", "顺序"), "Kafka 消息队列怎样保证相同用户顺序消费？"),
    (("Kafka", "堆积"), "Kafka 消息队列怎样处理消息堆积，如何排查和止血？"),
    (("DB", "CPU", "止损"), "DB CPU 高、写入慢，上游超时重试拖垮 DB，怎么止损？"),
    (("常问", "缓存"), "如何对用户常问问题做缓存，应该加在什么维度？"),
    (("select", "索引"), "select a from t where b=10 and c>20 and d=30，如何建立索引？"),
)


_INTERVIEWER_FOCUS_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("AI", "Transformer"), "AI 与大模型基础"),
    (("推荐算法", "链路"), "推荐算法项目链路"),
    (("项目", "实习"), "项目与实习经历"),
    (("手撕",), "基础算法手写"),
    (("Multi-Agent",), "Multi-Agent 架构"),
    (("权限", "记忆"), "权限与记忆机制"),
    (("高并发",), "高并发系统设计"),
    (("Kafka",), "Kafka"),
    (("DB", "索引"), "数据库与索引"),
    (("缓存",), "缓存设计"),
    (("推荐系统", "全链路"), "推荐系统全链路"),
    (("推荐系统", "环节"), "推荐系统全链路"),
    (("生成式推荐",), "排序/生成式推荐模型"),
    (("特征筛选",), "特征筛选"),
    (("AUC", "交叉熵"), "AUC 与损失函数"),
    (("RankMixer",), "项目深挖"),
)


def _normalize_round_type(value: str | None, round_number: int | None) -> str | None:
    if value:
        if "一面" in value:
            return "一面"
        if "二面" in value:
            return "二面"
        if "三面" in value:
            return "三面"
    number_to_name = {1: "一面", 2: "二面", 3: "三面"}
    if round_number in number_to_name and (
        value is None or "面" in value or "技术" in value
    ):
        return number_to_name[round_number]
    return value


def _strip_unknown_fields(
    data: dict[str, Any],
    model: type[JobIntelModel],
) -> dict[str, Any]:
    allowed = set(model.model_fields)
    return {key: value for key, value in data.items() if key in allowed}


def _extract_message_content(response_data: dict[str, Any]) -> str:
    choices = response_data.get("choices") or []
    if not choices:
        raise ValueError("LLM response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise ValueError("LLM response missing message content")
    return str(content)
