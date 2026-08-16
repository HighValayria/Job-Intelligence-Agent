from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from algorithm_push.push import HttpResponse, QQBotAdapter, QQBotConfig, load_qq_bot_config


def test_qq_bot_adapter_fetches_token_and_sends_group_message() -> None:
    calls: list[tuple[str, str, dict[str, str], dict[str, Any], float]] = []

    def transport(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> HttpResponse:
        calls.append((method, url, headers, payload, timeout))
        if url.endswith("/app/getAppAccessToken"):
            return HttpResponse(
                status_code=200,
                body=json.dumps({"access_token": "token-1", "expires_in": 7200}),
            )
        return HttpResponse(status_code=200, body='{"id":"message-1"}')

    adapter = QQBotAdapter(
        QQBotConfig(
            app_id="app-1",
            client_secret="secret-1",
            target_type="group",
            target_id="group-openid-1",
            token_url="https://bots.qq.com/app/getAppAccessToken",
            base_url="https://api.sgroup.qq.com",
        ),
        transport=transport,
    )

    result = adapter.send_daily_questions("hello")

    assert result.ok is True
    assert calls[0][3] == {"appId": "app-1", "clientSecret": "secret-1"}
    assert calls[1][1] == "https://api.sgroup.qq.com/v2/groups/group-openid-1/messages"
    assert calls[1][2]["Authorization"] == "QQBot token-1"
    assert calls[1][3] == {"msg_type": 0, "content": "hello"}


def test_qq_bot_adapter_uses_provided_access_token_without_token_request() -> None:
    calls: list[str] = []

    def transport(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> HttpResponse:
        calls.append(url)
        return HttpResponse(status_code=200, body="{}")

    adapter = QQBotAdapter(
        QQBotConfig(
            access_token="ready-token",
            target_type="user",
            target_id="user-openid-1",
        ),
        transport=transport,
    )

    result = adapter.send_daily_questions("hello")

    assert result.ok is True
    assert calls == ["https://api.sgroup.qq.com/v2/users/user-openid-1/messages"]


def test_qq_bot_adapter_returns_failed_result_on_http_error() -> None:
    def transport(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> HttpResponse:
        return HttpResponse(status_code=401, body="unauthorized")

    adapter = QQBotAdapter(
        QQBotConfig(access_token="bad-token", target_id="group-openid-1"),
        transport=transport,
    )

    result = adapter.send_daily_questions("hello")

    assert result.ok is False
    assert "401" in (result.error or "")


def test_qq_bot_check_can_skip_token_fetch() -> None:
    calls: list[str] = []

    def transport(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> HttpResponse:
        calls.append(url)
        return HttpResponse(status_code=200, body="{}")

    adapter = QQBotAdapter(
        QQBotConfig(
            app_id="app-1",
            client_secret="secret-1",
            target_id="group-openid-1",
        ),
        transport=transport,
    )

    result = adapter.check(fetch_token=False)

    assert result.ok is True
    assert result.auth_mode == "app_credentials"
    assert result.token_checked is False
    assert result.endpoint == "https://api.sgroup.qq.com/v2/groups/group-openid-1/messages"
    assert calls == []


def test_qq_bot_check_fetches_token_when_requested() -> None:
    calls: list[str] = []

    def transport(
        method: str,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: float,
    ) -> HttpResponse:
        calls.append(url)
        return HttpResponse(
            status_code=200,
            body=json.dumps({"access_token": "token-1", "expires_in": 7200}),
        )

    adapter = QQBotAdapter(
        QQBotConfig(
            app_id="app-1",
            client_secret="secret-1",
            target_id="group-openid-1",
        ),
        transport=transport,
    )

    result = adapter.check(fetch_token=True)

    assert result.ok is True
    assert result.token_checked is True
    assert calls == ["https://bots.qq.com/app/getAppAccessToken"]


def test_qq_bot_check_warns_when_group_target_looks_like_visible_group_number() -> None:
    adapter = QQBotAdapter(
        QQBotConfig(access_token="ready-token", target_id="123456789"),
    )

    result = adapter.check(fetch_token=False)

    assert result.ok is True
    assert result.warnings
    assert "group openid" in result.warnings[0]


def test_qq_bot_config_reads_environment_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "algorithm_push.yaml"
    config_path.write_text(
        "\n".join(
            [
                "qq_bot:",
                "  target_type: group",
                "  target_id: from-file",
                "  access_token: from-file-token",
            ]
        ),
        encoding="utf-8",
    )
    previous = {
        "QQ_BOT_TARGET_ID": os.environ.get("QQ_BOT_TARGET_ID"),
        "QQ_BOT_ACCESS_TOKEN": os.environ.get("QQ_BOT_ACCESS_TOKEN"),
    }
    try:
        os.environ["QQ_BOT_TARGET_ID"] = "from-env"
        os.environ["QQ_BOT_ACCESS_TOKEN"] = "from-env-token"

        config = load_qq_bot_config(config_path)

        assert config.target_id == "from-env"
        assert config.access_token == "from-env-token"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
