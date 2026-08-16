from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from algorithm_push.models.push import PushResult, PushStatus
from algorithm_push.push.adapters import PushAdapter
from algorithm_push.push.config import QQBotConfig


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    body: str


@dataclass(frozen=True)
class QQBotCheckResult:
    ok: bool
    auth_mode: str
    endpoint: str | None
    token_checked: bool
    warnings: list[str]
    error: str | None = None


HttpTransport = Callable[
    [str, str, dict[str, str], dict[str, Any], float],
    HttpResponse,
]


class QQBotAdapter(PushAdapter):
    def __init__(
        self,
        config: QQBotConfig,
        *,
        transport: HttpTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or _urllib_transport
        self._cached_access_token = config.access_token
        self._token_expires_at: datetime | None = None
        self._validate_config()

    def send_daily_questions(self, message: str) -> PushResult:
        return self.send_text(
            target_type=self.config.target_type,
            target_id=self.config.target_id or "",
            message=message,
        )

    def send_text(
        self,
        *,
        target_type: str,
        target_id: str,
        message: str,
        msg_id: str | None = None,
        msg_seq: int = 1,
    ) -> PushResult:
        try:
            token = self._access_token()
            endpoint = self._message_endpoint_for(target_type, target_id)
            payload: dict[str, Any] = {
                "msg_type": self.config.msg_type,
                "content": message,
            }
            if msg_id:
                payload["msg_id"] = msg_id
                payload["msg_seq"] = msg_seq
            response = self.transport(
                "POST",
                endpoint,
                {
                    "Content-Type": "application/json",
                    "Authorization": f"QQBot {token}",
                },
                payload,
                self.config.timeout_seconds,
            )
            if 200 <= response.status_code < 300:
                return PushResult(
                    status=PushStatus.SENT,
                    message=f"qq bot message accepted: {response.status_code}",
                    pushed_at=datetime.now(timezone.utc),
                )
            return PushResult(
                status=PushStatus.FAILED,
                error=f"qq bot send failed: {response.status_code} {response.body}",
            )
        except Exception as exc:
            return PushResult(status=PushStatus.FAILED, error=str(exc))

    def check(self, *, fetch_token: bool = True) -> QQBotCheckResult:
        warnings: list[str] = []
        try:
            endpoint = self._message_endpoint()
            if self.config.target_type == "group" and self.config.target_id:
                if self.config.target_id.isdigit():
                    warnings.append(
                        "QQ_BOT_TARGET_ID looks numeric; group sends require the group openid, "
                        "not the visible QQ group number."
                    )
            auth_mode = self._auth_mode()
            token_checked = False
            if fetch_token and auth_mode == "app_credentials":
                self._access_token()
                token_checked = True
            elif fetch_token and auth_mode == "access_token":
                token_checked = bool(self._access_token())
            return QQBotCheckResult(
                ok=True,
                auth_mode=auth_mode,
                endpoint=endpoint,
                token_checked=token_checked,
                warnings=warnings,
            )
        except Exception as exc:
            return QQBotCheckResult(
                ok=False,
                auth_mode=self._auth_mode(),
                endpoint=None,
                token_checked=False,
                warnings=warnings,
                error=str(exc),
            )

    def _access_token(self) -> str:
        if self._cached_access_token and (
            self._token_expires_at is None
            or datetime.now(timezone.utc) < self._token_expires_at
        ):
            return self._cached_access_token
        if not self.config.app_id or not self.config.client_secret:
            raise ValueError(
                "QQ bot requires QQ_BOT_ACCESS_TOKEN or QQ_BOT_APP_ID + QQ_BOT_CLIENT_SECRET"
            )
        response = self.transport(
            "POST",
            self.config.token_url,
            {"Content-Type": "application/json"},
            {
                "appId": self.config.app_id,
                "clientSecret": self.config.client_secret,
            },
            self.config.timeout_seconds,
        )
        if not 200 <= response.status_code < 300:
            raise ValueError(
                f"qq bot token request failed: {response.status_code} {response.body}"
            )
        payload = json.loads(response.body or "{}")
        token = payload.get("access_token")
        if not token:
            raise ValueError(f"qq bot token response missing access_token: {response.body}")
        expires_in = int(payload.get("expires_in") or 7200)
        self._cached_access_token = str(token)
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(expires_in - 60, 1)
        )
        return self._cached_access_token

    def _message_endpoint(self) -> str:
        return self._message_endpoint_for(
            self.config.target_type,
            self.config.target_id or "",
        )

    def _message_endpoint_for(self, target_type: str, target_id: str) -> str:
        base_url = self.config.base_url.rstrip("/")
        if target_type == "group":
            return f"{base_url}/v2/groups/{target_id}/messages"
        if target_type == "user":
            return f"{base_url}/v2/users/{target_id}/messages"
        if target_type == "channel":
            return f"{base_url}/channels/{target_id}/messages"
        raise ValueError(f"unsupported QQ bot target_type: {target_type}")

    def _validate_config(self) -> None:
        if self.config.target_type not in {"group", "user", "channel"}:
            raise ValueError(f"unsupported QQ bot target_type: {self.config.target_type}")
        if not self.config.target_id:
            raise ValueError("QQ bot requires QQ_BOT_TARGET_ID")

    def _auth_mode(self) -> str:
        if self.config.access_token:
            return "access_token"
        if self.config.app_id and self.config.client_secret:
            return "app_credentials"
        return "missing"


def _urllib_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> HttpResponse:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                status_code=response.status,
                body=response.read().decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as exc:
        return HttpResponse(
            status_code=exc.code,
            body=exc.read().decode("utf-8", errors="replace"),
        )
