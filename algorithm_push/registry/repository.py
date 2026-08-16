from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from algorithm_push.models import (
    DailySelection,
    InterviewQuestionCandidate,
    Platform,
    Question,
    QuestionInput,
    QuestionPool,
    QuestionStatus,
    PushResult,
    PushStatus,
    SelectionItem,
)
from algorithm_push.registry.canonical import infer_canonical_key, normalize_alias
from algorithm_push.registry.db import initialize_database, open_connection


HOT_POOLS = {QuestionPool.LEETCODE_HOT100, QuestionPool.NOWCODER_HOT101}
INTERVIEW_POOLS = {QuestionPool.INTERVIEW_EXTRACTED, QuestionPool.INTERVIEW_MANUAL}


@dataclass(frozen=True)
class InterviewIngestionResult:
    question_id: str | None
    canonical_key: str
    inserted_or_updated: bool
    duplicate_of_hot_pool: bool
    status: str


class AlgorithmQuestionRepository:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.conn = open_connection(self.db_path)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "AlgorithmQuestionRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def initialize(self) -> None:
        initialize_database(self.conn)

    def upsert_question(self, question: QuestionInput) -> Question:
        item = QuestionInput.model_validate(question)
        platform = item.platform or _platform_for_pool(item.pool)
        canonical_key = infer_canonical_key(
            title=item.title,
            platform=platform.value,
            canonical_key=item.canonical_key,
        )
        now = _now_iso()

        existing = self.conn.execute(
            """
            SELECT question_id, created_at
            FROM questions
            WHERE pool = ? AND canonical_key = ?
            """,
            (item.pool.value, canonical_key),
        ).fetchone()
        question_id = existing["question_id"] if existing else str(uuid4())
        created_at = existing["created_at"] if existing else now

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO questions (
                    question_id, canonical_key, title, url, pool, platform,
                    primary_tag, tags_json, status, enabled, priority,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pool, canonical_key) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    platform = excluded.platform,
                    primary_tag = excluded.primary_tag,
                    tags_json = excluded.tags_json,
                    status = excluded.status,
                    enabled = excluded.enabled,
                    priority = excluded.priority,
                    updated_at = excluded.updated_at
                """,
                (
                    question_id,
                    canonical_key,
                    item.title,
                    item.url,
                    item.pool.value,
                    platform.value,
                    item.primary_tag,
                    _json(item.tags),
                    item.status.value,
                    int(item.enabled),
                    item.priority,
                    created_at,
                    now,
                ),
            )
            for alias in [item.title, *item.aliases]:
                self.add_alias(
                    alias=alias,
                    canonical_key=canonical_key,
                    source=item.pool.value,
                    commit=False,
                )

        return self.get_question(question_id)

    def add_alias(
        self,
        *,
        alias: str,
        canonical_key: str,
        source: str,
        commit: bool = True,
    ) -> None:
        alias = alias.strip()
        if not alias:
            return
        now = _now_iso()
        params = (
            alias,
            normalize_alias(alias),
            canonical_key.strip().lower(),
            source,
            now,
            now,
        )
        if commit:
            with self.conn:
                self._upsert_alias(params)
        else:
            self._upsert_alias(params)

    def find_canonical_key_by_alias(self, alias: str) -> str | None:
        normalized = normalize_alias(alias)
        rows = self.conn.execute(
            """
            SELECT DISTINCT canonical_key
            FROM question_aliases
            WHERE normalized_alias = ?
            """,
            (normalized,),
        ).fetchall()
        if len(rows) == 1:
            return str(rows[0]["canonical_key"])
        return None

    def canonical_has_hot_pool(self, canonical_key: str) -> bool:
        placeholders = ", ".join("?" for _ in HOT_POOLS)
        rows = self.conn.execute(
            f"""
            SELECT 1
            FROM questions
            WHERE canonical_key = ?
              AND pool IN ({placeholders})
            LIMIT 1
            """,
            (canonical_key.strip().lower(), *[pool.value for pool in HOT_POOLS]),
        ).fetchone()
        return rows is not None

    def upsert_interview_question(
        self, candidate: InterviewQuestionCandidate
    ) -> InterviewIngestionResult:
        item = InterviewQuestionCandidate.model_validate(candidate)
        title = (item.normalized_title or item.raw_title).strip()
        matched_key = item.canonical_key or self.find_canonical_key_by_alias(title)
        canonical_key = infer_canonical_key(
            title=title,
            platform=Platform.OTHER.value,
            canonical_key=matched_key,
        )

        duplicate_of_hot = self.canonical_has_hot_pool(canonical_key)
        question_id: str | None = None
        inserted_or_updated = False

        if not duplicate_of_hot:
            question = self.upsert_question(
                QuestionInput(
                    canonical_key=canonical_key,
                    title=title,
                    url=item.url,
                    pool=QuestionPool.INTERVIEW_EXTRACTED,
                    platform=Platform.OTHER,
                    primary_tag=item.primary_tag,
                    tags=item.tags,
                    enabled=item.enabled,
                    priority=item.priority,
                    status=QuestionStatus.ACTIVE if item.url else QuestionStatus.PENDING,
                    aliases=[item.raw_title],
                )
            )
            question_id = question.question_id
            inserted_or_updated = True

        self._record_mention(
            question_id=question_id,
            canonical_key=canonical_key,
            candidate=item,
        )
        return InterviewIngestionResult(
            question_id=question_id,
            canonical_key=canonical_key,
            inserted_or_updated=inserted_or_updated,
            duplicate_of_hot_pool=duplicate_of_hot,
            status="linked_to_hot_pool" if duplicate_of_hot else "saved",
        )

    def get_question(self, question_id: str) -> Question:
        row = self.conn.execute(
            "SELECT * FROM questions WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"question not found: {question_id}")
        return _question_from_row(row)

    def list_questions(
        self,
        *,
        pool: QuestionPool | str | None = None,
        status: QuestionStatus | str | None = None,
        active_only: bool = False,
    ) -> list[Question]:
        clauses: list[str] = []
        params: list[Any] = []
        if pool is not None:
            pool_value = pool.value if isinstance(pool, QuestionPool) else pool
            clauses.append("pool = ?")
            params.append(pool_value)
        if status is not None:
            status_value = status.value if isinstance(status, QuestionStatus) else status
            clauses.append("status = ?")
            params.append(status_value)
        if active_only:
            clauses.append("enabled = 1")
            clauses.append("status = ?")
            params.append(QuestionStatus.ACTIVE.value)
            clauses.append("url IS NOT NULL")
            clauses.append("url != ''")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM questions
            {where}
            ORDER BY pool, canonical_key
            """,
            params,
        ).fetchall()
        return [_question_from_row(row) for row in rows]

    def review_rows(
        self,
        *,
        status: QuestionStatus | str = QuestionStatus.PENDING,
    ) -> list[dict[str, Any]]:
        status_value = status.value if isinstance(status, QuestionStatus) else status
        rows = self.conn.execute(
            """
            SELECT
                q.question_id,
                q.canonical_key,
                q.title,
                q.url,
                q.pool,
                q.platform,
                q.primary_tag,
                q.tags_json,
                q.status,
                q.enabled,
                q.priority,
                COUNT(m.mention_id) AS mention_count,
                MAX(m.source_post_url) AS latest_source_post_url,
                MAX(m.context) AS latest_context
            FROM questions q
            LEFT JOIN question_mentions m ON m.question_id = q.question_id
            WHERE q.status = ?
            GROUP BY q.question_id
            ORDER BY q.updated_at DESC, q.pool, q.title
            """,
            (status_value,),
        ).fetchall()
        return [_review_row_from_row(row) for row in rows]

    def resolve_pending_question(
        self,
        *,
        question_id: str,
        url: str,
        canonical_key: str | None = None,
        title: str | None = None,
        primary_tag: str | None = None,
        tags: list[str] | None = None,
        aliases: list[str] | None = None,
        priority: float | None = None,
    ) -> Question:
        existing = self.get_question(question_id)
        resolved_title = (title or existing.title).strip()
        resolved_canonical_key = (
            canonical_key.strip().lower()
            if canonical_key
            else existing.canonical_key
        )
        resolved_primary_tag = (primary_tag or existing.primary_tag).strip()
        resolved_tags = _normalize_tags(tags if tags is not None else existing.tags)
        if resolved_primary_tag not in resolved_tags:
            resolved_tags.insert(0, resolved_primary_tag)

        with self.conn:
            self.conn.execute(
                """
                UPDATE questions
                SET canonical_key = ?,
                    title = ?,
                    url = ?,
                    primary_tag = ?,
                    tags_json = ?,
                    status = ?,
                    enabled = 1,
                    priority = ?,
                    updated_at = ?
                WHERE question_id = ?
                """,
                (
                    resolved_canonical_key,
                    resolved_title,
                    url.strip(),
                    resolved_primary_tag,
                    _json(resolved_tags),
                    QuestionStatus.ACTIVE.value,
                    priority if priority is not None else existing.priority,
                    _now_iso(),
                    question_id,
                ),
            )
            for alias in [resolved_title, *(aliases or [])]:
                self.add_alias(
                    alias=alias,
                    canonical_key=resolved_canonical_key,
                    source=existing.pool.value,
                    commit=False,
                )
        return self.get_question(question_id)

    def list_active_questions_in_pools(
        self, pools: set[QuestionPool] | list[QuestionPool] | tuple[QuestionPool, ...]
    ) -> list[Question]:
        if not pools:
            return []
        pool_values = [pool.value for pool in pools]
        placeholders = ", ".join("?" for _ in pool_values)
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM questions
            WHERE pool IN ({placeholders})
              AND enabled = 1
              AND status = ?
              AND url IS NOT NULL
              AND url != ''
            ORDER BY pool, canonical_key
            """,
            (*pool_values, QuestionStatus.ACTIVE.value),
        ).fetchall()
        return [_question_from_row(row) for row in rows]

    def get_daily_selection(self, selection_date: date | str) -> DailySelection | None:
        selection_date_text = _date_text(selection_date)
        rows = self.conn.execute(
            """
            SELECT
                ds.selection_date,
                ds.slot,
                ds.selected_score,
                ds.created_at AS selection_created_at,
                q.*
            FROM daily_selections ds
            JOIN questions q ON q.question_id = ds.question_id
            WHERE ds.selection_date = ?
            ORDER BY
                CASE
                    WHEN ds.slot LIKE 'leetcode_%' THEN 1
                    WHEN ds.slot LIKE 'nowcoder_%' THEN 2
                    WHEN ds.slot LIKE 'interview_extra_%' THEN 3
                    ELSE 4
                END,
                ds.slot
            """,
            (selection_date_text,),
        ).fetchall()
        if not rows:
            return None
        items = [
            SelectionItem(
                question=_question_from_selection_row(row),
                slot=row["slot"],
                selected_score=row["selected_score"],
            )
            for row in rows
        ]
        return DailySelection(
            selection_date=date.fromisoformat(selection_date_text),
            items=items,
            created_at=datetime.fromisoformat(rows[0]["selection_created_at"]),
        )

    def save_daily_selection(self, selection: DailySelection) -> None:
        now = _now_iso()
        with self.conn:
            for item in selection.items:
                self.conn.execute(
                    """
                    INSERT INTO daily_selections (
                        selection_date, question_id, slot, pool, selected_score, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        selection.selection_date.isoformat(),
                        item.question.question_id,
                        item.slot,
                        item.question.pool.value,
                        item.selected_score,
                        now,
                    ),
                )

    def last_selected_dates_by_canonical(
        self,
        *,
        before: date,
    ) -> dict[str, date]:
        rows = self.conn.execute(
            """
            SELECT q.canonical_key, MAX(ds.selection_date) AS last_date
            FROM daily_selections ds
            JOIN questions q ON q.question_id = ds.question_id
            WHERE ds.selection_date < ?
            GROUP BY q.canonical_key
            """,
            (before.isoformat(),),
        ).fetchall()
        return {
            row["canonical_key"]: date.fromisoformat(row["last_date"])
            for row in rows
            if row["last_date"]
        }

    def topic_counts(self, *, before: date, days: int) -> dict[str, int]:
        start_date = before - timedelta(days=days)
        rows = self.conn.execute(
            """
            SELECT q.primary_tag, COUNT(*) AS count
            FROM daily_selections ds
            JOIN questions q ON q.question_id = ds.question_id
            WHERE ds.selection_date >= ?
              AND ds.selection_date < ?
            GROUP BY q.primary_tag
            """,
            (start_date.isoformat(), before.isoformat()),
        ).fetchall()
        return {row["primary_tag"]: int(row["count"]) for row in rows}

    def next_push_attempt(self, selection_date: date | str) -> int:
        selection_date_text = _date_text(selection_date)
        row = self.conn.execute(
            """
            SELECT MAX(attempt) AS max_attempt
            FROM push_history
            WHERE selection_date = ?
            """,
            (selection_date_text,),
        ).fetchone()
        return int(row["max_attempt"] or 0) + 1

    def record_push_result(
        self,
        *,
        selection: DailySelection,
        attempt: int,
        result: PushResult,
    ) -> None:
        pushed_at = (
            result.pushed_at.isoformat()
            if result.pushed_at is not None
            else (_now_iso() if result.status == PushStatus.SENT else None)
        )
        with self.conn:
            for item in selection.items:
                self.conn.execute(
                    """
                    INSERT INTO push_history (
                        selection_date, question_id, attempt, push_status,
                        pushed_at, error, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        selection.selection_date.isoformat(),
                        item.question.question_id,
                        attempt,
                        result.status.value,
                        pushed_at,
                        result.error,
                        _now_iso(),
                    ),
                )

    def latest_push_status(self, selection_date: date | str) -> str | None:
        selection_date_text = _date_text(selection_date)
        row = self.conn.execute(
            """
            SELECT push_status
            FROM push_history
            WHERE selection_date = ?
            ORDER BY attempt DESC, id DESC
            LIMIT 1
            """,
            (selection_date_text,),
        ).fetchone()
        return None if row is None else str(row["push_status"])

    def latest_push_error(self, selection_date: date | str) -> str | None:
        selection_date_text = _date_text(selection_date)
        row = self.conn.execute(
            """
            SELECT error
            FROM push_history
            WHERE selection_date = ?
            ORDER BY attempt DESC, id DESC
            LIMIT 1
            """,
            (selection_date_text,),
        ).fetchone()
        return None if row is None else row["error"]

    def recent_push_statuses(self, *, limit: int = 7) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH latest_attempts AS (
                SELECT selection_date, MAX(attempt) AS latest_attempt
                FROM push_history
                GROUP BY selection_date
            )
            SELECT
                ph.selection_date,
                ph.attempt,
                ph.push_status,
                ph.pushed_at,
                ph.error,
                COUNT(ph.question_id) AS question_count,
                MAX(ph.created_at) AS created_at
            FROM push_history ph
            JOIN latest_attempts la
              ON la.selection_date = ph.selection_date
             AND la.latest_attempt = ph.attempt
            GROUP BY ph.selection_date, ph.attempt, ph.push_status, ph.pushed_at, ph.error
            ORDER BY ph.selection_date DESC, ph.attempt DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_rows(self, table: str) -> int:
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"unsupported table: {table}")
        row = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def _upsert_alias(self, params: tuple[str, str, str, str, str, str]) -> None:
        self.conn.execute(
            """
            INSERT INTO question_aliases (
                alias, normalized_alias, canonical_key, source, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_alias, source) DO UPDATE SET
                alias = excluded.alias,
                canonical_key = excluded.canonical_key,
                updated_at = excluded.updated_at
            """,
            params,
        )

    def _record_mention(
        self,
        *,
        question_id: str | None,
        canonical_key: str,
        candidate: InterviewQuestionCandidate,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO question_mentions (
                    question_id, canonical_key, raw_title, normalized_title,
                    source_post_url, company, interview_round, context, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    question_id,
                    canonical_key,
                    candidate.raw_title,
                    candidate.normalized_title,
                    candidate.source_post_url,
                    candidate.company,
                    candidate.interview_round,
                    candidate.context,
                    _now_iso(),
                ),
            )


def _question_from_row(row: sqlite3.Row) -> Question:
    data = dict(row)
    data["tags"] = json.loads(data.pop("tags_json") or "[]")
    data["enabled"] = bool(data["enabled"])
    return Question.model_validate(data)


def _review_row_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["tags"] = json.loads(data.pop("tags_json") or "[]")
    data["enabled"] = bool(data["enabled"])
    data["mention_count"] = int(data["mention_count"] or 0)
    return data


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    for tag in tags:
        stripped = tag.strip()
        if stripped and stripped not in normalized:
            normalized.append(stripped)
    return normalized


def _question_from_selection_row(row: sqlite3.Row) -> Question:
    allowed = {
        "question_id",
        "canonical_key",
        "title",
        "url",
        "pool",
        "platform",
        "primary_tag",
        "tags_json",
        "status",
        "enabled",
        "priority",
        "created_at",
        "updated_at",
    }
    data = {key: row[key] for key in allowed}
    data["tags"] = json.loads(data.pop("tags_json") or "[]")
    data["enabled"] = bool(data["enabled"])
    return Question.model_validate(data)


def _platform_for_pool(pool: QuestionPool) -> Platform:
    if pool in {QuestionPool.LEETCODE_HOT100, QuestionPool.LEETCODE_CUSTOM}:
        return Platform.LEETCODE
    if pool == QuestionPool.NOWCODER_HOT101:
        return Platform.NOWCODER
    return Platform.OTHER


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_text(value: date | str) -> str:
    if isinstance(value, date):
        return value.isoformat()
    date.fromisoformat(value)
    return value


_ALLOWED_TABLES = {
    "algorithm_schema_version",
    "questions",
    "question_aliases",
    "question_mentions",
    "daily_selections",
    "push_history",
}
