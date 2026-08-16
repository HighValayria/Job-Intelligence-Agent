from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QQEventContext:
    content: str
    target_type: str
    target_id: str
    sender_openid: str | None = None
    msg_id: str | None = None
    event_type: str | None = None


def parse_qq_event(payload: dict[str, Any]) -> QQEventContext | None:
    data = payload.get("d") if isinstance(payload.get("d"), dict) else payload
    if not isinstance(data, dict):
        return None

    event_type = _string(
        payload.get("t")
        or payload.get("event_type")
        or payload.get("eventType")
        or data.get("event_type")
        or data.get("eventType")
    )
    content = _clean_content(
        _string(data.get("content") or data.get("text") or data.get("message"))
    )
    if not content:
        return None

    group_openid = _string(
        data.get("group_openid")
        or data.get("group_id")
        or _nested(data, "group", "openid")
        or _nested(data, "group", "id")
        or _nested(data, "msg", "group_openid")
        or _nested(data, "msg", "group_id")
    )
    user_openid = _string(
        data.get("user_openid")
        or data.get("openid")
        or _nested(data, "author", "user_openid")
        or _nested(data, "author", "openid")
        or _nested(data, "user", "openid")
        or _nested(data, "msg", "author", "user_openid")
        or _nested(data, "msg", "author", "openid")
    )
    msg_id = _string(data.get("id") or data.get("msg_id") or data.get("message_id"))

    if group_openid:
        return QQEventContext(
            content=content,
            target_type="group",
            target_id=group_openid,
            sender_openid=user_openid,
            msg_id=msg_id,
            event_type=event_type,
        )
    if user_openid:
        return QQEventContext(
            content=content,
            target_type="user",
            target_id=user_openid,
            sender_openid=user_openid,
            msg_id=msg_id,
            event_type=event_type,
        )
    return None


def _clean_content(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"<@![^>]+>", " ", value)
    cleaned = re.sub(r"<@[^>]+>", " ", cleaned)
    cleaned = re.sub(r"@\S+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _nested(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
