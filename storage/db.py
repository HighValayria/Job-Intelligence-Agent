from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS crawl_runs (
    run_id TEXT PRIMARY KEY,
    collector TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS companies (
    canonical_name TEXT PRIMARY KEY,
    company_type TEXT,
    aliases_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    author TEXT,
    publish_time TEXT,
    crawl_time TEXT,
    raw_text TEXT,
    images_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    ocr_text TEXT,
    full_content TEXT,
    content_fingerprint TEXT UNIQUE,
    primary_type TEXT,
    secondary_tags_json TEXT NOT NULL,
    extraction_json TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    inserted_at TEXT NOT NULL,
    PRIMARY KEY (platform, post_id)
);

CREATE TABLE IF NOT EXISTS recruitments (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    company TEXT,
    company_type TEXT,
    department TEXT,
    job_title TEXT,
    job_family TEXT,
    job_type TEXT,
    recruitment_batch TEXT,
    graduation_year INTEGER,
    education_requirement TEXT,
    major_requirement TEXT,
    city TEXT,
    skills_json TEXT,
    responsibilities_json TEXT,
    requirements_json TEXT,
    headcount INTEGER,
    application_start TEXT,
    application_deadline TEXT,
    application_method TEXT,
    official_url TEXT,
    referral_code TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    field_evidence_json TEXT NOT NULL,
    PRIMARY KEY (platform, post_id),
    FOREIGN KEY (platform, post_id) REFERENCES posts(platform, post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS interviews (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    company TEXT,
    department TEXT,
    job_title TEXT,
    job_family TEXT,
    recruitment_type TEXT,
    interview_date TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    field_evidence_json TEXT NOT NULL,
    PRIMARY KEY (platform, post_id),
    FOREIGN KEY (platform, post_id) REFERENCES posts(platform, post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS interview_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    round_number INTEGER,
    round_type TEXT,
    duration TEXT,
    self_intro INTEGER,
    project_questions_json TEXT,
    basic_questions_json TEXT,
    system_design_questions_json TEXT,
    coding_questions_json TEXT,
    algorithm_questions_json TEXT,
    scenario_questions_json TEXT,
    behavior_questions_json TEXT,
    focus_json TEXT,
    difficulty TEXT,
    result TEXT,
    FOREIGN KEY (platform, post_id) REFERENCES posts(platform, post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS offers (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    company TEXT,
    department TEXT,
    job_title TEXT,
    job_family TEXT,
    city TEXT,
    offer_level TEXT,
    offer_tier TEXT,
    base_monthly INTEGER,
    salary_months INTEGER,
    annual_base INTEGER,
    performance_bonus INTEGER,
    sign_on_bonus INTEGER,
    stock TEXT,
    allowance TEXT,
    estimated_total_comp INTEGER,
    probation_salary TEXT,
    probation_period TEXT,
    housing TEXT,
    meal TEXT,
    transport TEXT,
    insurance TEXT,
    provident_fund TEXT,
    annual_leave TEXT,
    offer_date TEXT,
    deadline TEXT,
    accepted INTEGER,
    salary_raw TEXT,
    benefit_raw TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    field_evidence_json TEXT NOT NULL,
    PRIMARY KEY (platform, post_id),
    FOREIGN KEY (platform, post_id) REFERENCES posts(platform, post_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS work_conditions (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    company TEXT,
    department TEXT,
    job_family TEXT,
    city TEXT,
    base_monthly INTEGER,
    annual_total_comp INTEGER,
    bonus TEXT,
    stock TEXT,
    start_time TEXT,
    end_time_typical TEXT,
    end_time_extreme TEXT,
    work_hours_raw TEXT,
    overtime_frequency TEXT,
    weekend_work TEXT,
    on_call TEXT,
    annual_leave TEXT,
    canteen TEXT,
    meal_allowance TEXT,
    housing TEXT,
    transport TEXT,
    management TEXT,
    team_atmosphere TEXT,
    promotion TEXT,
    job_stability TEXT,
    pros_json TEXT,
    cons_json TEXT,
    wlb_score REAL,
    overall_sentiment TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    needs_review INTEGER NOT NULL DEFAULT 0,
    field_evidence_json TEXT NOT NULL,
    PRIMARY KEY (platform, post_id),
    FOREIGN KEY (platform, post_id) REFERENCES posts(platform, post_id) ON DELETE CASCADE
);
"""


def open_connection(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()

