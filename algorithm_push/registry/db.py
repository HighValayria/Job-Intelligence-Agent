from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS algorithm_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    pool TEXT NOT NULL,
    platform TEXT NOT NULL,
    primary_tag TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    enabled INTEGER NOT NULL DEFAULT 1,
    priority REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(pool, canonical_key)
);

CREATE INDEX IF NOT EXISTS idx_questions_canonical_key
    ON questions(canonical_key);

CREATE INDEX IF NOT EXISTS idx_questions_pool_enabled
    ON questions(pool, enabled, status);

CREATE TABLE IF NOT EXISTS question_aliases (
    alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(normalized_alias, source)
);

CREATE INDEX IF NOT EXISTS idx_question_aliases_normalized
    ON question_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS question_mentions (
    mention_id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT,
    canonical_key TEXT NOT NULL,
    raw_title TEXT NOT NULL,
    normalized_title TEXT,
    source_post_url TEXT,
    company TEXT,
    interview_round TEXT,
    context TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS daily_selections (
    selection_date TEXT NOT NULL,
    question_id TEXT NOT NULL,
    slot TEXT NOT NULL,
    pool TEXT NOT NULL,
    selected_score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (selection_date, slot),
    UNIQUE(selection_date, question_id),
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS push_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selection_date TEXT NOT NULL,
    question_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    push_status TEXT NOT NULL,
    pushed_at TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
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
    conn.execute(
        "INSERT OR IGNORE INTO algorithm_schema_version (version) VALUES (?)",
        (1,),
    )
    conn.commit()
