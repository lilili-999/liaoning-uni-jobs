import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    city TEXT NOT NULL,
    school TEXT NOT NULL,
    title TEXT NOT NULL,
    post_date TEXT,
    year INTEGER,
    job_category TEXT,
    position_keywords TEXT,
    degree_requirement TEXT,
    major_requirement TEXT,
    political_requirement TEXT,
    fresh_graduate TEXT,
    deadline TEXT,
    summary TEXT,
    list_url TEXT,
    detail_url TEXT NOT NULL UNIQUE,
    attachment_urls TEXT,
    content_hash TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    status TEXT DEFAULT '有效',
    is_new_today INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jobs_school_date
ON jobs (school, post_date);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    new_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    change_type TEXT NOT NULL,
    old_hash TEXT,
    new_hash TEXT,
    changed_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect() as connection:
        connection.executescript(SCHEMA)


if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化：{DB_PATH}")
