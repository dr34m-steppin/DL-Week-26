import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "relearnai.db"


SCHEMA_SQL = """
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


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row[1] for row in rows}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
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
