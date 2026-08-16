from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from algorithm_push.models import PushResult, PushStatus, QuestionInput, QuestionPool
from algorithm_push.push import QQBotAdapter
from algorithm_push.push.formatter import format_daily_questions
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector import DailySelector
from algorithm_push.selector.config import SelectionConfig
from algorithm_push.validation import check_readiness
from algorithm_push.webhook.events import QQEventContext, parse_qq_event


HELP_TEXT = """支持命令：
帮助
今日算法
状态
加题 <pool> <url> <tag> <title>

pool 可选：leetcode_custom, interview_manual"""


@dataclass(frozen=True)
class WebhookResponse:
    handled: bool
    reply_text: str | None = None
    push_result: PushResult | None = None
    error: str | None = None


def handle_qq_event(
    payload: dict[str, object],
    *,
    repository: AlgorithmQuestionRepository,
    adapter: QQBotAdapter,
    selection_config: SelectionConfig | None = None,
    today: date | None = None,
) -> WebhookResponse:
    context = parse_qq_event(payload)
    if context is None:
        return WebhookResponse(handled=False)

    try:
        reply = _reply_for_context(
            context,
            repository=repository,
            selection_config=selection_config or SelectionConfig(),
            today=today or date.today(),
        )
    except Exception as exc:
        reply = f"处理失败：{exc}"

    result = adapter.send_text(
        target_type=context.target_type,
        target_id=context.target_id,
        message=reply,
        msg_id=context.msg_id,
    )
    return WebhookResponse(
        handled=True,
        reply_text=reply,
        push_result=result,
        error=result.error,
    )


def _reply_for_context(
    context: QQEventContext,
    *,
    repository: AlgorithmQuestionRepository,
    selection_config: SelectionConfig,
    today: date,
) -> str:
    content = context.content.strip()
    lowered = content.lower()
    if lowered in {"help", "帮助", "菜单", "命令"}:
        return HELP_TEXT
    if lowered in {"今日算法", "today", "daily", "今日题目"}:
        selection = DailySelector(repository, config=selection_config).select(
            today,
            reuse_existing=True,
            persist=True,
        )
        return format_daily_questions(selection)
    if lowered in {"状态", "status"}:
        readiness = check_readiness(
            repository,
            config=selection_config,
            days=30,
        )
        selection = repository.get_daily_selection(today)
        push_status = repository.latest_push_status(today) or "not_sent"
        return "\n".join(
            [
                "算法推送状态",
                f"date: {today.isoformat()}",
                f"readiness: {'ready' if readiness.ok else 'not_ready'}",
                f"selection: {'created' if selection else 'missing'}",
                f"push: {push_status}",
            ]
        )
    if lowered.startswith("加题 ") or lowered.startswith("add "):
        return _handle_add_question(content, context, repository)
    return HELP_TEXT


def _handle_add_question(
    content: str,
    context: QQEventContext,
    repository: AlgorithmQuestionRepository,
) -> str:
    admins = _admin_openids()
    if not admins:
        return "加题功能未启用：请先在 .env 设置 QQ_BOT_ADMIN_OPENIDS。"
    if not context.sender_openid or context.sender_openid not in admins:
        return "无权限：只有 QQ_BOT_ADMIN_OPENIDS 中的用户可以加题。"

    parts = shlex.split(content)
    if len(parts) < 5:
        return "格式：加题 <pool> <url> <tag> <title>"
    _, pool_text, url, tag, *title_parts = parts
    try:
        pool = QuestionPool(pool_text)
    except ValueError:
        return "pool 不支持。可用：leetcode_custom, interview_manual"
    if pool not in {QuestionPool.LEETCODE_CUSTOM, QuestionPool.INTERVIEW_MANUAL}:
        return "群命令只允许添加到 leetcode_custom 或 interview_manual。"
    title = " ".join(title_parts).strip()
    if not title:
        return "标题不能为空。"

    question = repository.upsert_question(
        QuestionInput(
            title=title,
            url=url,
            pool=pool,
            primary_tag=tag,
            aliases=[title],
        )
    )
    return "\n".join(
        [
            "已添加题目",
            f"pool: {question.pool.value}",
            f"canonical_key: {question.canonical_key}",
            f"title: {question.title}",
        ]
    )


def _admin_openids() -> set[str]:
    raw = os.environ.get("QQ_BOT_ADMIN_OPENIDS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}
