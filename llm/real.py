from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from env_loader import load_env_file
from llm.base import ExtractedResult, LLMProvider
from models.classification import ClassificationResult, PostType
from models.information_gap import InformationGap
from models.interview import Interview
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
        return model.model_validate(data)

    def normalize(self, result: ExtractedResult) -> ExtractedResult:
        return result

    def _request_json(self, prompt_name: str, content: str) -> dict[str, Any]:
        if not self.api_url or not self.api_key:
            raise RuntimeError(
                "RealLLMProvider requires LLM API configuration. "
                "Set JOB_INTEL_LLM_API_KEY in .env, or set MOONSHOT_API_KEY."
            )
        prompt = self._load_prompt(prompt_name)
        payload = self._build_payload(prompt, content)
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
        }

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


def _extract_message_content(response_data: dict[str, Any]) -> str:
    choices = response_data.get("choices") or []
    if not choices:
        raise ValueError("LLM response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise ValueError("LLM response missing message content")
    return str(content)
