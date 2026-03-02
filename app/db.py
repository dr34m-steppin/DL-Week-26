import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Iterable, Optional

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:  # pragma: no cover - optional dependency in local-only mode
    psycopg2 = None
    RealDictCursor = None

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_FILE = "relearnai.db"


SQLITE_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'professor')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    professor_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (professor_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS course_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, course_id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS skill_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    prerequisites_json TEXT NOT NULL DEFAULT '[]',
    validated INTEGER NOT NULL DEFAULT 0,
    professor_notes TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_option TEXT NOT NULL,
    explanation TEXT NOT NULL,
    source_chunk TEXT NOT NULL DEFAULT '',
    approved INTEGER NOT NULL DEFAULT 0,
    created_by_ai INTEGER NOT NULL DEFAULT 1,
    professor_edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    selected_option TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    response_time_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (question_id) REFERENCES quiz_questions(id)
);

CREATE TABLE IF NOT EXISTS student_topic_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    hints_used INTEGER NOT NULL DEFAULT 0,
    total_response_time_ms INTEGER NOT NULL DEFAULT 0,
    streak_wrong INTEGER NOT NULL DEFAULT 0,
    mastery_score REAL NOT NULL DEFAULT 0,
    struggle_score REAL NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    UNIQUE(user_id, course_id, topic),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS snapscore_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS risk_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    professor_override TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, course_id, topic),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS grading_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    score_percent REAL NOT NULL,
    ai_recommended_grade TEXT NOT NULL,
    professor_decision TEXT NOT NULL DEFAULT 'PENDING',
    professor_notes TEXT NOT NULL DEFAULT '',
    reviewed_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    message TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (course_id) REFERENCES courses(id)
);

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_interest_profiles (
    user_id INTEGER PRIMARY KEY,
    user_type TEXT NOT NULL DEFAULT 'student',
    domains_json TEXT NOT NULL DEFAULT '[]',
    skill_level TEXT NOT NULL DEFAULT 'intermediate',
    goals_json TEXT NOT NULL DEFAULT '[]',
    learning_style TEXT NOT NULL DEFAULT 'projects',
    time_commitment_min INTEGER NOT NULL DEFAULT 60,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS learning_journeys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'goal',
    source_text TEXT NOT NULL,
    learner_level TEXT NOT NULL DEFAULT 'intermediate',
    visibility TEXT NOT NULL DEFAULT 'private',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    journey_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS journey_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    journey_id INTEGER NOT NULL,
    milestone_title TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    evidence_text TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (journey_id) REFERENCES learning_journeys(id)
);

CREATE TABLE IF NOT EXISTS contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    domain TEXT NOT NULL,
    contribution_type TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'private',
    is_open_source INTEGER NOT NULL DEFAULT 0,
    source_url TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    ai_similarity REAL NOT NULL DEFAULT 0,
    ai_novelty REAL NOT NULL DEFAULT 0,
    ai_factual_confidence REAL NOT NULL DEFAULT 0,
    ai_status TEXT NOT NULL DEFAULT 'PENDING',
    human_status TEXT NOT NULL DEFAULT 'PENDING',
    final_status TEXT NOT NULL DEFAULT 'PENDING',
    snapscore_awarded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    allow_course_conversion INTEGER NOT NULL DEFAULT 0,
    outline_json TEXT NOT NULL DEFAULT '',
    outline_course_id INTEGER,
    outline_generated_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS contribution_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contribution_id INTEGER NOT NULL,
    reviewer_user_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    confidence_score REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contribution_id) REFERENCES contributions(id),
    FOREIGN KEY (reviewer_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS contribution_endorsements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contribution_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    weight REAL NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contribution_id, user_id),
    FOREIGN KEY (contribution_id) REFERENCES contributions(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tech_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'medium',
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


POSTGRES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'professor')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    professor_id BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS course_documents (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id),
    filename TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS enrollments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, course_id)
);

CREATE TABLE IF NOT EXISTS skill_map (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id),
    topic TEXT NOT NULL,
    prerequisites_json TEXT NOT NULL DEFAULT '[]',
    validated INTEGER NOT NULL DEFAULT 0,
    professor_notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS quiz_questions (
    id BIGSERIAL PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES courses(id),
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_option TEXT NOT NULL,
    explanation TEXT NOT NULL,
    source_chunk TEXT NOT NULL DEFAULT '',
    approved INTEGER NOT NULL DEFAULT 0,
    created_by_ai INTEGER NOT NULL DEFAULT 1,
    professor_edited INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    question_id BIGINT NOT NULL REFERENCES quiz_questions(id),
    selected_option TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    response_time_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS student_topic_state (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    topic TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    hints_used INTEGER NOT NULL DEFAULT 0,
    total_response_time_ms INTEGER NOT NULL DEFAULT 0,
    streak_wrong INTEGER NOT NULL DEFAULT 0,
    mastery_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    struggle_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMP,
    UNIQUE(user_id, course_id, topic)
);

CREATE TABLE IF NOT EXISTS snapscore_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS risk_flags (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    topic TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    professor_override TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, course_id, topic)
);

