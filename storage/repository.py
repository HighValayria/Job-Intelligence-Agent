from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from models.classification import ClassificationResult, PostType
from models.interview import Interview
from models.offer import Offer
from models.raw_post import RawPost
from models.recruitment import Recruitment
from models.unified_content import UnifiedContent
from models.work_condition import WorkCondition
from storage.db import initialize_database, open_connection

ExtractedPayload = Recruitment | Interview | Offer | WorkCondition | None


@dataclass(frozen=True)
class SavePostResult:
    inserted: bool
    reason: str


class Repository:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.conn = open_connection(self.db_path)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def initialize(self) -> None:
        initialize_database(self.conn)

    def start_crawl_run(self, collector: str) -> str:
        run_id = str(uuid4())
        self.conn.execute(
            """
            INSERT INTO crawl_runs (run_id, collector, started_at)
            VALUES (?, ?, ?)
            """,
            (run_id, collector, _now_iso()),
        )
        self.conn.commit()
        return run_id

    def finish_crawl_run(
        self,
        run_id: str,
        *,
        inserted_count: int,
        skipped_count: int,
        status: str = "succeeded",
    ) -> None:
        self.conn.execute(
            """
            UPDATE crawl_runs
            SET finished_at = ?, inserted_count = ?, skipped_count = ?, status = ?
            WHERE run_id = ?
            """,
            (_now_iso(), inserted_count, skipped_count, status, run_id),
        )
        self.conn.commit()

    def refresh_companies(self, companies: list[dict[str, Any]]) -> None:
        with self.conn:
            for company in companies:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO companies
                        (canonical_name, company_type, aliases_json)
                    VALUES (?, ?, ?)
                    """,
                    (
                        company["canonical_name"],
                        company.get("company_type"),
                        _json(company.get("aliases", [])),
                    ),
                )

    def post_exists(self, platform: str, post_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM posts WHERE platform = ? AND post_id = ? LIMIT 1",
            (platform, post_id),
        ).fetchone()
        return row is not None

    def fingerprint_exists(self, fingerprint: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM posts WHERE content_fingerprint = ? LIMIT 1",
            (fingerprint,),
        ).fetchone()
        return row is not None

    def save_processed_post(
        self,
        *,
        raw_post: RawPost,
        content: UnifiedContent,
        classification: ClassificationResult,
        extracted: ExtractedPayload,
        content_fingerprint: str,
    ) -> SavePostResult:
        if self.post_exists(raw_post.platform, raw_post.post_id):
            return SavePostResult(inserted=False, reason="duplicate_post_id")
        if self.fingerprint_exists(content_fingerprint):
            return SavePostResult(inserted=False, reason="duplicate_content")

        extraction_data = (
            extracted.model_dump(mode="json") if extracted is not None else None
        )
        needs_review = classification.needs_review or (
            extracted.needs_review if extracted is not None else True
        )
        confidence = min(
            classification.confidence,
            extracted.confidence if extracted is not None else 0.0,
        )

        try:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO posts (
                        platform, post_id, url, title, author, publish_time,
                        crawl_time, raw_text, images_json, metadata_json,
                        ocr_text, full_content, content_fingerprint,
                        primary_type, secondary_tags_json, extraction_json,
                        confidence, needs_review, inserted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        raw_post.platform,
                        raw_post.post_id,
                        raw_post.url,
                        raw_post.title,
                        raw_post.author,
                        _iso(raw_post.publish_time),
                        _iso(raw_post.crawl_time),
                        raw_post.text,
                        _json(raw_post.images),
                        _json(raw_post.metadata),
                        content.ocr_text,
                        content.full_content,
                        content_fingerprint,
                        classification.primary_type.value,
                        _json(classification.secondary_tags),
                        _json(extraction_data),
                        confidence,
                        int(needs_review),
                        _now_iso(),
                    ),
                )
                if extracted is not None:
                    self._insert_extracted(
                        raw_post.platform,
                        raw_post.post_id,
                        classification.primary_type,
                        extracted,
                    )
        except sqlite3.IntegrityError as exc:
            if "content_fingerprint" in str(exc):
                return SavePostResult(inserted=False, reason="duplicate_content")
            if "posts.platform, posts.post_id" in str(exc):
                return SavePostResult(inserted=False, reason="duplicate_post_id")
            raise

        return SavePostResult(inserted=True, reason="inserted")

    def count_rows(self, table: str) -> int:
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"unsupported table: {table}")
        row = self.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def fetch_all(self, table: str) -> list[dict[str, Any]]:
        if table not in _ALLOWED_TABLES:
            raise ValueError(f"unsupported table: {table}")
        rows = self.conn.execute(f"SELECT * FROM {table}").fetchall()
        return [dict(row) for row in rows]

    def fetch_overview(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                platform, post_id, title, author, publish_time, crawl_time,
                primary_type, secondary_tags_json, confidence, needs_review,
                url, content_fingerprint
            FROM posts
            ORDER BY crawl_time DESC, platform, post_id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_needs_review(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT platform, post_id, title, primary_type, confidence, url
            FROM posts
            WHERE needs_review = 1
            ORDER BY crawl_time DESC, platform, post_id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _insert_extracted(
        self,
        platform: str,
        post_id: str,
        post_type: PostType,
        extracted: Recruitment | Interview | Offer | WorkCondition,
    ) -> None:
        if post_type == PostType.RECRUITMENT and isinstance(extracted, Recruitment):
            self._insert_recruitment(platform, post_id, extracted)
        elif post_type == PostType.INTERVIEW and isinstance(extracted, Interview):
            self._insert_interview(platform, post_id, extracted)
        elif post_type == PostType.OFFER and isinstance(extracted, Offer):
            self._insert_offer(platform, post_id, extracted)
        elif post_type == PostType.WORK_CONDITION and isinstance(
            extracted, WorkCondition
        ):
            self._insert_work_condition(platform, post_id, extracted)

    def _insert_recruitment(
        self, platform: str, post_id: str, record: Recruitment
    ) -> None:
        data = record.model_dump(mode="json")
        self.conn.execute(
            """
            INSERT INTO recruitments (
                platform, post_id, company, company_type, department, job_title,
                job_family, job_type, recruitment_batch, graduation_year,
                education_requirement, major_requirement, city, skills_json,
                responsibilities_json, requirements_json, headcount,
                application_start, application_deadline, application_method,
                official_url, referral_code, confidence, needs_review,
                field_evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                post_id,
                data["company"],
                data["company_type"],
                data["department"],
                data["job_title"],
                data["job_family"],
                data["job_type"],
                data["recruitment_batch"],
                data["graduation_year"],
                data["education_requirement"],
                data["major_requirement"],
                data["city"],
                _json(data["skills"]),
                _json(data["responsibilities"]),
                _json(data["requirements"]),
                data["headcount"],
                data["application_start"],
                data["application_deadline"],
                data["application_method"],
                data["official_url"],
                data["referral_code"],
                data["confidence"],
                int(data["needs_review"]),
                _json(data["field_evidence"]),
            ),
        )

    def _insert_interview(self, platform: str, post_id: str, record: Interview) -> None:
        data = record.model_dump(mode="json")
        self.conn.execute(
            """
            INSERT INTO interviews (
                platform, post_id, company, department, job_title, job_family,
                recruitment_type, interview_date, confidence, needs_review,
                field_evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                post_id,
                data["company"],
                data["department"],
                data["job_title"],
                data["job_family"],
                data["recruitment_type"],
                data["interview_date"],
                data["confidence"],
                int(data["needs_review"]),
                _json(data["field_evidence"]),
            ),
        )
        for round_data in data["rounds"] or []:
            self.conn.execute(
                """
                INSERT INTO interview_rounds (
                    platform, post_id, round_number, round_type, duration,
                    self_intro, project_questions_json, basic_questions_json,
                    system_design_questions_json, coding_questions_json,
                    algorithm_questions_json, scenario_questions_json,
                    behavior_questions_json, focus_json, difficulty, result
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    platform,
                    post_id,
                    round_data["round_number"],
                    round_data["round_type"],
                    round_data["duration"],
                    _bool_to_int(round_data["self_intro"]),
                    _json(round_data["project_questions"]),
                    _json(round_data["basic_questions"]),
                    _json(round_data["system_design_questions"]),
                    _json(round_data["coding_questions"]),
                    _json(round_data["algorithm_questions"]),
                    _json(round_data["scenario_questions"]),
                    _json(round_data["behavior_questions"]),
                    _json(round_data["focus"]),
                    round_data["difficulty"],
                    round_data["result"],
                ),
            )

    def _insert_offer(self, platform: str, post_id: str, record: Offer) -> None:
        data = record.model_dump(mode="json")
        self.conn.execute(
            """
            INSERT INTO offers (
                platform, post_id, company, department, job_title, job_family,
                city, offer_level, offer_tier, base_monthly, salary_months,
                annual_base, performance_bonus, sign_on_bonus, stock, allowance,
                estimated_total_comp, probation_salary, probation_period, housing,
                meal, transport, insurance, provident_fund, annual_leave,
                offer_date, deadline, accepted, salary_raw, benefit_raw,
                confidence, needs_review, field_evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                post_id,
                data["company"],
                data["department"],
                data["job_title"],
                data["job_family"],
                data["city"],
                data["offer_level"],
                data["offer_tier"],
                data["base_monthly"],
                data["salary_months"],
                data["annual_base"],
                data["performance_bonus"],
                data["sign_on_bonus"],
                data["stock"],
                data["allowance"],
                data["estimated_total_comp"],
                data["probation_salary"],
                data["probation_period"],
                data["housing"],
                data["meal"],
                data["transport"],
                data["insurance"],
                data["provident_fund"],
                data["annual_leave"],
                data["offer_date"],
                data["deadline"],
                _bool_to_int(data["accepted"]),
                data["salary_raw"],
                data["benefit_raw"],
                data["confidence"],
                int(data["needs_review"]),
                _json(data["field_evidence"]),
            ),
        )

    def _insert_work_condition(
        self, platform: str, post_id: str, record: WorkCondition
    ) -> None:
        data = record.model_dump(mode="json")
        self.conn.execute(
            """
            INSERT INTO work_conditions (
                platform, post_id, company, department, job_family, city,
                base_monthly, annual_total_comp, bonus, stock, start_time,
                end_time_typical, end_time_extreme, work_hours_raw,
                overtime_frequency, weekend_work, on_call, annual_leave,
                canteen, meal_allowance, housing, transport, management,
                team_atmosphere, promotion, job_stability, pros_json,
                cons_json, wlb_score, overall_sentiment, confidence,
                needs_review, field_evidence_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                platform,
                post_id,
                data["company"],
                data["department"],
                data["job_family"],
                data["city"],
                data["base_monthly"],
                data["annual_total_comp"],
                data["bonus"],
                data["stock"],
                data["start_time"],
                data["end_time_typical"],
                data["end_time_extreme"],
                data["work_hours_raw"],
                data["overtime_frequency"],
                data["weekend_work"],
                data["on_call"],
                data["annual_leave"],
                data["canteen"],
                data["meal_allowance"],
                data["housing"],
                data["transport"],
                data["management"],
                data["team_atmosphere"],
                data["promotion"],
                data["job_stability"],
                _json(data["pros"]),
                _json(data["cons"]),
                data["wlb_score"],
                data["overall_sentiment"],
                data["confidence"],
                int(data["needs_review"]),
                _json(data["field_evidence"]),
            ),
        )


_ALLOWED_TABLES = {
    "crawl_runs",
    "companies",
    "posts",
    "recruitments",
    "interviews",
    "interview_rounds",
    "offers",
    "work_conditions",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return int(value)

