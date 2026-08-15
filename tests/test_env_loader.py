from __future__ import annotations

import os
from pathlib import Path

from env_loader import load_env_file
from llm.real import RealLLMProvider, _prepare_extraction_data
from models.interview import Interview
from models.recruitment import Recruitment


def test_load_env_file_preserves_existing_environment(
    tmp_path: Path, monkeypatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "JOB_INTEL_LLM_API_KEY=from-file",
                'QUOTED="hello world"',
                "INLINE=value # comment",
                "export EXPORTED=ok",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("JOB_INTEL_LLM_API_KEY", "existing")

    loaded = load_env_file(env_path)

    assert loaded is True
    assert os.environ["JOB_INTEL_LLM_API_KEY"] == "existing"
    assert os.environ["QUOTED"] == "hello world"
    assert os.environ["INLINE"] == "value"
    assert os.environ["EXPORTED"] == "ok"


def test_real_llm_provider_loads_moonshot_env_aliases(
    tmp_path: Path, monkeypatch
) -> None:
    for env_name in (
        "JOB_INTEL_LLM_API_URL",
        "JOB_INTEL_LLM_API_KEY",
        "JOB_INTEL_LLM_MODEL",
        "MOONSHOT_API_KEY",
        "MOONSHOT_MODEL",
    ):
        monkeypatch.delenv(env_name, raising=False)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "MOONSHOT_API_KEY=moonshot-key",
                "MOONSHOT_MODEL=kimi-k3",
            ]
        ),
        encoding="utf-8",
    )

    provider = RealLLMProvider(
        {
            "env_file": str(env_path),
            "default_api_url": "https://api.moonshot.cn/v1/chat/completions",
            "api_key_fallback_envs": ["MOONSHOT_API_KEY"],
            "model_fallback_envs": ["MOONSHOT_MODEL"],
            "default_model": "kimi-k3",
        }
    )

    assert provider.api_url == "https://api.moonshot.cn/v1/chat/completions"
    assert provider.api_key == "moonshot-key"
    assert provider.model == "kimi-k3"


def test_real_llm_provider_reports_safe_configuration_status(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("JOB_INTEL_LLM_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("JOB_INTEL_LLM_API_KEY=secret-value", encoding="utf-8")

    provider = RealLLMProvider(
        {
            "env_file": str(env_path),
            "default_api_url": "https://api.moonshot.cn/v1/chat/completions",
            "default_model": "kimi-k3",
            "reasoning_effort": "low",
        }
    )
    status = provider.configuration_status()
    payload = provider._build_payload("system", "user")

    assert status["api_key_configured"] is True
    assert "secret-value" not in str(status)
    assert status["model"] == "kimi-k3"
    assert status["reasoning_effort"] == "low"
    assert status["cache_dir"] == "data\\llm-cache" or status["cache_dir"] == "data/llm-cache"
    assert payload["reasoning_effort"] == "low"


def test_prepare_extraction_data_repairs_common_llm_aliases() -> None:
    data = {
        "post_id": None,
        "company": "百度",
        "position": "搜广推",
        "interview_type": "校招",
        "field_evidence": {"company": "bad evidence shape"},
        "source_title": "ignored",
        "rounds": [
            {
                "round_name": "一面",
                "self_intro": "自我介绍",
                "questions": ["自我介绍"],
                "coding": ["合并两个有序数组"],
                "focus": "算法题",
                "notes": "ignored",
            }
        ],
    }

    repaired = _prepare_extraction_data(data, Interview, "interview/001")

    assert repaired == {
        "post_id": "interview/001",
        "company": "百度",
        "job_title": "搜广推",
        "recruitment_type": "校招",
        "rounds": [
            {
                "round_type": "一面",
                "self_intro": True,
                "basic_questions": ["自我介绍"],
                "coding_questions": ["合并两个有序数组"],
                "interviewer_focus": ["算法题"],
            }
        ],
    }
    assert Interview.model_validate(repaired).post_id == "interview/001"


def test_real_llm_provider_normalizes_common_domain_values() -> None:
    provider = RealLLMProvider({"env_file": None})
    recruitment = Recruitment(
        post_id="recruitment/002",
        job_type="校园招聘",
        recruitment_batch="2027校园招聘",
        job_family="研发岗、算法岗、产品岗、职能岗",
    )
    interview = Interview(
        post_id="interview/001",
        job_title="搜广推算法",
        job_family="搜广推",
        recruitment_type="校园招聘",
        rounds=[{"round_number": 1, "round_type": "技术一面"}],
    )

    normalized_recruitment = provider.normalize(recruitment)
    normalized_interview = provider.normalize(interview)

    assert isinstance(normalized_recruitment, Recruitment)
    assert normalized_recruitment.job_type == "校招"
    assert normalized_recruitment.job_family == "其他"
    assert isinstance(normalized_interview, Interview)
    assert normalized_interview.job_family == "推荐算法"
    assert normalized_interview.recruitment_type == "校招"
    assert normalized_interview.rounds
    assert normalized_interview.rounds[0].round_type == "一面"


def test_real_llm_provider_cache_round_trip(tmp_path: Path) -> None:
    provider = RealLLMProvider(
        {
            "env_file": None,
            "cache_dir": str(tmp_path / "cache"),
            "default_api_url": "https://api.moonshot.cn/v1/chat/completions",
        }
    )
    payload = provider._build_payload("system", "user")
    cache_key = provider._cache_key(payload)
    expected = {"company": "Shopee"}

    assert provider._read_cache(cache_key) is None
    provider._write_cache(cache_key, expected)

    assert provider._read_cache(cache_key) == expected
