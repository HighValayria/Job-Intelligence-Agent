from __future__ import annotations

import os
from pathlib import Path

from env_loader import load_env_file
from llm.real import RealLLMProvider


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
    assert payload["reasoning_effort"] == "low"
