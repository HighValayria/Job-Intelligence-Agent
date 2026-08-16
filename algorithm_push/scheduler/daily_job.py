from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from algorithm_push.models.push import PushStatus
from algorithm_push.push import (
    ConsoleAdapter,
    PushAdapter,
    PushService,
    QQBotAdapter,
    load_qq_bot_config,
)
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector import DailySelector
from algorithm_push.selector.config import SelectionConfig


class SchedulerRunStatus(StrEnum):
    SKIPPED_DISABLED = "skipped_disabled"
    SKIPPED_NOT_DUE = "skipped_not_due"
    SKIPPED_ALREADY_SENT = "skipped_already_sent"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True)
class SchedulerConfig:
    push_enabled: bool = False
    push_time: time = time(9, 0)
    timezone: str = "Asia/Shanghai"
    adapter: str = "console"


@dataclass(frozen=True)
class SchedulerRunResult:
    status: SchedulerRunStatus
    selection_date: str
    message: str
    push_status: str | None = None


class DailyScheduler:
    def __init__(
        self,
        repository: AlgorithmQuestionRepository,
        *,
        selection_config: SelectionConfig,
        scheduler_config: SchedulerConfig,
        adapter: PushAdapter | None = None,
    ) -> None:
        self.repository = repository
        self.selection_config = selection_config
        self.scheduler_config = scheduler_config
        self.adapter = adapter or _adapter_from_name(scheduler_config.adapter)

    def run_once(
        self,
        *,
        now: datetime | None = None,
        seed: int | None = None,
        force: bool = False,
    ) -> SchedulerRunResult:
        current = _localized_now(now, self.scheduler_config.timezone)
        selection_date = current.date()

        if not force and not self.scheduler_config.push_enabled:
            return SchedulerRunResult(
                status=SchedulerRunStatus.SKIPPED_DISABLED,
                selection_date=selection_date.isoformat(),
                message="push is disabled",
            )
        if not force and current.time() < self.scheduler_config.push_time:
            return SchedulerRunResult(
                status=SchedulerRunStatus.SKIPPED_NOT_DUE,
                selection_date=selection_date.isoformat(),
                message=f"not due until {self.scheduler_config.push_time.strftime('%H:%M')}",
            )
        if (
            not force
            and self.repository.latest_push_status(selection_date) == PushStatus.SENT.value
        ):
            return SchedulerRunResult(
                status=SchedulerRunStatus.SKIPPED_ALREADY_SENT,
                selection_date=selection_date.isoformat(),
                message="selection was already sent",
                push_status=PushStatus.SENT.value,
            )

        selector = DailySelector(self.repository, config=self.selection_config)
        selection = selector.select(
            selection_date,
            seed=seed,
            reuse_existing=True,
            persist=True,
        )
        result = PushService(self.repository, self.adapter).push_existing_selection(
            selection.selection_date
        )
        return SchedulerRunResult(
            status=SchedulerRunStatus.SENT if result.ok else SchedulerRunStatus.FAILED,
            selection_date=selection.selection_date.isoformat(),
            message=result.message or result.error or "",
            push_status=result.status.value,
        )


def load_scheduler_config(path: Path | str | None = None) -> SchedulerConfig:
    payload = _load_yaml(Path(path)) if path is not None and Path(path).exists() else {}
    push = payload.get("push", {})
    enabled = _env_bool("PUSH_ENABLED", push.get("enabled", False))
    push_time = _env_value("PUSH_TIME", push.get("time", "09:00"))
    timezone = _env_value("TIMEZONE", push.get("timezone", "Asia/Shanghai"))
    adapter = _env_value("PUSH_ADAPTER", push.get("adapter", "console"))
    return SchedulerConfig(
        push_enabled=enabled,
        push_time=_parse_time(str(push_time)),
        timezone=str(timezone),
        adapter=str(adapter),
    )


def _adapter_from_name(name: str) -> PushAdapter:
    if name == "console":
        return ConsoleAdapter()
    if name == "qq":
        return QQBotAdapter(load_qq_bot_config())
    raise ValueError(f"unsupported push adapter: {name}")


def _localized_now(now: datetime | None, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def _parse_time(value: str) -> time:
    hour, separator, minute = value.partition(":")
    if not separator:
        raise ValueError(f"invalid push time: {value}")
    return time(int(hour), int(minute))


def _env_value(name: str, default: Any) -> Any:
    return os.environ.get(name, os.environ.get(f"ALGORITHM_{name}", default))


def _env_bool(name: str, default: Any) -> bool:
    value = _env_value(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        return _load_simple_config_yaml(text)
    return yaml.safe_load(text) or {}


def _load_simple_config_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()
        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            current_section = {}
            result[section] = current_section
            continue
        if current_section is None or ":" not in stripped:
            continue
        key, _, raw_value = stripped.partition(":")
        current_section[key.strip()] = _parse_scalar(raw_value.strip())
    return result


def _parse_scalar(value: str) -> Any:
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value in {"true", "false"}:
        return value == "true"
    return value
