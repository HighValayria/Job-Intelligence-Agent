from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QQBotConfig:
    app_id: str | None = None
    client_secret: str | None = None
    access_token: str | None = None
    target_type: str = "group"
    target_id: str | None = None
    base_url: str = "https://api.sgroup.qq.com"
    token_url: str = "https://bots.qq.com/app/getAppAccessToken"
    timeout_seconds: float = 10.0
    msg_type: int = 0


def load_qq_bot_config(path: Path | str | None = None) -> QQBotConfig:
    payload = _load_yaml(Path(path)) if path is not None and Path(path).exists() else {}
    qq = payload.get("qq_bot", {})
    return QQBotConfig(
        app_id=_env_value("QQ_BOT_APP_ID", qq.get("app_id")),
        client_secret=_env_value("QQ_BOT_CLIENT_SECRET", qq.get("client_secret")),
        access_token=_env_value("QQ_BOT_ACCESS_TOKEN", qq.get("access_token")),
        target_type=str(_env_value("QQ_BOT_TARGET_TYPE", qq.get("target_type", "group"))),
        target_id=_env_value("QQ_BOT_TARGET_ID", qq.get("target_id")),
        base_url=str(
            _env_value("QQ_BOT_BASE_URL", qq.get("base_url", "https://api.sgroup.qq.com"))
        ),
        token_url=str(
            _env_value(
                "QQ_BOT_TOKEN_URL",
                qq.get("token_url", "https://bots.qq.com/app/getAppAccessToken"),
            )
        ),
        timeout_seconds=float(
            _env_value("QQ_BOT_TIMEOUT_SECONDS", qq.get("timeout_seconds", 10.0))
        ),
        msg_type=int(_env_value("QQ_BOT_MSG_TYPE", qq.get("msg_type", 0))),
    )


def _env_value(name: str, default: Any) -> Any:
    return os.environ.get(name, os.environ.get(f"ALGORITHM_{name}", default))


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        return _load_simple_config_yaml(text)
    return yaml.safe_load(text) or {}


def _load_simple_config_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, result)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        if ":" not in stripped:
            continue
        key, _, raw_value = stripped.partition(":")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value.strip() == "":
            section: dict[str, Any] = {}
            parent[key.strip()] = section
            stack.append((indent, section))
        else:
            parent[key.strip()] = _parse_scalar(raw_value.strip())
    return result


def _parse_scalar(value: str) -> Any:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
