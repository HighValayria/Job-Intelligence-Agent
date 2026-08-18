from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from algorithm_push.models import PushResult, PushStatus, QuestionInput, QuestionPool
from algorithm_push.push import QQBotAdapter, QQBotConfig
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.entertainment import MemeImage
from algorithm_push.webhook import handle_qq_event, parse_qq_event
import algorithm_push.webhook.handler as webhook_handler


class CapturingQQAdapter(QQBotAdapter):
    def __init__(self) -> None:
        super().__init__(
            QQBotConfig(access_token="token", target_type="group", target_id="fallback")
        )
        self.sent: list[dict[str, object]] = []

    def send_text(
        self,
        *,
        target_type: str,
        target_id: str,
        message: str,
        msg_id: str | None = None,
        msg_seq: int = 1,
    ) -> PushResult:
        self.sent.append(
            {
                "target_type": target_type,
                "target_id": target_id,
                "message": message,
                "msg_id": msg_id,
                "msg_seq": msg_seq,
            }
        )
        return PushResult(status=PushStatus.SENT, message="captured")


def test_parse_group_event_context() -> None:
    context = parse_qq_event(
        {
            "t": "GROUP_AT_MESSAGE_CREATE",
            "d": {
                "id": "msg-1",
                "content": "<@!bot> 帮助",
                "group_openid": "group-openid-1",
                "author": {"user_openid": "user-openid-1"},
            },
        }
    )

    assert context is not None
    assert context.content == "帮助"
    assert context.target_type == "group"
    assert context.target_id == "group-openid-1"
    assert context.sender_openid == "user-openid-1"
    assert context.msg_id == "msg-1"


def test_webhook_help_replies_to_group(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        adapter = CapturingQQAdapter()

        result = handle_qq_event(
            {
                "d": {
                    "id": "msg-1",
                    "content": "帮助",
                    "group_openid": "group-openid-1",
                    "author": {"user_openid": "user-openid-1"},
                }
            },
            repository=repository,
            adapter=adapter,
        )

        assert result.handled is True
        assert "今日算法" in (result.reply_text or "")
        assert adapter.sent[0]["target_id"] == "group-openid-1"
        assert adapter.sent[0]["msg_id"] == "msg-1"


def test_webhook_today_creates_selection_and_replies(tmp_path: Path) -> None:
    with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
        repository.initialize()
        _seed_questions(repository)
        adapter = CapturingQQAdapter()

        result = handle_qq_event(
            {
                "d": {
                    "content": "今日算法",
                    "group_openid": "group-openid-1",
                    "author": {"user_openid": "admin-openid"},
                }
            },
            repository=repository,
            adapter=adapter,
            today=date(2026, 8, 16),
        )

        assert result.handled is True
        assert "2026-08-16" in (result.reply_text or "")
        assert repository.count_rows("daily_selections") == 5


def test_webhook_add_question_requires_admin(tmp_path: Path) -> None:
    previous = os.environ.get("QQ_BOT_ADMIN_OPENIDS")
    try:
        os.environ["QQ_BOT_ADMIN_OPENIDS"] = "admin-openid"
        with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
            repository.initialize()
            adapter = CapturingQQAdapter()

            result = handle_qq_event(
                {
                    "d": {
                        "content": (
                            "加题 interview_manual https://example.test/design "
                            "design System Design"
                        ),
                        "group_openid": "group-openid-1",
                        "author": {"user_openid": "admin-openid"},
                    }
                },
                repository=repository,
                adapter=adapter,
            )

            assert "已添加题目" in (result.reply_text or "")
            assert len(repository.list_questions(pool=QuestionPool.INTERVIEW_MANUAL)) == 1
    finally:
        if previous is None:
            os.environ.pop("QQ_BOT_ADMIN_OPENIDS", None)
        else:
            os.environ["QQ_BOT_ADMIN_OPENIDS"] = previous


def test_webhook_fun_request_replies_with_memes(tmp_path: Path) -> None:
    previous_fetch = webhook_handler.fetch_recent_meme_images

    def fake_fetch_recent_meme_images(**kwargs):
        return [
            MemeImage(
                image_url=f"https://example.test/meme-{index}.jpg",
                thread_url=f"https://tieba.baidu.com/p/{index}",
                title=f"meme {index}",
                post_date=date(2026, 8, 18),
            )
            for index in range(1, 5)
        ]

    try:
        webhook_handler.fetch_recent_meme_images = fake_fetch_recent_meme_images
        with AlgorithmQuestionRepository(tmp_path / "algorithm.sqlite3") as repository:
            repository.initialize()
            adapter = CapturingQQAdapter()

            result = handle_qq_event(
                {
                    "d": {
                        "id": "msg-fun",
                        "content": "<@!bot> 来点乏味",
                        "group_openid": "group-openid-1",
                        "author": {"user_openid": "user-openid-1"},
                    }
                },
                repository=repository,
                adapter=adapter,
            )

            assert result.handled is True
            assert "来点趣味" in (result.reply_text or "")
            assert "https://example.test/meme-4.jpg" in (result.reply_text or "")
            assert adapter.sent[0]["msg_id"] == "msg-fun"
    finally:
        webhook_handler.fetch_recent_meme_images = previous_fetch


def _seed_questions(repository: AlgorithmQuestionRepository) -> None:
    tags = ["array_hash", "linked_list", "binary_tree", "graph", "heap", "design"]
    for index in range(6):
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"leetcode:webhook-{index}",
                title=f"LC Webhook {index}",
                url=f"https://leetcode.cn/problems/webhook-{index}/",
                pool=QuestionPool.LEETCODE_HOT100,
                primary_tag=tags[index % len(tags)],
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"nowcoder:webhook-{index}",
                title=f"NC Webhook {index}",
                url=f"https://www.nowcoder.com/webhook/{index}",
                pool=QuestionPool.NOWCODER_HOT101,
                primary_tag=tags[(index + 2) % len(tags)],
            )
        )
        repository.upsert_question(
            QuestionInput(
                canonical_key=f"interview:webhook-{index}",
                title=f"Interview Webhook {index}",
                url=f"https://example.test/webhook/{index}",
                pool=QuestionPool.INTERVIEW_MANUAL,
                primary_tag=tags[(index + 4) % len(tags)],
            )
        )