CREATE TABLE IF NOT EXISTS grading_reviews (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    score_percent DOUBLE PRECISION NOT NULL,
    ai_recommended_grade TEXT NOT NULL,
    professor_decision TEXT NOT NULL DEFAULT 'PENDING',
    professor_notes TEXT NOT NULL DEFAULT '',
    reviewed_by BIGINT REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    course_id BIGINT NOT NULL REFERENCES courses(id),
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    message TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS domains (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_interest_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES users(id),
    user_type TEXT NOT NULL DEFAULT 'student',
    domains_json TEXT NOT NULL DEFAULT '[]',
    skill_level TEXT NOT NULL DEFAULT 'intermediate',
    goals_json TEXT NOT NULL DEFAULT '[]',
    learning_style TEXT NOT NULL DEFAULT 'projects',
    time_commitment_min INTEGER NOT NULL DEFAULT 60,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learning_journeys (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'goal',
    source_text TEXT NOT NULL,
    learner_level TEXT NOT NULL DEFAULT 'intermediate',
    visibility TEXT NOT NULL DEFAULT 'private',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    journey_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journey_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    journey_id BIGINT NOT NULL REFERENCES learning_journeys(id),
    milestone_title TEXT NOT NULL,
    order_index INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    evidence_text TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contributions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    domain TEXT NOT NULL,
    contribution_type TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'private',
    is_open_source INTEGER NOT NULL DEFAULT 0,
    source_url TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    ai_similarity DOUBLE PRECISION NOT NULL DEFAULT 0,
    ai_novelty DOUBLE PRECISION NOT NULL DEFAULT 0,
    ai_factual_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    ai_status TEXT NOT NULL DEFAULT 'PENDING',
    human_status TEXT NOT NULL DEFAULT 'PENDING',
    final_status TEXT NOT NULL DEFAULT 'PENDING',
    snapscore_awarded INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    allow_course_conversion INTEGER NOT NULL DEFAULT 0,
    outline_json TEXT NOT NULL DEFAULT '',
    outline_course_id BIGINT,
    outline_generated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS contribution_reviews (
    id BIGSERIAL PRIMARY KEY,
    contribution_id BIGINT NOT NULL REFERENCES contributions(id),
    reviewer_user_id BIGINT NOT NULL REFERENCES users(id),
    decision TEXT NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contribution_endorsements (
    id BIGSERIAL PRIMARY KEY,
    contribution_id BIGINT NOT NULL REFERENCES contributions(id),
    user_id BIGINT NOT NULL REFERENCES users(id),
    weight DOUBLE PRECISION NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(contribution_id, user_id)
);

CREATE TABLE IF NOT EXISTS tech_updates (
    id BIGSERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'medium',
    created_by BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    link TEXT NOT NULL DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _database_url() -> str:
    for key in ("DATABASE_URL", "SUPABASE_DATABASE_URL", "POSTGRES_URL"):
        value = os.getenv(key, "").strip()
        if value:
            if "sslmode=" not in value.lower():
                sep = "&" if "?" in value else "?"
                value = f"{value}{sep}sslmode=require"
            return value
    return ""


def _using_postgres() -> bool:
    value = _database_url().lower()
    return value.startswith("postgres://") or value.startswith("postgresql://")


def _sqlite_db_path() -> Path:
    db_path_env = os.getenv("DB_PATH", "").strip()
    if db_path_env:
        candidate = Path(db_path_env)
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass

    render_disk_path = Path("/var/data")
    if render_disk_path.exists() and os.access(render_disk_path, os.W_OK):
        return render_disk_path / DEFAULT_DB_FILE
    return DATA_DIR / DEFAULT_DB_FILE


def _sqlite_to_postgres_query(query: str) -> str:
    q = query.strip().rstrip(";")

    q = re.sub(
        r"datetime\('now',\s*'-\s*([0-9]+)\s*day'\)",
        lambda m: f"(NOW() - INTERVAL '{m.group(1)} days')",
        q,
        flags=re.IGNORECASE,
    )
    q = re.sub(
        r"substr\(([^,]+),\s*1\s*,\s*10\s*\)",
        r"substring((\1)::text from 1 for 10)",
        q,
        flags=re.IGNORECASE,
    )

    if re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", q, flags=re.IGNORECASE):
        q = re.sub(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", "INSERT INTO ", q, count=1, flags=re.IGNORECASE)
        if "on conflict" not in q.lower():
            q = f"{q} ON CONFLICT DO NOTHING"

    replace_match = re.match(
        r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*VALUES\s*\((.*)\)\s*$",
        q,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if replace_match:
        table = replace_match.group(1)
        cols_raw = replace_match.group(2)
        values_raw = replace_match.group(3)
        columns = [item.strip() for item in cols_raw.split(",") if item.strip()]
        if columns:
            conflict_col = columns[0]
            updates = [f"{col} = EXCLUDED.{col}" for col in columns[1:]]
            q = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({values_raw})"
            if updates:
                q += f" ON CONFLICT ({conflict_col}) DO UPDATE SET {', '.join(updates)}"
            else:
                q += f" ON CONFLICT ({conflict_col}) DO NOTHING"

    q = q.replace("?", "%s")
    return q


class _PostgresCursorCompat:
    def __init__(self, cursor: Any, lastrowid: Optional[int] = None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _PostgresConnectionCompat:
    def __init__(self, raw_conn: Any):
        self._raw = raw_conn

    def execute(self, query: str, params: Iterable[Any] = ()):
        sql = _sqlite_to_postgres_query(query)
        values = tuple(params or ())
        cur = self._raw.cursor(cursor_factory=RealDictCursor)

        lastrowid = None
        is_insert = sql.lstrip().lower().startswith("insert ")
        has_returning = " returning " in f" {sql.lower()} "

        if is_insert and not has_returning:
            try:
                cur.execute(f"{sql} RETURNING id", values)
                row = cur.fetchone()
                if row and "id" in row and row["id"] is not None:
                    lastrowid = int(row["id"])
                return _PostgresCursorCompat(cur, lastrowid=lastrowid)
            except Exception:
                self._raw.rollback()
                cur = self._raw.cursor(cursor_factory=RealDictCursor)

        cur.execute(sql, values)
        return _PostgresCursorCompat(cur, lastrowid=lastrowid)

    def executemany(self, query: str, seq_of_params: Iterable[Iterable[Any]]):
        sql = _sqlite_to_postgres_query(query)
        values = [tuple(params or ()) for params in seq_of_params]
        cur = self._raw.cursor(cursor_factory=RealDictCursor)
        cur.executemany(sql, values)
        return cur

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def get_connection():
    if _using_postgres():
        if psycopg2 is None:
            raise RuntimeError("DATABASE_URL is set but psycopg2 is not installed. Add psycopg2-binary to requirements.")
        db_url = _database_url()
        parsed = urlparse(db_url)
        if not parsed.scheme.startswith("postgres"):
            raise RuntimeError("DATABASE_URL must start with postgresql:// or postgres://")
        raw_conn = psycopg2.connect(db_url, connect_timeout=12)
        raw_conn.autocommit = False
        return _PostgresConnectionCompat(raw_conn)

    db_path = _sqlite_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    if _using_postgres():
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ? AND column_name = ?
            LIMIT 1
            """,
            (table, column),
        ).fetchone()
        if row:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return

    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _run_postgres_schema(conn) -> None:
    statements = [stmt.strip() for stmt in POSTGRES_SCHEMA_SQL.split(";") if stmt.strip()]
    for stmt in statements:
        conn.execute(stmt)


def init_db() -> None:
    conn = get_connection()
    try:
        if _using_postgres():
            _run_postgres_schema(conn)
        else:
            conn.executescript(SQLITE_SCHEMA_SQL)

        _ensure_column(conn, "contributions", "allow_course_conversion", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "contributions", "outline_json", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "contributions", "outline_course_id", "INTEGER")
        _ensure_column(conn, "contributions", "outline_generated_at", "TEXT NOT NULL DEFAULT ''")

        default_domains = [
            ("ai", "Artificial Intelligence"),
            ("robotics", "Robotics"),
            ("semiconductor", "Semiconductor"),
            ("finance", "Finance"),
            ("healthcare", "Healthcare"),
            ("nlp", "Natural Language Processing"),
            ("computer-vision", "Computer Vision"),
            ("data-science", "Data Science"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO domains (slug, display_name) VALUES (?, ?)",
            default_domains,
        )
        conn.commit()
    finally:
        conn.close()
