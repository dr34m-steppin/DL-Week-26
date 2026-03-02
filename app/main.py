import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.db import get_connection, init_db
from app.security import hash_password, verify_password
from app.services.llm import LLMService
from app.services.mastery import compute_topic_state, grade_band
from app.services.pdf_utils import extract_text_from_pdf_bytes
from app.services.platform import (
    ai_preverify_contribution,
    generate_journey_from_goal,
    interest_match_score,
    parse_json_list,
    reputation_components,
    split_csv_values,
)
from app.services.retrieval import LexicalRetriever, split_into_chunks

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="ReLearnAI")
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
llm_service = LLMService()


def _fetchone(conn, query: str, params: tuple = ()):
    return conn.execute(query, params).fetchone()


def _fetchall(conn, query: str, params: tuple = ()):
    return conn.execute(query, params).fetchall()


def _execute(conn, query: str, params: tuple = ()):
    cursor = conn.execute(query, params)
    conn.commit()
    return cursor


def _current_user(request: Request) -> Optional[Dict[str, Any]]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    conn = get_connection()
    try:
        row = _fetchone(conn, "SELECT * FROM users WHERE id = ?", (user_id,))
        return dict(row) if row else None
    finally:
        conn.close()


def _require_auth(request: Request, role: Optional[str] = None) -> Optional[RedirectResponse]:
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if role and user["role"] != role:
        return RedirectResponse("/", status_code=303)
    return None


def _context(request: Request, **kwargs: Any) -> Dict[str, Any]:
    return {
        "request": request,
        "user": _current_user(request),
        **kwargs,
    }


def _latest_course_document(conn, course_id: int):
    return _fetchone(
        conn,
        """
        SELECT * FROM course_documents
        WHERE course_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (course_id,),
    )


def _course_documents(conn, course_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    rows = _fetchall(
        conn,
        """
        SELECT *
        FROM course_documents
        WHERE course_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (course_id, limit),
    )
    return [dict(row) for row in rows]


def _course_corpus_text(
    conn,
    course_id: int,
    max_docs: int = 12,
    max_chars: int = 120000,
    max_chars_per_doc: int = 14000,
) -> str:
    documents = _course_documents(conn, course_id, limit=max_docs)
    if not documents:
        return ""

    chunks: List[str] = []
    used_chars = 0
    for idx, doc in enumerate(documents, start=1):
        filename = str(doc.get("filename", f"document_{idx}"))
        raw_text = str(doc.get("raw_text", "") or "").strip()
        if not raw_text:
            continue

        limited = raw_text[:max_chars_per_doc]
        section = f"[Source {idx}: {filename}]\n{limited}"
        section_len = len(section)
        if used_chars + section_len > max_chars and chunks:
            break
        chunks.append(section)
        used_chars += section_len

    return "\n\n".join(chunks).strip()


def _ensure_enrolled(conn, user_id: int, course_id: int) -> None:
    _execute(
        conn,
        """
        INSERT OR IGNORE INTO enrollments (user_id, course_id)
        VALUES (?, ?)
        """,
        (user_id, course_id),
    )


def _course_snapscore_breakdown(conn, user_id: int, course_id: int) -> Dict[str, Any]:
    mastery_row = _fetchone(
        conn,
        """
        SELECT AVG(mastery_score) AS avg_mastery
        FROM student_topic_state
        WHERE user_id = ? AND course_id = ?
        """,
        (user_id, course_id),
    )
    mastery_pct = round(float((mastery_row["avg_mastery"] or 0) * 100), 2) if mastery_row else 0.0

    quiz_row = _fetchone(
        conn,
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct
        FROM quiz_attempts
        WHERE user_id = ? AND course_id = ?
        """,
        (user_id, course_id),
    )
    total_attempts = int(quiz_row["total"] or 0) if quiz_row else 0
    correct_attempts = int(quiz_row["correct"] or 0) if quiz_row else 0
    accuracy_pct = round(((correct_attempts + 2) / max(1, total_attempts + 4)) * 100, 2)

    grading_rows = _fetchall(
        conn,
        """
        SELECT score_percent
        FROM grading_reviews
        WHERE user_id = ? AND course_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 2
        """,
        (user_id, course_id),
    )
    latest_grade = float(grading_rows[0]["score_percent"]) if grading_rows else mastery_pct
    prev_grade = float(grading_rows[1]["score_percent"]) if len(grading_rows) > 1 else latest_grade
    trend_delta = latest_grade - prev_grade
    improvement_pct = max(0.0, min(100.0, latest_grade + trend_delta * 0.8))

    engagement_row = _fetchone(
        conn,
        """
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT substr(created_at, 1, 10)) AS active_days
        FROM quiz_attempts
        WHERE user_id = ? AND course_id = ?
          AND created_at >= datetime('now', '-21 day')
        """,
        (user_id, course_id),
    )
    recent_total = int(engagement_row["total"] or 0) if engagement_row else 0
    active_days = int(engagement_row["active_days"] or 0) if engagement_row else 0
    engagement_pct = min(100.0, min(70.0, recent_total * 5.0) + min(30.0, active_days * 4.0))

    contrib_row = _fetchone(
        conn,
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN final_status = 'VERIFIED' THEN 1 ELSE 0 END) AS verified
        FROM contributions
        WHERE user_id = ?
        """,
        (user_id,),
    )
    verified_contrib = int(contrib_row["verified"] or 0) if contrib_row else 0
    contribution_bonus = min(8.0, verified_contrib * 2.0)

    score = (
        mastery_pct * 0.38
        + accuracy_pct * 0.28
        + improvement_pct * 0.22
        + engagement_pct * 0.12
        + contribution_bonus
    )
    final_score = int(round(max(0.0, min(100.0, score))))

    return {
        "score": final_score,
        "mastery_pct": round(mastery_pct, 2),
        "accuracy_pct": round(accuracy_pct, 2),
        "improvement_pct": round(improvement_pct, 2),
        "engagement_pct": round(engagement_pct, 2),
        "contribution_bonus": round(contribution_bonus, 2),
        "attempts": total_attempts,
    }


def _snapscore_total(conn, user_id: int, course_id: int) -> int:
    return int(_course_snapscore_breakdown(conn, user_id, course_id)["score"])


def _parse_options(raw: str) -> List[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()][:4]
        except json.JSONDecodeError:
            pass
    opts = [line.strip() for line in raw.splitlines() if line.strip()]
    return opts[:4]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _question_priority(question: Dict[str, Any], topic_mastery: Dict[str, float]) -> float:
    return topic_mastery.get(question["topic"], 0.5)


def _extract_citations(chunks: List[Any]) -> List[str]:
    return [f"Chunk {chunk.chunk_id}" for chunk in chunks]


def _topic_category(topic: str) -> str:
    t = topic.lower()
    mapping = [
        ("NLP", ["language", "text", "token", "embedding", "transformer", "nlp"]),
        ("Search", ["retrieval", "rag", "search", "index", "vector"]),
        ("Learning", ["learning", "training", "gradient", "backprop", "optimization"]),
        ("Evaluation", ["metric", "evaluation", "precision", "recall", "f1", "accuracy"]),
        ("Reasoning", ["reasoning", "planning", "agent", "decision"]),
    ]
    for label, keywords in mapping:
        if any(keyword in t for keyword in keywords):
            return label
    return "Foundations"


def _topic_confidence(topic: str, prerequisites: List[str]) -> int:
    seed = sum(ord(ch) for ch in topic) + len(prerequisites) * 13
    base = 76 + (seed % 17)
    if prerequisites:
        base += 2
    return max(65, min(97, base))


def _skill_status(validated: int, notes: str) -> str:
    if validated:
        return "Human Validated"
    if notes.strip():
        return "AI Generated"
    return "Draft"


def _parse_prerequisites_json(raw: str) -> List[str]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in raw.split(",") if item.strip()]


def _prepare_skill_map(rows: List[Any]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        prereqs = _parse_prerequisites_json(item.get("prerequisites_json", "[]"))
        notes = str(item.get("professor_notes", "") or "")
        topic = str(item.get("topic", "") or "")

        item["prerequisites_list"] = prereqs
        item["prerequisites_text"] = ", ".join(prereqs)
        item["category"] = _topic_category(topic)
        item["confidence_score"] = _topic_confidence(topic, prereqs)
        item["status_badge"] = _skill_status(int(item.get("validated", 0)), notes)
        item["ai_reason"] = notes.strip() or (
            "AI inferred this topic and prerequisite relation from semantic dependencies in the course document."
        )
        prepared.append(item)
    return prepared


def _build_skill_graph(skill_map: List[Dict[str, Any]]) -> Dict[str, Any]:
    def _normalize_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()

    def _tokens(value: str) -> set:
        return {token for token in _normalize_key(value).split(" ") if token}

    topic_to_id = {item["topic"].strip().lower(): str(item["id"]) for item in skill_map if item["topic"].strip()}
    normalized_topic_to_id = {
        _normalize_key(item["topic"]): str(item["id"])
        for item in skill_map
        if _normalize_key(item["topic"])
    }
    topic_tokens_by_id = {
        str(item["id"]): _tokens(item["topic"])
        for item in skill_map
        if str(item.get("id", "")).strip()
    }
    nodes = [
        {
            "id": str(item["id"]),
            "topic": item["topic"],
            "category": item["category"],
            "confidence": item["confidence_score"],
            "status": item["status_badge"],
            "reason": item["ai_reason"],
        }
        for item in skill_map
    ]
    edges: List[Dict[str, str]] = []
    edge_set = set()
    adjacency: Dict[str, List[str]] = {node["id"]: [] for node in nodes}
    fallback_inferred = False

    def _resolve_prereq_source(prereq: str, target_id: str) -> Optional[str]:
        raw = (prereq or "").strip()
        if not raw:
            return None

        source = topic_to_id.get(raw.lower())
        if source and source != target_id:
            return source

        normalized = _normalize_key(raw)
        if normalized in normalized_topic_to_id:
            matched = normalized_topic_to_id[normalized]
            if matched != target_id:
                return matched

        prereq_tokens = _tokens(raw)
        if not prereq_tokens:
            return None

        best_id = None
        best_score = 0.0
        for node_id, node_tokens in topic_tokens_by_id.items():
            if node_id == target_id or not node_tokens:
                continue
            overlap = prereq_tokens.intersection(node_tokens)
            if not overlap:
                continue
            coverage = len(overlap) / max(1, len(prereq_tokens))
            if coverage > best_score:
                best_score = coverage
                best_id = node_id

        if best_score >= 0.6:
            return best_id
        return None

    for item in skill_map:
        target = str(item["id"])
        for prereq in item.get("prerequisites_list", []):
            source = _resolve_prereq_source(str(prereq), target)
            if not source:
                continue
            edge_key = (source, target)
            if edge_key in edge_set:
                continue
            edge_set.add(edge_key)
            edges.append({"source": source, "target": target})
            adjacency[source].append(target)

    # Visual fallback: if no dependency edges were recognized, show an inferred sequence.
    if not edges and len(nodes) > 1:
        fallback_inferred = True
        for idx in range(len(nodes) - 1):
            source = nodes[idx]["id"]
            target = nodes[idx + 1]["id"]
            edge_key = (source, target)
            if edge_key in edge_set:
                continue
            edge_set.add(edge_key)
            edges.append({"source": source, "target": target})
            adjacency[source].append(target)

    visiting = set()
    visited = set()

    def _dfs(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for nxt in adjacency.get(node_id, []):
            if _dfs(nxt):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    has_cycle = any(_dfs(node["id"]) for node in nodes)
    return {
        "nodes": nodes,
        "edges": edges,
        "has_cycle": has_cycle,
        "fallback_inferred": fallback_inferred,
    }


def _session_autopilot_key(course_id: int) -> str:
    return f"autopilot_course_{course_id}"


def _autopilot_enabled(request: Request, course_id: int) -> bool:
    value = request.session.get(_session_autopilot_key(course_id), True)
    return bool(value)


def _manual_learning_state(course_id: int) -> Dict[str, Any]:
    return {
        "state": "MANUAL_MODE",
        "label": "Manual mode",
        "reason": "AI autopilot is off. Choose summary, relearn, tutor, or quiz manually.",
        "cta_label": "Open Learning Tools",
        "cta_href": f"/student/course/{course_id}/learning",
    }


def _mastery_from_counts(attempts: int, correct: int) -> float:
    return round((correct + 1) / (attempts + 2), 4)


def _ensure_interest_profile(conn, user: Dict[str, Any]) -> Dict[str, Any]:
    row = _fetchone(conn, "SELECT * FROM user_interest_profiles WHERE user_id = ?", (user["id"],))
    if row:
        item = dict(row)
    else:
        default_type = "professor" if user["role"] == "professor" else "student"
        _execute(
            conn,
            """
            INSERT OR IGNORE INTO user_interest_profiles
            (user_id, user_type, domains_json, skill_level, goals_json, learning_style, time_commitment_min)
            VALUES (?, ?, '[]', 'intermediate', '[]', 'projects', 60)
            """,
            (user["id"], default_type),
        )
        item = dict(_fetchone(conn, "SELECT * FROM user_interest_profiles WHERE user_id = ?", (user["id"],)))

    item["domains"] = parse_json_list(str(item.get("domains_json", "[]")), [])
    item["goals"] = parse_json_list(str(item.get("goals_json", "[]")), [])
    return item


def _load_domains(conn) -> List[Dict[str, Any]]:
    rows = _fetchall(conn, "SELECT slug, display_name FROM domains ORDER BY display_name ASC")
    return [dict(row) for row in rows]


def _notify_user(conn, user_id: int, category: str, title: str, body: str, link: str = "") -> None:
    _execute(
        conn,
        """
        INSERT INTO notifications (user_id, category, title, body, link)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, category, title, body, link),
    )


def _notify_all_users(conn, category: str, title: str, body: str, link: str = "") -> int:
    total_row = _fetchone(conn, "SELECT COUNT(*) AS total FROM users")
    total = int(total_row["total"] or 0) if total_row else 0
    if total <= 0:
        return 0
    _execute(
        conn,
        """
        INSERT INTO notifications (user_id, category, title, body, link)
        SELECT id, ?, ?, ?, ?
        FROM users
        """,
        (category, title, body, link),
    )
    return total


def _notify_domain_watchers(conn, domain: str, title: str, body: str, link: str = "") -> int:
    # Product behavior: publish/update notifications are platform-wide.
    # `domain` is kept for call-site compatibility and future filtering.
    _ = domain
    return _notify_all_users(conn, "tech_update", title, body, link)


def _safe_json_load(raw: str, fallback: Any):
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _outline_to_text(outline: Dict[str, Any]) -> str:
    modules = outline.get("modules", [])
    milestones = outline.get("milestones", [])
    micro = outline.get("micro_projects", [])
    verify = outline.get("verification_checkpoints", [])
    final_project = outline.get("final_project", {})

    lines: List[str] = []
    lines.append(f"Learning Outline Topic: {outline.get('goal', '')}")
    lines.append(f"Domain: {outline.get('domain', '')}")
    lines.append(f"Learner Level: {outline.get('learner_level', '')}")
    lines.append(f"Pacing: {outline.get('pacing', '')}")
    lines.append("")
    lines.append("Modules")
    for module in modules:
        lines.append(f"- {module.get('phase', 'Phase')}: {', '.join(module.get('items', []))}")
    lines.append("")
    lines.append("Milestones")
    for milestone in milestones:
        lines.append(f"- {milestone.get('title', '')}: {milestone.get('description', '')}")
        lines.append(f"  Checkpoint: {milestone.get('checkpoint', '')}")
    lines.append("")
    lines.append("Micro Projects")
    for item in micro:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Verification Checkpoints")
    for item in verify:
        lines.append(f"- {item}")
    if final_project:
        lines.append("")
        lines.append(f"Final Project: {final_project.get('title', '')}")
        lines.append(f"Objective: {final_project.get('objective', '')}")
        lines.append("Deliverables:")
        for d in final_project.get("deliverables", []):
            lines.append(f"- {d}")
    return "\n".join(lines).strip()


def _resolve_publication_course_owner(conn, contribution_owner_id: int) -> int:
    owner = _fetchone(conn, "SELECT id, role FROM users WHERE id = ?", (contribution_owner_id,))
    if owner and owner["role"] == "professor":
        return int(owner["id"])
    fallback = _fetchone(conn, "SELECT id FROM users WHERE role = 'professor' ORDER BY id ASC LIMIT 1")
    if fallback:
        return int(fallback["id"])
    return int(contribution_owner_id)


def _looks_like_non_real_account(full_name: str, email: str) -> bool:
    name = (full_name or "").strip().lower()
    mail = (email or "").strip().lower()
    local = mail.split("@", 1)[0] if "@" in mail else mail
    domain = mail.split("@", 1)[1] if "@" in mail else ""

    disposable_domains = {
        "x.com",
        "example.com",
        "test.com",
        "mailinator.com",
        "fake.com",
        "invalid.com",
    }
    if domain in disposable_domains:
        return True

    if re.match(r"^(test|demo|journey|acct|snaplive)[-_0-9]*$", local):
        return True

    blocked_name_tokens = {
        "journey tester",
        "journey fix",
        "acct set",
        "snap live",
        "test user",
        "demo user",
    }
    if name in blocked_name_tokens:
        return True

    if len(name) < 3:
        return True

    return False


def _domain_terms(domain: str) -> List[str]:
    d = (domain or "").strip().lower()
    mapping = {
        "ai": ["ai", "artificial intelligence", "machine learning", "deep learning"],
        "robotics": ["robotics", "robot", "control", "automation", "cobot"],
        "semiconductor": ["semiconductor", "chip", "vlsi", "asic", "hardware"],
        "finance": ["finance", "fintech", "trading", "risk", "banking"],
        "healthcare": ["healthcare", "medical", "clinical", "biomedical"],
        "nlp": ["nlp", "natural language", "language model", "transformer", "text"],
        "computer-vision": ["computer vision", "vision", "image", "cnn", "detection"],
        "data-science": ["data science", "analytics", "statistics", "data"],
    }
    values = mapping.get(d, [d]) if d else []
    return [v for v in values if v]


def _text_contains_terms(text: str, terms: List[str]) -> bool:
    normalized = (text or "").strip().lower()
    return any(term in normalized for term in terms)


def _domain_course_ids(conn, domain: str) -> List[int]:
    terms = _domain_terms(domain)
    if not terms:
        return []
    rows = _fetchall(conn, "SELECT id, title, description FROM courses")
    matched: List[int] = []
    for row in rows:
        text = f"{row['title'] or ''} {row['description'] or ''}"
        if _text_contains_terms(text, terms):
            matched.append(int(row["id"]))
    return matched


def _user_domain_scores(conn, user_id: int, domains: List[str]) -> Dict[str, float]:
    contrib_rows = _fetchall(
        conn,
        """
        SELECT lower(domain) AS domain, COUNT(*) AS total,
               SUM(CASE WHEN final_status = 'VERIFIED' THEN 1 ELSE 0 END) AS verified
        FROM contributions
        WHERE user_id = ?
        GROUP BY lower(domain)
        """,
        (user_id,),
    )
    contrib_map = {
        str(row["domain"]): {
            "total": int(row["total"] or 0),
            "verified": int(row["verified"] or 0),
        }
        for row in contrib_rows
    }

    journey_rows = _fetchall(
        conn,
        """
        SELECT lower(domain) AS domain, COUNT(*) AS total,
               SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed
        FROM learning_journeys
        WHERE user_id = ?
        GROUP BY lower(domain)
        """,
        (user_id,),
    )
    journey_map = {
        str(row["domain"]): {
            "total": int(row["total"] or 0),
            "completed": int(row["completed"] or 0),
        }
        for row in journey_rows
    }

    scores: Dict[str, float] = {}
    for domain in domains:
        d = domain.strip().lower()
        score = 0.0

        c = contrib_map.get(d, {"total": 0, "verified": 0})
        score += c["total"] * 1.25
        score += c["verified"] * 2.8

        j = journey_map.get(d, {"total": 0, "completed": 0})
        score += j["total"] * 1.1
        score += j["completed"] * 1.6

        course_ids = _domain_course_ids(conn, d)
        if course_ids:
            placeholders = ",".join(["?"] * len(course_ids))
            params = [user_id] + course_ids
            attempts_row = _fetchone(
                conn,
                f"SELECT COUNT(*) AS total FROM quiz_attempts WHERE user_id = ? AND course_id IN ({placeholders})",
                tuple(params),
            )
            attempts = int(attempts_row["total"] or 0) if attempts_row else 0
            score += min(3.0, attempts / 8.0)

        scores[d] = round(score, 3)

    return scores


def _compute_user_reputation(conn, user_id: int, domain: str = "") -> Dict[str, Any]:
    domain_filter = domain.strip().lower()
    domain_clause = ""
    contrib_params: List[Any] = [user_id]
    if domain_filter:
        domain_clause = " AND lower(c.domain) = ? "
        contrib_params.append(domain_filter)

    course_ids: List[int] = _domain_course_ids(conn, domain_filter) if domain_filter else []

    mastery_avg_pct = 0.0
    if course_ids:
        placeholders = ",".join(["?"] * len(course_ids))
        params = [user_id] + course_ids
        mastery_row = _fetchone(
            conn,
            f"""
            SELECT AVG(mastery_score) AS avg_mastery
            FROM student_topic_state
            WHERE user_id = ? AND course_id IN ({placeholders})
            """,
            tuple(params),
        )
        mastery_avg_pct = round(float((mastery_row["avg_mastery"] or 0) * 100), 2) if mastery_row else 0.0
    else:
        mastery_row = _fetchone(
            conn,
            "SELECT AVG(mastery_score) AS avg_mastery FROM student_topic_state WHERE user_id = ?",
            (user_id,),
        )
        mastery_avg_pct = round(float((mastery_row["avg_mastery"] or 0) * 100), 2) if mastery_row else 0.0

    if course_ids:
        placeholders = ",".join(["?"] * len(course_ids))
        params = [user_id] + course_ids
        quiz_row = _fetchone(
            conn,
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct
            FROM quiz_attempts
            WHERE user_id = ? AND course_id IN ({placeholders})
            """,
            tuple(params),
        )
    else:
        quiz_row = _fetchone(
            conn,
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct
            FROM quiz_attempts
            WHERE user_id = ?
            """,
            (user_id,),
        )
    total_quiz = int(quiz_row["total"] or 0) if quiz_row else 0
    correct_quiz = int(quiz_row["correct"] or 0) if quiz_row else 0
    quiz_accuracy_pct = round((correct_quiz / max(1, total_quiz)) * 100, 2)

    contribution_row = _fetchone(
        conn,
        f"""
        SELECT
            COUNT(*) AS total_contrib,
            SUM(CASE WHEN final_status = 'VERIFIED' THEN 1 ELSE 0 END) AS verified_contrib,
            AVG(ai_novelty) AS avg_novelty,
            SUM(CASE WHEN final_status = 'VERIFIED' THEN snapscore_awarded ELSE 0 END) AS awarded
        FROM contributions c
        WHERE c.user_id = ?
        {domain_clause}
        """,
        tuple(contrib_params),
    )
    total_contrib = int(contribution_row["total_contrib"] or 0) if contribution_row else 0
    verified_contrib = int(contribution_row["verified_contrib"] or 0) if contribution_row else 0
    avg_novelty = float(contribution_row["avg_novelty"] or 0) if contribution_row else 0.0
    awarded = int(contribution_row["awarded"] or 0) if contribution_row else 0

    endorsement_row = _fetchone(
        conn,
        """
        SELECT COALESCE(SUM(weight), 0) AS endorsement_weight
        FROM contribution_endorsements ce
        JOIN contributions c ON c.id = ce.contribution_id
        WHERE c.user_id = ?
        """
        + (domain_clause if domain_clause else ""),
        tuple(contrib_params),
    )
    endorsement_weight = float(endorsement_row["endorsement_weight"] or 0) if endorsement_row else 0.0

    if domain_filter:
        journey_row = _fetchone(
            conn,
            """
            SELECT
                COUNT(*) AS total_journeys,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_journeys
            FROM learning_journeys
            WHERE user_id = ? AND lower(domain) = ?
            """,
            (user_id, domain_filter),
        )
    else:
        journey_row = _fetchone(
            conn,
            """
            SELECT
                COUNT(*) AS total_journeys,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_journeys
            FROM learning_journeys
            WHERE user_id = ?
            """,
            (user_id,),
        )
    total_journeys = int(journey_row["total_journeys"] or 0) if journey_row else 0
    completed_journeys = int(journey_row["completed_journeys"] or 0) if journey_row else 0

    total_projects = total_contrib + total_journeys
    done_projects = verified_contrib + completed_journeys
    project_completion_pct = round((done_projects / max(1, total_projects)) * 100, 2) if total_projects else 0.0
    peer_validation_pct = round(min(100.0, endorsement_weight * 12.5), 2)
    publication_originality_pct = round(avg_novelty, 2)
    contribution_impact_pct = round(min(100.0, ((awarded + endorsement_weight * 4) / max(1, total_contrib)) * 4.0), 2) if total_contrib else 0.0
    recent_activity_count = total_quiz + total_contrib + total_journeys + int(endorsement_weight)

    comp = reputation_components(
        {
            "mastery_avg_pct": mastery_avg_pct,
            "quiz_accuracy_pct": quiz_accuracy_pct,
            "project_completion_pct": project_completion_pct,
            "peer_validation_pct": peer_validation_pct,
            "publication_originality_pct": publication_originality_pct,
            "contribution_impact_pct": contribution_impact_pct,
            "recent_activity_count": recent_activity_count,
        }
    )

    return {
        "snapscore": comp["snapscore"],
        "components": comp,
        "totals": {
            "quiz_total": total_quiz,
            "contributions_total": total_contrib,
            "verified_contributions": verified_contrib,
            "journeys_total": total_journeys,
            "completed_journeys": completed_journeys,
            "endorsement_weight": round(endorsement_weight, 2),
        },
    }


def _can_human_verify(conn, user: Dict[str, Any]) -> bool:
    if user["role"] == "professor":
        return True
    rep = _compute_user_reputation(conn, int(user["id"]))
    return float(rep["snapscore"]) >= 70.0


def _build_workflow(document: Any, skill_map: List[Dict[str, Any]], questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_skills = len(skill_map)
    validated = sum(1 for item in skill_map if int(item.get("validated", 0)) == 1)
    total_questions = len(questions)
    approved = sum(1 for q in questions if int(q.get("approved", 0)) == 1)

    step1 = "Completed" if document else "Pending"
    step2 = "Completed" if total_skills > 0 else "Pending"
    if total_skills == 0:
        step3 = "Pending"
    elif validated == total_skills:
        step3 = "Completed"
    else:
        step3 = "In Progress"
    if total_questions == 0:
        step4 = "Pending"
    elif approved > 0:
        step4 = "Completed"
    else:
        step4 = "In Progress"

    progress = 0.0
    progress += 25 if step1 == "Completed" else 0
    progress += 25 if step2 == "Completed" else 0
    progress += 25 * (validated / max(1, total_skills)) if total_skills else 0
    progress += 25 * (approved / max(1, total_questions)) if total_questions else 0

    gap_closed = min(100.0, round(8 + (validated / max(1, total_skills)) * 52 + min(total_questions, 12) * 2.2, 1))
    improvement = min(100.0, round(6 + (approved / max(1, total_questions)) * 38 + min(validated, 10) * 3.3, 1))

    steps = [
        {"number": 1, "title": "Upload Course Docs", "status": step1},
        {"number": 2, "title": "Generate Skill Map", "status": step2},
        {"number": 3, "title": "Validate", "status": step3},
        {"number": 4, "title": "Generate Quiz Bank", "status": step4},
    ]

    return {
        "steps": steps,
        "progress_pct": int(round(progress)),
        "validated_count": validated,
        "total_skills": total_skills,
        "approved_count": approved,
        "total_questions": total_questions,
        "gap_closed_pct": gap_closed,
        "improvement_pct": improvement,
    }


def _risk_confidence(level: str, reason: str) -> int:
    base_map = {"LOW": 58, "MEDIUM": 71, "HIGH": 84}
    base = base_map.get(level.upper(), 62)
    spread = min(10, len(reason.strip()) // 24)
    return max(40, min(96, base + spread))


def _prepare_risk_flags(rows: List[Any]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        level = str(item.get("risk_level", "LOW")).upper()
        reason = str(item.get("reason", "") or "").strip()
        item["risk_level"] = level
        item["risk_level_class"] = level.lower()
        item["ai_confidence"] = _risk_confidence(level, reason)
        item["status_label"] = {
            "OPEN": "Keep AI Assessment",
            "MONITOR": "Monitor Closely",
            "DISMISSED": "Clear Risk",
            "RESOLVED": "Flag for Investigation Complete",
        }.get(str(item.get("status", "OPEN")).upper(), "Keep AI Assessment")
        prepared.append(item)
    return prepared


def _grade_confidence(score_percent: float, decision: str) -> int:
    spread = int(min(18, abs(score_percent - 50) / 3))
    pending_penalty = 7 if decision == "PENDING" else 0
    return max(45, min(96, 62 + spread - pending_penalty))


def _grade_reason(score_percent: float, ai_grade: str) -> str:
    if score_percent <= 1:
        return "No successful attempts recorded."
    if ai_grade in {"A", "B"}:
        return "Consistent strong performance across recent attempts."
    if ai_grade == "C":
        return "Mixed performance with partial mastery across topics."
    return "Low mastery trend detected in current assessment window."


def _prepare_grading_reviews(rows: List[Any]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        score = float(item.get("score_percent", 0) or 0)
        ai_grade = str(item.get("ai_recommended_grade", "F")).upper()
        decision = str(item.get("professor_decision", "PENDING")).upper()
        notes = str(item.get("professor_notes", "") or "")

        item["score_percent"] = score
        item["ai_recommended_grade"] = ai_grade
        item["professor_decision"] = decision
        item["ai_confidence"] = _grade_confidence(score, decision)
        item["ai_reason"] = _grade_reason(score, ai_grade)
        item["grade_class"] = "high" if ai_grade in {"A", "B"} else ("medium" if ai_grade == "C" else "low")
        manual_grade = ""
        for line in notes.splitlines():
            normalized = line.strip()
            if normalized.lower().startswith("override grade:"):
                candidate = normalized.split(":", 1)[1].strip().upper()
                if candidate in {"A", "B", "C", "D", "F"}:
                    manual_grade = candidate
                    break
        item["manual_grade"] = manual_grade
        prepared.append(item)
    return prepared


def _load_tutor_messages(conn, user_id: int, course_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    rows = _fetchall(
        conn,
        """
        SELECT * FROM chat_messages
        WHERE user_id = ? AND course_id = ?
        ORDER BY created_at ASC, id ASC
        LIMIT ?
        """,
        (user_id, course_id, limit),
    )
    parsed: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["citations"] = json.loads(item["citations_json"]) if item["citations_json"] else []
        parsed.append(item)
    return parsed


def _load_quiz_questions(conn, course_id: int, user_id: int, mode: str = "diagnostic") -> Dict[str, Any]:
    approved_rows = _fetchall(
        conn,
        "SELECT * FROM quiz_questions WHERE course_id = ? AND approved = 1",
        (course_id,),
    )
    draft_rows = _fetchall(
        conn,
        "SELECT * FROM quiz_questions WHERE course_id = ?",
        (course_id,),
    )

    if approved_rows:
        source_rows = approved_rows
        source_status = "approved"
    elif draft_rows:
        source_rows = draft_rows
        source_status = "draft"
    else:
        return {"questions": [], "source_status": "empty", "total_available": 0}

    topic_states = _fetchall(
        conn,
        "SELECT topic, mastery_score FROM student_topic_state WHERE user_id = ? AND course_id = ?",
        (user_id, course_id),
    )
    mastery_map = {row["topic"]: float(row["mastery_score"]) for row in topic_states}

    question_dicts = [dict(row) for row in source_rows]
    question_dicts.sort(key=lambda q: _question_priority(q, mastery_map))

    if mode == "targeted":
        selected = question_dicts[: min(8, len(question_dicts))]
    else:
        selected = question_dicts[: min(6, len(question_dicts))]

    questions: List[Dict[str, Any]] = []
    for row in selected:
        item = dict(row)
        try:
            options = json.loads(item["options_json"])
        except json.JSONDecodeError:
            options = [item["options_json"]]
        item["options"] = options
        questions.append(item)

    return {
        "questions": questions,
        "source_status": source_status,
        "total_available": len(source_rows),
    }


def _learning_state(conn, user_id: int, course_id: int) -> Dict[str, Any]:
    attempts_row = _fetchone(
        conn,
        "SELECT COUNT(*) AS total FROM quiz_attempts WHERE user_id = ? AND course_id = ?",
        (user_id, course_id),
    )
    attempts = int(attempts_row["total"]) if attempts_row else 0

    approved_row = _fetchone(
        conn,
        "SELECT COUNT(*) AS total FROM quiz_questions WHERE course_id = ? AND approved = 1",
        (course_id,),
    )
    approved_count = int(approved_row["total"]) if approved_row else 0

    draft_row = _fetchone(
        conn,
        "SELECT COUNT(*) AS total FROM quiz_questions WHERE course_id = ?",
        (course_id,),
    )
    draft_count = int(draft_row["total"]) if draft_row else 0

    low_mastery = _fetchone(
        conn,
        """
        SELECT topic, mastery_score
        FROM student_topic_state
        WHERE user_id = ? AND course_id = ?
        ORDER BY mastery_score ASC
        LIMIT 1
        """,
        (user_id, course_id),
    )

    if draft_count == 0:
        return {
            "state": "DIAGNOSTIC_ERROR",
            "label": "Quiz not ready",
            "reason": "No quiz bank available yet. Ask professor to generate or approve questions.",
            "cta_label": "Refresh Dashboard",
            "cta_href": f"/student/course/{course_id}/dashboard",
        }
    if attempts == 0:
        return {
            "state": "DIAGNOSTIC_READY",
            "label": "Diagnostic ready",
            "reason": "Start your first diagnostic to initialize mastery tracking.",
            "cta_label": "Start Diagnostic",
            "cta_href": f"/student/course/{course_id}/quiz?mode=diagnostic",
        }
    if low_mastery and float(low_mastery["mastery_score"]) < 0.65:
        return {
            "state": "DIAGNOSTIC_DONE",
            "label": "Targeted practice recommended",
            "reason": f"Your current weakest topic is {low_mastery['topic']}.",
            "cta_label": "Continue Learning",
            "cta_href": f"/student/course/{course_id}/quiz?mode=targeted",
        }

    return {
        "state": "DIAGNOSTIC_DONE",
        "label": "Learning loop active",
        "reason": "Keep momentum with another adaptive practice round.",
        "cta_label": "Continue Learning",
        "cta_href": f"/student/course/{course_id}/quiz?mode=targeted",
    }


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
    except Exception as exc:
        print(f"[startup] init_db failed: {exc}", flush=True)
        raise


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    if user["role"] == "professor":
        return RedirectResponse("/prof", status_code=303)
    return RedirectResponse("/student", status_code=303)


@app.get("/dashboard")
def dashboard_route(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect
    user = _current_user(request)
    if user["role"] == "professor":
        return RedirectResponse("/prof", status_code=303)
    return RedirectResponse("/student", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", _context(request, error=None))


@app.post("/register", response_class=HTMLResponse)
def register_action(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    learner_type: str = Form("student"),
    interest_domains: str = Form(""),
    goals: str = Form(""),
):
    if role not in {"student", "professor"}:
        return templates.TemplateResponse(
            "register.html",
            _context(request, error="Role must be student or professor."),
            status_code=400,
        )

    if _looks_like_non_real_account(full_name, email):
        return templates.TemplateResponse(
            "register.html",
            _context(request, error="Please register with a real name and institutional/personal email."),
            status_code=400,
        )

    conn = get_connection()
    try:
        existing = _fetchone(conn, "SELECT id FROM users WHERE email = ?", (email.lower(),))
        if existing:
            return templates.TemplateResponse(
                "register.html",
                _context(request, error="Email already registered."),
                status_code=400,
            )

        cursor = _execute(
            conn,
            """
            INSERT INTO users (full_name, email, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            (full_name.strip(), email.lower().strip(), hash_password(password), role),
        )
        user_id = int(cursor.lastrowid)

        profile_type = "professor" if role == "professor" else ("professional" if learner_type == "professional" else "student")
        domain_values = split_csv_values(interest_domains)
        goal_values = split_csv_values(goals)

        _execute(
            conn,
            """
            INSERT OR REPLACE INTO user_interest_profiles
            (user_id, user_type, domains_json, skill_level, goals_json, learning_style, time_commitment_min, updated_at)
            VALUES (?, ?, ?, 'intermediate', ?, 'projects', 60, CURRENT_TIMESTAMP)
            """,
            (
                user_id,
                profile_type,
                json.dumps(domain_values),
                json.dumps(goal_values),
            ),
        )
    finally:
        conn.close()

    return RedirectResponse("/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", _context(request, error=None))


@app.post("/login", response_class=HTMLResponse)
def login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    conn = get_connection()
    try:
        user = _fetchone(conn, "SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
    finally:
        conn.close()

    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            _context(request, error="Invalid credentials."),
            status_code=400,
        )

    request.session["user_id"] = user["id"]
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/prof", response_class=HTMLResponse)
def professor_home(request: Request):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        courses = _fetchall(
            conn,
            "SELECT * FROM courses WHERE professor_id = ? ORDER BY created_at DESC",
            (user["id"],),
        )
    finally:
        conn.close()

    return templates.TemplateResponse(
        "prof_home.html",
        _context(request, courses=courses),
    )


@app.post("/prof/courses/create")
def create_course(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        cursor = _execute(
            conn,
            """
            INSERT INTO courses (title, description, professor_id)
            VALUES (?, ?, ?)
            """,
            (title.strip(), description.strip(), user["id"]),
        )
        course_id = cursor.lastrowid
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=course_created", status_code=303)


@app.get("/prof/course/{course_id}", response_class=HTMLResponse)
def professor_course(request: Request, course_id: int):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        course = _fetchone(
            conn,
            "SELECT * FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not course:
            return RedirectResponse("/prof", status_code=303)

        document = _latest_course_document(conn, course_id)
        documents = _course_documents(conn, course_id)
        skill_rows = _fetchall(
            conn,
            "SELECT * FROM skill_map WHERE course_id = ? ORDER BY id ASC",
            (course_id,),
        )
        skill_map = _prepare_skill_map(skill_rows)
        questions_raw = _fetchall(
            conn,
            "SELECT * FROM quiz_questions WHERE course_id = ? ORDER BY created_at DESC, id DESC",
            (course_id,),
        )
        questions = []
        for row in questions_raw:
            item = dict(row)
            try:
                options = json.loads(item["options_json"])
            except json.JSONDecodeError:
                options = [item["options_json"]]
            item["options_text"] = "\n".join(options)
            questions.append(item)
        workflow = _build_workflow(document, skill_map, questions)
        skill_graph = _build_skill_graph(skill_map)
        risk_rows = _fetchall(
            conn,
            """
            SELECT rf.*, u.full_name AS student_name
            FROM risk_flags rf
            JOIN users u ON u.id = rf.user_id
            WHERE rf.course_id = ?
            ORDER BY rf.updated_at DESC
            """,
            (course_id,),
        )
        grading_rows = _fetchall(
            conn,
            """
            SELECT gr.*, u.full_name AS student_name
            FROM grading_reviews gr
            JOIN users u ON u.id = gr.user_id
            WHERE gr.course_id = ?
            ORDER BY gr.created_at DESC
            LIMIT 30
            """,
            (course_id,),
        )
        risk_flags = _prepare_risk_flags(risk_rows)
        grading_reviews = _prepare_grading_reviews(grading_rows)

        requested_risk_id = _safe_int(request.query_params.get("risk_selected"), 0)
        requested_grading_id = _safe_int(request.query_params.get("grading_selected"), 0)

        selected_risk = risk_flags[0] if risk_flags else None
        if requested_risk_id and risk_flags:
            for flag in risk_flags:
                if int(flag.get("id", 0)) == requested_risk_id:
                    selected_risk = flag
                    break

        selected_grading = grading_reviews[0] if grading_reviews else None
        if requested_grading_id and grading_reviews:
            for review in grading_reviews:
                if int(review.get("id", 0)) == requested_grading_id:
                    selected_grading = review
                    break
    finally:
        conn.close()

    return templates.TemplateResponse(
        "prof_course.html",
        _context(
            request,
            course=course,
            document=document,
            documents=documents,
            skill_map=skill_map,
            questions=questions,
            risk_flags=risk_flags,
            grading_reviews=grading_reviews,
            selected_risk=selected_risk,
            selected_grading=selected_grading,
            workflow=workflow,
            skill_graph=skill_graph,
            toast=request.query_params.get("toast", ""),
            improvement=request.query_params.get("improvement", ""),
        ),
    )


@app.post("/prof/course/{course_id}/upload-doc")
async def upload_document(request: Request, course_id: int, files: List[UploadFile] = File(...)):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        uploaded = [item for item in files if item and (item.filename or "").strip()]
        if not uploaded:
            return RedirectResponse(f"/prof/course/{course_id}", status_code=303)

        for file in uploaded:
            raw_bytes = await file.read()
            filename = file.filename or "uploaded_document"
            if filename.lower().endswith(".pdf"):
                raw_text = extract_text_from_pdf_bytes(raw_bytes)
            else:
                raw_text = raw_bytes.decode("utf-8", errors="ignore")

            if not raw_text.strip():
                raw_text = "Uploaded file did not contain extractable text."

            _execute(
                conn,
                """
                INSERT INTO course_documents (course_id, filename, raw_text)
                VALUES (?, ?, ?)
                """,
                (course_id, filename, raw_text),
            )

        # Recompute dependent artifacts after document updates.
        _execute(conn, "DELETE FROM skill_map WHERE course_id = ?", (course_id,))
        _execute(conn, "DELETE FROM quiz_questions WHERE course_id = ?", (course_id,))
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=doc_uploaded", status_code=303)


@app.post("/prof/course/{course_id}/document/{document_id}/delete")
def delete_document(request: Request, course_id: int, document_id: int):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        _execute(
            conn,
            "DELETE FROM course_documents WHERE id = ? AND course_id = ?",
            (document_id, course_id),
        )

        # Source corpus changed, force regeneration of dependent artifacts.
        _execute(conn, "DELETE FROM skill_map WHERE course_id = ?", (course_id,))
        _execute(conn, "DELETE FROM quiz_questions WHERE course_id = ?", (course_id,))
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=doc_removed", status_code=303)


@app.post("/prof/course/{course_id}/generate-skill-map")
def generate_skill_map(request: Request, course_id: int):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        source_text = _course_corpus_text(conn, course_id)
        if not source_text:
            return RedirectResponse(f"/prof/course/{course_id}", status_code=303)

        skill_nodes = llm_service.generate_skill_map(source_text, max_topics=10)
        _execute(conn, "DELETE FROM skill_map WHERE course_id = ?", (course_id,))
        for node in skill_nodes:
            _execute(
                conn,
                """
                INSERT INTO skill_map (course_id, topic, prerequisites_json, validated, professor_notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    course_id,
                    node["topic"],
                    json.dumps(node["prerequisites"]),
                    0,
                    str(node.get("reason", "")),
                ),
            )
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=skill_map_generated", status_code=303)


@app.post("/prof/course/{course_id}/skill-map/{skill_id}/update")
def update_skill_map_item(
    request: Request,
    course_id: int,
    skill_id: int,
    topic: str = Form(...),
    prerequisites: str = Form(""),
    validated: Optional[str] = Form(None),
    professor_notes: str = Form(""),
):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    prereq_list = [item.strip() for item in prerequisites.split(",") if item.strip()]

    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        _execute(
            conn,
            """
            UPDATE skill_map
            SET topic = ?, prerequisites_json = ?, validated = ?, professor_notes = ?
            WHERE id = ? AND course_id = ?
            """,
            (
                topic.strip(),
                json.dumps(prereq_list),
                1 if validated else 0,
                professor_notes.strip(),
                skill_id,
                course_id,
            ),
        )
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=skill_map_saved", status_code=303)


@app.post("/prof/course/{course_id}/skill-map/save-all")
async def save_skill_map_all(request: Request, course_id: int):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    form = await request.form()
    skill_ids_raw = str(form.get("skill_ids", "")).strip()
    skill_ids = [item.strip() for item in skill_ids_raw.split(",") if item.strip().isdigit()]

    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        for sid in skill_ids:
            skill_id = int(sid)
            topic = str(form.get(f"topic_{skill_id}", "")).strip()
            prereqs_raw = str(form.get(f"prerequisites_{skill_id}", "")).strip()
            prereq_list = [entry.strip() for entry in prereqs_raw.split(",") if entry.strip()]
            validated = 1 if str(form.get(f"validated_{skill_id}", "")) == "on" else 0
            notes = str(form.get(f"notes_{skill_id}", "")).strip()

            if not topic:
                continue

            _execute(
                conn,
                """
                UPDATE skill_map
                SET topic = ?, prerequisites_json = ?, validated = ?, professor_notes = ?
                WHERE id = ? AND course_id = ?
                """,
                (
                    topic,
                    json.dumps(prereq_list),
                    validated,
                    notes,
                    skill_id,
                    course_id,
                ),
            )
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=skill_map_saved", status_code=303)


@app.post("/prof/course/{course_id}/generate-quiz")
def generate_quiz_bank(
    request: Request,
    course_id: int,
    count: int = Form(8),
    difficulty: str = Form("Intermediate"),
    coverage_scope: str = Form("all"),
    blooms_level: str = Form("Apply"),
    selected_topics: str = Form(""),
):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        source_text = _course_corpus_text(conn, course_id)
        if not source_text:
            return RedirectResponse(f"/prof/course/{course_id}", status_code=303)

        validated_rows = _fetchall(
            conn,
            "SELECT topic FROM skill_map WHERE course_id = ? AND validated = 1",
            (course_id,),
        )
        all_rows = _fetchall(conn, "SELECT topic FROM skill_map WHERE course_id = ?", (course_id,))
        base_topics = [row["topic"] for row in (validated_rows or all_rows)]
        all_topics = [row["topic"] for row in all_rows]

        selected = [item.strip() for item in selected_topics.split(",") if item.strip()]
        if coverage_scope == "selected" and selected:
            selected_set = {item.lower() for item in selected}
            topics = [topic for topic in all_topics if topic.lower() in selected_set]
            if not topics:
                topics = base_topics
        else:
            topics = base_topics

        generated = llm_service.generate_quiz(
            source_text,
            topics,
            num_questions=max(3, min(count, 20)),
            difficulty=difficulty,
            blooms_level=blooms_level,
            coverage_scope=coverage_scope,
        )
        _execute(conn, "DELETE FROM quiz_questions WHERE course_id = ?", (course_id,))

        for question in generated:
            options = question.get("options") or []
            if len(options) < 4:
                continue
            if len(options) > 4:
                options = options[:4]
            _execute(
                conn,
                """
                INSERT INTO quiz_questions (
                    course_id, topic, question, options_json, correct_option,
                    explanation, source_chunk, approved, created_by_ai, professor_edited
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1, 0)
                """,
                (
                    course_id,
                    str(question.get("topic", "General")),
                    str(question.get("question", "Untitled question")),
                    json.dumps(options),
                    str(question.get("correct_option", options[0])),
                    str(question.get("explanation", "")),
                    str(question.get("source_chunk", "")),
                ),
            )
    finally:
        conn.close()

    improvement = min(100.0, round(8 + len(generated) * 4.5, 1))
    return RedirectResponse(
        f"/prof/course/{course_id}?toast=quiz_generated&improvement={improvement}",
        status_code=303,
    )


@app.post("/prof/course/{course_id}/question/{question_id}/update")
def update_question(
    request: Request,
    course_id: int,
    question_id: int,
    topic: str = Form(...),
    question: str = Form(...),
    options: str = Form(...),
    correct_option: str = Form(...),
    explanation: str = Form(""),
    source_chunk: str = Form(""),
    approved: Optional[str] = Form(None),
):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    parsed_options = _parse_options(options)
    if not parsed_options:
        parsed_options = [correct_option.strip()]

    if correct_option.strip() not in parsed_options:
        parsed_options[0] = correct_option.strip()

    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        _execute(
            conn,
            """
            UPDATE quiz_questions
            SET topic = ?, question = ?, options_json = ?, correct_option = ?,
                explanation = ?, source_chunk = ?, approved = ?, professor_edited = 1
            WHERE id = ? AND course_id = ?
            """,
            (
                topic.strip(),
                question.strip(),
                json.dumps(parsed_options),
                correct_option.strip(),
                explanation.strip(),
                source_chunk.strip(),
                1 if approved else 0,
                question_id,
                course_id,
            ),
        )
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=quiz_updated", status_code=303)


@app.post("/prof/course/{course_id}/risk/{risk_id}/override")
def override_risk(
    request: Request,
    course_id: int,
    risk_id: int,
    status: str = Form(...),
    note: str = Form(""),
    risk_selected: str = Form(""),
    grading_selected: str = Form(""),
):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    if status not in {"OPEN", "MONITOR", "DISMISSED", "RESOLVED"}:
        status = "OPEN"

    user = _current_user(request)
    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        _execute(
            conn,
            """
            UPDATE risk_flags
            SET status = ?, professor_override = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND course_id = ?
            """,
            (status, note.strip(), risk_id, course_id),
        )
    finally:
        conn.close()

    selected_risk = _safe_int(risk_selected, risk_id)
    selected_grading = _safe_int(grading_selected, 0)
    query = f"?toast=risk_updated&risk_selected={selected_risk}"
    if selected_grading:
        query += f"&grading_selected={selected_grading}"
    return RedirectResponse(f"/prof/course/{course_id}{query}", status_code=303)


@app.post("/prof/course/{course_id}/grading/{review_id}/decision")
def grading_decision(
    request: Request,
    course_id: int,
    review_id: int,
    decision: str = Form(""),
    override_grade: str = Form(""),
    notes: str = Form(""),
    risk_selected: str = Form(""),
    grading_selected: str = Form(""),
):
    redirect = _require_auth(request, role="professor")
    if redirect:
        return redirect

    user = _current_user(request)
    decision = decision.strip().upper()
    selected_risk = _safe_int(risk_selected, 0)
    selected_grading = _safe_int(grading_selected, review_id)

    query_suffix = f"&risk_selected={selected_risk}" if selected_risk else ""
    query_suffix += f"&grading_selected={selected_grading}" if selected_grading else ""

    if decision not in {"CONFIRMED", "OVERRIDDEN", "PENDING"}:
        return RedirectResponse(
            f"/prof/course/{course_id}?toast=grading_decision_required{query_suffix}",
            status_code=303,
        )

    override_grade = override_grade.strip().upper()
    if decision == "OVERRIDDEN" and override_grade not in {"A", "B", "C", "D", "F"}:
        return RedirectResponse(
            f"/prof/course/{course_id}?toast=override_grade_required{query_suffix}",
            status_code=303,
        )

    conn = get_connection()
    try:
        owned = _fetchone(
            conn,
            "SELECT id FROM courses WHERE id = ? AND professor_id = ?",
            (course_id, user["id"]),
        )
        if not owned:
            return RedirectResponse("/prof", status_code=303)

        final_notes = notes.strip()
        if decision == "OVERRIDDEN" and override_grade:
            prefix = f"Override Grade: {override_grade}"
            final_notes = f"{prefix}\n{final_notes}" if final_notes else prefix

        _execute(
            conn,
            """
            UPDATE grading_reviews
            SET professor_decision = ?, professor_notes = ?, reviewed_by = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND course_id = ?
            """,
            (decision, final_notes, user["id"], review_id, course_id),
        )
    finally:
        conn.close()

    return RedirectResponse(f"/prof/course/{course_id}?toast=grading_updated{query_suffix}", status_code=303)


@app.get("/student", response_class=HTMLResponse)
def student_home(request: Request):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        courses = _fetchall(
            conn,
            """
            SELECT c.*, u.full_name AS professor_name,
                   CASE WHEN e.id IS NULL THEN 0 ELSE 1 END AS enrolled
            FROM courses c
            JOIN users u ON u.id = c.professor_id
            LEFT JOIN enrollments e ON e.course_id = c.id AND e.user_id = ?
            ORDER BY c.created_at DESC
            """,
            (user["id"],),
        )
    finally:
        conn.close()

    return templates.TemplateResponse(
        "student_home.html",
        _context(request, courses=courses),
    )


@app.post("/student/enroll/{course_id}")
def enroll_course(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        exists = _fetchone(conn, "SELECT id FROM courses WHERE id = ?", (course_id,))
        if exists:
            _ensure_enrolled(conn, user["id"], course_id)
    finally:
        conn.close()

    return RedirectResponse(f"/student/course/{course_id}", status_code=303)


@app.get("/student/course/{course_id}", response_class=HTMLResponse)
def student_course(request: Request, course_id: int):
    return RedirectResponse(f"/student/course/{course_id}/dashboard", status_code=303)


@app.get("/student/course/{course_id}/quiz", response_class=HTMLResponse)
def take_quiz(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    mode = str(request.query_params.get("mode", "diagnostic")).strip().lower()
    if mode not in {"diagnostic", "targeted"}:
        mode = "diagnostic"

    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT * FROM courses WHERE id = ?", (course_id,))
        if not course:
            return RedirectResponse("/student", status_code=303)

        _ensure_enrolled(conn, user["id"], course_id)
        question_pack = _load_quiz_questions(conn, course_id, user["id"], mode=mode)
        questions = question_pack["questions"]
        source_status = question_pack["source_status"]
        tutor_messages = _load_tutor_messages(conn, user["id"], course_id, limit=40)
        has_document = bool(_latest_course_document(conn, course_id))
    finally:
        conn.close()

    return templates.TemplateResponse(
        "student_quiz.html",
        _context(
            request,
            course=course,
            questions=questions,
            started_at=int(time.time() * 1000),
            quiz_mode=mode,
            source_status=source_status,
            tutor_messages=tutor_messages,
            has_document=has_document,
            breadcrumbs=[
                {"label": "Course", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Dashboard", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Quiz", "href": f"/student/course/{course_id}/quiz?mode={mode}"},
            ],
        ),
    )


@app.post("/student/course/{course_id}/quiz/submit", response_class=HTMLResponse)
async def submit_quiz(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    form = await request.form()
    started_at = int(form.get("started_at", "0") or 0)
    quiz_mode = str(form.get("quiz_mode", "diagnostic")).strip().lower()
    if quiz_mode not in {"diagnostic", "targeted"}:
        quiz_mode = "diagnostic"
    now_ms = int(time.time() * 1000)

    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT * FROM courses WHERE id = ?", (course_id,))
        if not course:
            return RedirectResponse("/student", status_code=303)

        _ensure_enrolled(conn, user["id"], course_id)

        all_questions = _fetchall(
            conn,
            "SELECT * FROM quiz_questions WHERE course_id = ?",
            (course_id,),
        )
        question_map = {row["id"]: row for row in all_questions}

        pre_rows = _fetchall(
            conn,
            """
            SELECT topic, mastery_score
            FROM student_topic_state
            WHERE user_id = ? AND course_id = ?
            """,
            (user["id"], course_id),
        )
        pre_mastery = {row["topic"]: float(row["mastery_score"]) for row in pre_rows}
        pre_avg = sum(pre_mastery.values()) / max(1, len(pre_mastery)) if pre_mastery else 0.0

        answers: List[Dict[str, Any]] = []
        for key, value in form.multi_items():
            if not key.startswith("q_"):
                continue
            try:
                qid = int(key.split("_", 1)[1])
            except ValueError:
                continue
            question = question_map.get(qid)
            if not question:
                continue
            selected_option = str(value)
            is_correct = 1 if selected_option == question["correct_option"] else 0
            answers.append(
                {
                    "question": question,
                    "selected": selected_option,
                    "is_correct": is_correct,
                }
            )

        if not answers:
            return RedirectResponse(f"/student/course/{course_id}/quiz?mode={quiz_mode}", status_code=303)

        per_question_time = max(5000, (now_ms - started_at) // max(1, len(answers)))
        correct_count = 0
        mistake_breakdown: List[Dict[str, Any]] = []

        for answer in answers:
            q = answer["question"]
            correct_count += int(answer["is_correct"])

            if not answer["is_correct"]:
                mistake_breakdown.append(
                    {
                        "topic": q["topic"],
                        "question": q["question"],
                        "selected": answer["selected"],
                        "correct": q["correct_option"],
                        "explanation": q["explanation"],
                    }
                )

            _execute(
                conn,
                """
                INSERT INTO quiz_attempts (user_id, course_id, question_id, selected_option, is_correct, response_time_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"],
                    course_id,
                    q["id"],
                    answer["selected"],
                    answer["is_correct"],
                    per_question_time,
                ),
            )

            state = _fetchone(
                conn,
                """
                SELECT * FROM student_topic_state
                WHERE user_id = ? AND course_id = ? AND topic = ?
                """,
                (user["id"], course_id, q["topic"]),
            )

            if state:
                attempts = int(state["attempts"]) + 1
                correct = int(state["correct"]) + int(answer["is_correct"])
                total_response = int(state["total_response_time_ms"]) + per_question_time
                streak_wrong = 0 if answer["is_correct"] else int(state["streak_wrong"]) + 1
            else:
                attempts = 1
                correct = int(answer["is_correct"])
                total_response = per_question_time
                streak_wrong = 0 if answer["is_correct"] else 1

            updated = compute_topic_state(
                attempts=attempts,
                correct=correct,
                total_response_time_ms=total_response,
                streak_wrong=streak_wrong,
            )

            if state:
                _execute(
                    conn,
                    """
                    UPDATE student_topic_state
                    SET attempts = ?, correct = ?, total_response_time_ms = ?, streak_wrong = ?,
                        mastery_score = ?, struggle_score = ?, last_attempt_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        updated.attempts,
                        updated.correct,
                        updated.total_response_time_ms,
                        updated.streak_wrong,
                        updated.mastery_score,
                        updated.struggle_score,
                        state["id"],
                    ),
                )
            else:
                _execute(
                    conn,
                    """
                    INSERT INTO student_topic_state (
                        user_id, course_id, topic, attempts, correct, total_response_time_ms,
                        streak_wrong, mastery_score, struggle_score, last_attempt_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        user["id"],
                        course_id,
                        q["topic"],
                        updated.attempts,
                        updated.correct,
                        updated.total_response_time_ms,
                        updated.streak_wrong,
                        updated.mastery_score,
                        updated.struggle_score,
                    ),
                )

            existing_flag = _fetchone(
                conn,
                "SELECT id FROM risk_flags WHERE user_id = ? AND course_id = ? AND topic = ?",
                (user["id"], course_id, q["topic"]),
            )

            resolved_status = "RESOLVED" if updated.risk_level == "LOW" else "OPEN"
            if existing_flag:
                _execute(
                    conn,
                    """
                    UPDATE risk_flags
                    SET risk_level = ?, reason = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        updated.risk_level,
                        updated.risk_reason,
                        resolved_status,
                        existing_flag["id"],
                    ),
                )
            else:
                _execute(
                    conn,
                    """
                    INSERT INTO risk_flags (user_id, course_id, topic, risk_level, reason, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user["id"],
                        course_id,
                        q["topic"],
                        updated.risk_level,
                        updated.risk_reason,
                        resolved_status,
                    ),
                )

            delta = 5 if answer["is_correct"] else -2
            reason = f"Quiz attempt on {q['topic']}"
            _execute(
                conn,
                """
                INSERT INTO snapscore_events (user_id, course_id, delta, reason)
                VALUES (?, ?, ?, ?)
                """,
                (user["id"], course_id, delta, reason),
            )

        completion_bonus = 10
        _execute(
            conn,
            "INSERT INTO snapscore_events (user_id, course_id, delta, reason) VALUES (?, ?, ?, ?)",
            (user["id"], course_id, completion_bonus, "Quiz completion streak bonus"),
        )

        score_percent = round(100.0 * correct_count / max(1, len(answers)), 2)
        ai_grade = grade_band(score_percent)
        _execute(
            conn,
            """
            INSERT INTO grading_reviews (user_id, course_id, score_percent, ai_recommended_grade)
            VALUES (?, ?, ?, ?)
            """,
            (user["id"], course_id, score_percent, ai_grade),
        )

        recommendations_rows = _fetchall(
            conn,
            """
            SELECT topic, mastery_score
            FROM student_topic_state
            WHERE user_id = ? AND course_id = ?
            ORDER BY mastery_score ASC
            LIMIT 3
            """,
            (user["id"], course_id),
        )
        recommendations = [dict(row) for row in recommendations_rows]

        post_rows = _fetchall(
            conn,
            """
            SELECT topic, mastery_score
            FROM student_topic_state
            WHERE user_id = ? AND course_id = ?
            """,
            (user["id"], course_id),
        )
        post_mastery = {row["topic"]: float(row["mastery_score"]) for row in post_rows}
        post_avg = sum(post_mastery.values()) / max(1, len(post_mastery)) if post_mastery else 0.0
        improvement_pct = round((post_avg - pre_avg) * 100, 1)

        impacted_topics = sorted({a["question"]["topic"] for a in answers})
        skill_impacts = []
        for topic in impacted_topics:
            before = pre_mastery.get(topic, 0.5)
            after = post_mastery.get(topic, before)
            delta = round((after - before) * 100, 1)
            skill_impacts.append({"topic": topic, "delta": delta})

        snapscore = _snapscore_total(conn, user["id"], course_id)
        tutor_messages = _load_tutor_messages(conn, user["id"], course_id, limit=40)
        has_document = bool(_latest_course_document(conn, course_id))
    finally:
        conn.close()

    return templates.TemplateResponse(
        "student_quiz_result.html",
        _context(
            request,
            course=course,
            total_questions=len(answers),
            correct_count=correct_count,
            score_percent=score_percent,
            ai_grade=ai_grade,
            snapscore=snapscore,
            recommendations=recommendations,
            skill_impacts=skill_impacts,
            mistake_breakdown=mistake_breakdown,
            improvement_pct=improvement_pct,
            quiz_mode=quiz_mode,
            tutor_messages=tutor_messages,
            has_document=has_document,
            breadcrumbs=[
                {"label": "Course", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Dashboard", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Results", "href": f"/student/course/{course_id}/quiz/submit"},
            ],
        ),
    )


@app.get("/student/course/{course_id}/dashboard", response_class=HTMLResponse)
def student_dashboard(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT * FROM courses WHERE id = ?", (course_id,))
        if not course:
            return RedirectResponse("/student", status_code=303)

        _ensure_enrolled(conn, user["id"], course_id)
        document = _latest_course_document(conn, course_id)

        topic_state_rows = _fetchall(
            conn,
            """
            SELECT topic, attempts, correct, mastery_score, struggle_score, last_attempt_at
            FROM student_topic_state
            WHERE user_id = ? AND course_id = ?
            ORDER BY mastery_score ASC
            """,
            (user["id"], course_id),
        )
        topic_states = [dict(row) for row in topic_state_rows]

        open_flag_rows = _fetchall(
            conn,
            """
            SELECT topic, risk_level, reason, status, professor_override
            FROM risk_flags
            WHERE user_id = ? AND course_id = ?
            ORDER BY updated_at DESC
            """,
            (user["id"], course_id),
        )
        open_flags = [dict(row) for row in open_flag_rows]

        recent_attempt_rows = _fetchall(
            conn,
            """
            SELECT qa.created_at, qa.is_correct, qa.response_time_ms, qq.topic
            FROM quiz_attempts qa
            JOIN quiz_questions qq ON qq.id = qa.question_id
            WHERE qa.user_id = ? AND qa.course_id = ?
            ORDER BY qa.created_at DESC
            LIMIT 20
            """,
            (user["id"], course_id),
        )
        recent_attempts = [dict(row) for row in recent_attempt_rows]

        grading_rows = _fetchall(
            conn,
            """
            SELECT score_percent, ai_recommended_grade, professor_decision, professor_notes, created_at
            FROM grading_reviews
            WHERE user_id = ? AND course_id = ?
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (user["id"], course_id),
        )
        grading = [dict(row) for row in grading_rows]

        snapscore = _snapscore_total(conn, user["id"], course_id)
        autopilot_enabled = _autopilot_enabled(request, course_id)
        learning_state = _learning_state(conn, user["id"], course_id) if autopilot_enabled else _manual_learning_state(course_id)
        tutor_messages = _load_tutor_messages(conn, user["id"], course_id, limit=40)

        next_actions = []
        if autopilot_enabled:
            for state in topic_states[:3]:
                confidence = round(min(0.95, max(0.52, 0.55 + (1 - float(state["mastery_score"])) * 0.4)), 2)
                next_actions.append(
                    {
                        "topic": state["topic"],
                        "action": (
                            f"Review document sections on {state['topic']}, then retake a targeted quiz."
                        ),
                        "confidence": confidence,
                        "evidence": f"Attempts {state['attempts']}, Correct {state['correct']}, Mastery {(float(state['mastery_score']) * 100):.1f}%",
                    }
                )
            if not next_actions and document:
                next_actions.append(
                    {
                        "topic": "Course Foundations",
                        "action": "Start diagnostic quiz to establish your baseline mastery.",
                        "confidence": 0.63,
                        "evidence": "No prior attempts recorded.",
                    }
                )
        else:
            next_actions.extend(
                [
                    {
                        "topic": "Summary",
                        "action": "Generate course summary first, then choose one concept to relearn.",
                        "confidence": "Manual",
                        "evidence": "Autopilot is OFF. You choose sequence.",
                    },
                    {
                        "topic": "Relearn",
                        "action": "Open Relearn Concepts for your weakest topic and review solved examples.",
                        "confidence": "Manual",
                        "evidence": "Best for filling conceptual gaps.",
                    },
                    {
                        "topic": "Practice",
                        "action": "Run diagnostic or targeted quiz when you are ready to measure progress.",
                        "confidence": "Manual",
                        "evidence": "Assessment updates mastery and SnapScore.",
                    },
                ]
            )

        latest_attempt_by_topic: Dict[str, Dict[str, Any]] = {}
        for attempt in recent_attempts:
            topic = str(attempt.get("topic", "") or "").strip()
            if topic and topic not in latest_attempt_by_topic:
                latest_attempt_by_topic[topic] = attempt

        mastery_delta: List[Dict[str, Any]] = []
        for state in topic_states:
            topic = str(state.get("topic", "") or "")
            attempts = int(state.get("attempts", 0) or 0)
            correct = int(state.get("correct", 0) or 0)
            current_mastery = float(state.get("mastery_score", 0) or 0)
            if attempts <= 0:
                continue

            latest = latest_attempt_by_topic.get(topic)
            if latest is not None:
                latest_correct = int(latest.get("is_correct", 0) or 0)
                previous_attempts = max(0, attempts - 1)
                previous_correct = max(0, correct - (1 if latest_correct else 0))
            else:
                previous_attempts = max(0, attempts - 1)
                previous_correct = max(0, correct)

            previous_mastery = _mastery_from_counts(previous_attempts, previous_correct)
            delta_pct = round((current_mastery - previous_mastery) * 100, 1)

            mastery_delta.append(
                {
                    "topic": topic,
                    "before_pct": round(previous_mastery * 100, 1),
                    "after_pct": round(current_mastery * 100, 1),
                    "delta_pct": delta_pct,
                    "delta_sign": "+" if delta_pct >= 0 else "",
                }
            )

        mastery_delta.sort(key=lambda item: abs(float(item["delta_pct"])), reverse=True)
        mastery_delta = mastery_delta[:5]

        attempts_count = len(recent_attempts)
        worst_flag = None
        severity = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        for flag in open_flags:
            level = str(flag.get("risk_level", "LOW")).upper()
            if not worst_flag or severity.get(level, 0) > severity.get(str(worst_flag.get("risk_level", "LOW")).upper(), 0):
                worst_flag = flag

        weakest_state = topic_states[0] if topic_states else None
        weakest_topic = str(weakest_state.get("topic")) if weakest_state else "N/A"

        avg_resp_row = _fetchone(
            conn,
            """
            SELECT AVG(response_time_ms) AS avg_ms
            FROM quiz_attempts
            WHERE user_id = ? AND course_id = ?
            """,
            (user["id"], course_id),
        )
        overall_avg_ms = float(avg_resp_row["avg_ms"] or 0) if avg_resp_row else 0.0

        topic_perf = None
        if weakest_topic and weakest_topic != "N/A":
            topic_perf = _fetchone(
                conn,
                """
                SELECT
                    COUNT(*) AS total_attempts,
                    SUM(CASE WHEN qa.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_attempts,
                    AVG(qa.response_time_ms) AS avg_ms
                FROM quiz_attempts qa
                JOIN quiz_questions qq ON qq.id = qa.question_id
                WHERE qa.user_id = ? AND qa.course_id = ? AND qq.topic = ?
                """,
                (user["id"], course_id, weakest_topic),
            )

        wrong_attempts = int(topic_perf["wrong_attempts"] or 0) if topic_perf else 0
        topic_avg_ms = float(topic_perf["avg_ms"] or 0) if topic_perf else 0.0
        slow_factor = round((topic_avg_ms / overall_avg_ms), 1) if overall_avg_ms > 0 and topic_avg_ms > 0 else 1.0

        if attempts_count == 0:
            reasoning = "No attempts yet. Start diagnostic quiz so the system can identify gaps and personalize interventions."
        elif weakest_state:
            reasoning = (
                f"You answered {wrong_attempts} {weakest_topic} questions incorrectly "
                f"and took {slow_factor}x longer than your average. "
                f"The system prioritized this topic for the next intervention."
            )
        else:
            reasoning = "The system is tracking your latest attempts and reprioritizing topics by mastery and struggle."

        adaptive_state = {
            "engine_name": "Adaptive Learning State",
            "risk_level": str(worst_flag.get("risk_level", "LOW") if worst_flag else "LOW").upper(),
            "gap_topic": weakest_topic,
            "intervention_status": "Autopilot Active" if autopilot_enabled else "Manual Planning",
            "reassessment_cycle": "Reassesses after every quiz submission.",
            "reasoning": reasoning,
        }
    finally:
        conn.close()

    return templates.TemplateResponse(
        "student_dashboard.html",
        _context(
            request,
            course=course,
            topic_states=topic_states,
            open_flags=open_flags,
            recent_attempts=recent_attempts,
            grading=grading,
            snapscore=snapscore,
            next_actions=next_actions,
            learning_state=learning_state,
            autopilot_enabled=autopilot_enabled,
            adaptive_state=adaptive_state,
            mastery_delta=mastery_delta,
            has_document=bool(document),
            tutor_messages=tutor_messages,
            breadcrumbs=[
                {"label": "Course", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Dashboard", "href": f"/student/course/{course_id}/dashboard"},
            ],
        ),
    )


@app.post("/student/course/{course_id}/autopilot")
async def student_autopilot_toggle(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    content_type = (request.headers.get("content-type", "") or "").lower()
    enabled_raw: Any = ""
    if "application/json" in content_type:
        body = await request.json()
        enabled_raw = body.get("enabled", "")
    else:
        form = await request.form()
        enabled_raw = form.get("enabled", "")

    enabled = str(enabled_raw).strip().lower() in {"1", "true", "on", "yes"}

    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT id FROM courses WHERE id = ?", (course_id,))
        if not course:
            return JSONResponse({"ok": False, "error": "Course not found"}, status_code=404)
        _ensure_enrolled(conn, user["id"], course_id)
        learning_state = _learning_state(conn, user["id"], course_id) if enabled else _manual_learning_state(course_id)
    finally:
        conn.close()

    request.session[_session_autopilot_key(course_id)] = enabled

    return JSONResponse(
        {
            "ok": True,
            "enabled": enabled,
            "label": "Learning Autopilot ON" if enabled else "Learning Autopilot OFF",
            "learning_state": learning_state,
        }
    )


@app.get("/student/course/{course_id}/snapscore")
def student_snapscore_live(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    user = _current_user(request)
    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT id FROM courses WHERE id = ?", (course_id,))
        if not course:
            return JSONResponse({"ok": False, "error": "Course not found"}, status_code=404)
        _ensure_enrolled(conn, user["id"], course_id)
        breakdown = _course_snapscore_breakdown(conn, user["id"], course_id)
    finally:
        conn.close()

    return JSONResponse({"ok": True, **breakdown})


@app.get("/student/course/{course_id}/tutor", response_class=HTMLResponse)
def tutor_page(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT * FROM courses WHERE id = ?", (course_id,))
        if not course:
            return RedirectResponse("/student", status_code=303)

        _ensure_enrolled(conn, user["id"], course_id)

        parsed_messages = _load_tutor_messages(conn, user["id"], course_id, limit=80)
        document = _latest_course_document(conn, course_id)
    finally:
        conn.close()

    return templates.TemplateResponse(
        "student_tutor.html",
        _context(
            request,
            course=course,
            messages=parsed_messages,
            has_document=bool(document),
            breadcrumbs=[
                {"label": "Course", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Dashboard", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Tutor", "href": f"/student/course/{course_id}/tutor"},
            ],
        ),
    )


@app.get("/student/course/{course_id}/learning", response_class=HTMLResponse)
def student_learning_tools(request: Request, course_id: int):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT * FROM courses WHERE id = ?", (course_id,))
        if not course:
            return RedirectResponse("/student", status_code=303)

        _ensure_enrolled(conn, user["id"], course_id)
        document = _latest_course_document(conn, course_id)
        source_text = _course_corpus_text(conn, course_id)
        tutor_messages = _load_tutor_messages(conn, user["id"], course_id, limit=40)
    finally:
        conn.close()

    return templates.TemplateResponse(
        "student_learning.html",
        _context(
            request,
            course=course,
            has_document=bool(document),
            tutor_messages=tutor_messages,
            active_tool="summary",
            generated_content="",
            focus_topic="",
            example_count=3,
            breadcrumbs=[
                {"label": "Course", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Dashboard", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Learning Tools", "href": f"/student/course/{course_id}/learning"},
            ],
        ),
    )


@app.post("/student/course/{course_id}/learning", response_class=HTMLResponse)
def student_learning_generate(
    request: Request,
    course_id: int,
    action_type: str = Form(...),
    focus_topic: str = Form(""),
    example_count: int = Form(3),
):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    action = action_type.strip().lower()
    if action not in {"summary", "relearn", "examples"}:
        action = "summary"

    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT * FROM courses WHERE id = ?", (course_id,))
        if not course:
            return RedirectResponse("/student", status_code=303)

        _ensure_enrolled(conn, user["id"], course_id)
        document = _latest_course_document(conn, course_id)
        tutor_messages = _load_tutor_messages(conn, user["id"], course_id, limit=40)
    finally:
        conn.close()

    generated_content = ""
    error = ""
    if not document:
        error = "Course document is missing. Ask professor to upload course material first."
    else:
        if action == "summary":
            generated_content = llm_service.generate_course_summary(source_text, focus_topic=focus_topic)
        elif action == "relearn":
            generated_content = llm_service.relearn_concept(source_text, concept=focus_topic)
        else:
            generated_content = llm_service.generate_solved_examples(
                source_text,
                concept=focus_topic,
                num_examples=max(1, min(5, int(example_count))),
            )

    return templates.TemplateResponse(
        "student_learning.html",
        _context(
            request,
            course=course,
            has_document=bool(document),
            tutor_messages=tutor_messages,
            active_tool=action,
            generated_content=generated_content,
            focus_topic=focus_topic,
            example_count=max(1, min(5, int(example_count))),
            error=error,
            breadcrumbs=[
                {"label": "Course", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Dashboard", "href": f"/student/course/{course_id}/dashboard"},
                {"label": "Learning Tools", "href": f"/student/course/{course_id}/learning"},
            ],
        ),
    )


@app.post("/student/course/{course_id}/tutor")
def tutor_ask(
    request: Request,
    course_id: int,
    question: str = Form(...),
    return_to: str = Form(""),
):
    redirect = _require_auth(request, role="student")
    if redirect:
        return redirect

    user = _current_user(request)
    question = question.strip()
    if not question:
        fallback = return_to if return_to.startswith(f"/student/course/{course_id}/") else f"/student/course/{course_id}/tutor"
        return RedirectResponse(fallback, status_code=303)

    conn = get_connection()
    try:
        course = _fetchone(conn, "SELECT * FROM courses WHERE id = ?", (course_id,))
        if not course:
            return RedirectResponse("/student", status_code=303)

        _ensure_enrolled(conn, user["id"], course_id)

        source_text = _course_corpus_text(conn, course_id)
        chunks = split_into_chunks(source_text)
        retriever = LexicalRetriever(chunks)
        retrieved = retriever.search(question, top_k=3)

        answer = llm_service.chat(question, retrieved)
        citations = _extract_citations(retrieved)

        _execute(
            conn,
            """
            INSERT INTO chat_messages (user_id, course_id, role, message, citations_json)
            VALUES (?, ?, 'user', ?, '[]')
            """,
            (user["id"], course_id, question),
        )
        _execute(
            conn,
            """
            INSERT INTO chat_messages (user_id, course_id, role, message, citations_json)
            VALUES (?, ?, 'assistant', ?, ?)
            """,
            (user["id"], course_id, answer, json.dumps(citations)),
        )
    finally:
        conn.close()

    fallback = return_to if return_to.startswith(f"/student/course/{course_id}/") else f"/student/course/{course_id}/tutor"
    return RedirectResponse(fallback, status_code=303)


@app.get("/settings", response_class=HTMLResponse)
@app.get("/interests", response_class=HTMLResponse)
def interests_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        profile = _ensure_interest_profile(conn, user)
        domains = _load_domains(conn)
    finally:
        conn.close()

    return templates.TemplateResponse(
        "settings.html",
        _context(
            request,
            profile=profile,
            domains=domains,
        ),
    )


@app.post("/settings")
@app.post("/interests")
def interests_update(
    request: Request,
    user_type: str = Form("student"),
    domains: str = Form(""),
    skill_level: str = Form("intermediate"),
    goals: str = Form(""),
    learning_style: str = Form("projects"),
    time_commitment_min: int = Form(60),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    user_type = user_type.strip().lower()
    if user_type not in {"student", "professional", "professor"}:
        user_type = "student"

    skill_level = skill_level.strip().lower()
    if skill_level not in {"beginner", "intermediate", "advanced"}:
        skill_level = "intermediate"

    learning_style = learning_style.strip().lower()
    if learning_style not in {"projects", "quizzes", "reading"}:
        learning_style = "projects"

    clean_domains = split_csv_values(domains)
    clean_goals = split_csv_values(goals)

    conn = get_connection()
    try:
        _ensure_interest_profile(conn, user)
        _execute(
            conn,
            """
            UPDATE user_interest_profiles
            SET user_type = ?, domains_json = ?, skill_level = ?, goals_json = ?, learning_style = ?,
                time_commitment_min = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (
                user_type,
                json.dumps(clean_domains),
                skill_level,
                json.dumps(clean_goals),
                learning_style,
                max(15, min(600, int(time_commitment_min))),
                user["id"],
            ),
        )
    finally:
        conn.close()

    return RedirectResponse("/settings", status_code=303)


@app.get("/journeys", response_class=HTMLResponse)
def journey_hub(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        profile = _ensure_interest_profile(conn, user)
        domains = _load_domains(conn)
        journeys_rows = _fetchall(
            conn,
            """
            SELECT j.*, u.full_name AS owner_name
            FROM learning_journeys j
            JOIN users u ON u.id = j.user_id
            WHERE j.user_id = ? OR j.visibility = 'public'
            ORDER BY j.updated_at DESC, j.id DESC
            LIMIT 80
            """,
            (user["id"],),
        )
        journeys: List[Dict[str, Any]] = []
        for row in journeys_rows:
            item = dict(row)
            item["journey"] = _safe_json_load(str(item.get("journey_json", "{}")), {})
            cp_rows = _fetchall(
                conn,
                "SELECT * FROM journey_checkpoints WHERE journey_id = ? ORDER BY order_index ASC",
                (item["id"],),
            )
            item["checkpoints"] = [dict(cp) for cp in cp_rows]
            journeys.append(item)
    finally:
        conn.close()

    return templates.TemplateResponse(
        "journeys.html",
        _context(
            request,
            profile=profile,
            domains=domains,
            journeys=journeys,
        ),
    )


@app.post("/journeys/create")
def journey_create(
    request: Request,
    title: str = Form(...),
    domain: str = Form(...),
    goal_text: str = Form(...),
    learner_level: str = Form("intermediate"),
    visibility: str = Form("private"),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    level = learner_level.strip().lower()
    if level not in {"beginner", "intermediate", "advanced"}:
        level = "intermediate"
    vis = visibility.strip().lower()
    if vis not in {"private", "public"}:
        vis = "private"

    journey_obj = generate_journey_from_goal(goal_text, domain, learner_level=level)
    conn = get_connection()
    try:
        cursor = _execute(
            conn,
            """
            INSERT INTO learning_journeys
            (user_id, title, domain, source_type, source_text, learner_level, visibility, status, journey_json)
            VALUES (?, ?, ?, 'goal', ?, ?, ?, 'ACTIVE', ?)
            """,
            (
                user["id"],
                title.strip() or f"{domain.title()} Journey",
                domain.strip().lower(),
                goal_text.strip(),
                level,
                vis,
                json.dumps(journey_obj),
            ),
        )
        journey_id = int(cursor.lastrowid)

        milestones = journey_obj.get("milestones", [])
        for idx, milestone in enumerate(milestones):
            _execute(
                conn,
                """
                INSERT INTO journey_checkpoints (journey_id, milestone_title, order_index, status, evidence_text)
                VALUES (?, ?, ?, 'PENDING', '')
                """,
                (journey_id, str(milestone.get("title", f"Milestone {idx+1}")), idx + 1),
            )

        if vis == "public":
            _notify_domain_watchers(
                conn,
                domain.strip().lower(),
                f"New public journey: {title.strip()}",
                "A new AI-generated learning journey is available for collaboration and review.",
                link="/journeys",
            )
    finally:
        conn.close()

    return RedirectResponse("/journeys", status_code=303)


@app.post("/journeys/{journey_id}/checkpoint/{checkpoint_id}")
def journey_checkpoint_update(
    request: Request,
    journey_id: int,
    checkpoint_id: int,
    status: str = Form("PENDING"),
    evidence_text: str = Form(""),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    status = status.strip().upper()
    if status not in {"PENDING", "IN_PROGRESS", "DONE"}:
        status = "PENDING"

    conn = get_connection()
    try:
        journey = _fetchone(
            conn,
            "SELECT * FROM learning_journeys WHERE id = ?",
            (journey_id,),
        )
        if not journey:
            return RedirectResponse("/journeys", status_code=303)
        if int(journey["user_id"]) != int(user["id"]) and journey["visibility"] != "public":
            return RedirectResponse("/journeys", status_code=303)

        _execute(
            conn,
            """
            UPDATE journey_checkpoints
            SET status = ?, evidence_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND journey_id = ?
            """,
            (status, evidence_text.strip(), checkpoint_id, journey_id),
        )
        _execute(
            conn,
            "UPDATE learning_journeys SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (journey_id,),
        )
    finally:
        conn.close()

    return RedirectResponse("/journeys", status_code=303)


@app.post("/journeys/{journey_id}/final-project")
def journey_generate_final_project(
    request: Request,
    journey_id: int,
    visibility: str = Form("private"),
    is_open_source: str = Form(""),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    vis = visibility.strip().lower()
    if vis not in {"private", "public"}:
        vis = "private"
    open_src = 1 if str(is_open_source).strip().lower() in {"1", "true", "on", "yes"} else 0

    conn = get_connection()
    try:
        journey_row = _fetchone(conn, "SELECT * FROM learning_journeys WHERE id = ?", (journey_id,))
        if not journey_row:
            return RedirectResponse("/journeys", status_code=303)

        journey_data = _safe_json_load(str(journey_row["journey_json"]), {})
        final_project = journey_data.get("final_project") or {}
        domain_value = str(journey_row["domain"] or "ai").strip().lower()
        title = str(final_project.get("title") or f"{journey_row['title']} - Final Project").strip()
        objective = str(final_project.get("objective") or journey_row["source_text"]).strip()
        deliverables = final_project.get("deliverables") or []
        rubric = final_project.get("verification_rubric") or []

        content_text = "\n".join(
            [
                f"Objective: {objective}",
                "",
                "Deliverables:",
                *[f"- {str(item)}" for item in deliverables],
                "",
                "Verification Rubric:",
                *[f"- {str(item)}" for item in rubric],
                "",
                "Journey Source Goal:",
                str(journey_row["source_text"]),
            ]
        ).strip()

        refs_rows = _fetchall(
            conn,
            """
            SELECT content_text, summary
            FROM contributions
            WHERE user_id != ?
              AND lower(domain) = ?
            """,
            (user["id"], domain_value),
        )
        refs = []
        for row in refs_rows:
            text = (str(row["content_text"] or "") + "\n" + str(row["summary"] or "")).strip()
            if text:
                refs.append(text)

        pre = ai_preverify_contribution(content_text, refs)
        ai_status = pre["status"]
        final_status = "FLAGGED" if ai_status == "FLAGGED" else "AI_VERIFIED"

        _execute(
            conn,
            """
            INSERT INTO contributions
            (user_id, title, summary, domain, contribution_type, visibility, is_open_source,
             source_url, content_text, ai_similarity, ai_novelty, ai_factual_confidence,
             ai_status, human_status, final_status)
            VALUES (?, ?, ?, ?, 'project', ?, ?, '', ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                user["id"],
                title,
                objective,
                domain_value,
                vis,
                open_src,
                content_text,
                float(pre["similarity_pct"]),
                float(pre["novelty_pct"]),
                float(pre["factual_confidence_pct"]),
                ai_status,
                final_status,
            ),
        )

        if vis == "public":
            _notify_domain_watchers(
                conn,
                domain_value,
                f"New AI-generated final project draft: {title}",
                "A new project draft from learning journey is ready for review.",
                link="/contributions",
            )
    finally:
        conn.close()

    return RedirectResponse("/contributions", status_code=303)


@app.post("/journeys/{journey_id}/report-upload")
async def journey_upload_report(
    request: Request,
    journey_id: int,
    report_title: str = Form(""),
    summary: str = Form(""),
    visibility: str = Form("private"),
    is_open_source: str = Form(""),
    report_file: UploadFile = File(...),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    vis = visibility.strip().lower()
    if vis not in {"private", "public"}:
        vis = "private"
    open_src = 1 if str(is_open_source).strip().lower() in {"1", "true", "on", "yes"} else 0

    raw_bytes = await report_file.read()
    filename = report_file.filename or "project_report.txt"
    if filename.lower().endswith(".pdf"):
        report_text = extract_text_from_pdf_bytes(raw_bytes)
    else:
        report_text = raw_bytes.decode("utf-8", errors="ignore")
    report_text = report_text.strip() or "No extractable report text."

    conn = get_connection()
    try:
        journey_row = _fetchone(conn, "SELECT * FROM learning_journeys WHERE id = ?", (journey_id,))
        if not journey_row:
            return RedirectResponse("/journeys", status_code=303)
        if int(journey_row["user_id"]) != int(user["id"]):
            return RedirectResponse("/journeys", status_code=303)

        domain_value = str(journey_row["domain"] or "ai").strip().lower()
        title = report_title.strip() or f"{journey_row['title']} - Final Project Report"
        merged_content = f"{summary.strip()}\n\n{report_text}".strip()

        refs_rows = _fetchall(
            conn,
            """
            SELECT content_text, summary
            FROM contributions
            WHERE user_id != ?
              AND lower(domain) = ?
            """,
            (user["id"], domain_value),
        )
        refs = []
        for row in refs_rows:
            text = (str(row["content_text"] or "") + "\n" + str(row["summary"] or "")).strip()
            if text:
                refs.append(text)

        pre = ai_preverify_contribution(merged_content, refs)
        ai_status = pre["status"]
        final_status = "FLAGGED" if ai_status == "FLAGGED" else "AI_VERIFIED"

        _execute(
            conn,
            """
            INSERT INTO contributions
            (user_id, title, summary, domain, contribution_type, visibility, is_open_source,
             source_url, content_text, ai_similarity, ai_novelty, ai_factual_confidence,
             ai_status, human_status, final_status)
            VALUES (?, ?, ?, ?, 'final_project_report', ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                user["id"],
                title,
                summary.strip() or "Final project report submitted from journey.",
                domain_value,
                vis,
                open_src,
                filename,
                merged_content,
                float(pre["similarity_pct"]),
                float(pre["novelty_pct"]),
                float(pre["factual_confidence_pct"]),
                ai_status,
                final_status,
            ),
        )
    finally:
        conn.close()

    return RedirectResponse("/contributions", status_code=303)


@app.get("/contributions", response_class=HTMLResponse)
def contributions_hub(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        profile = _ensure_interest_profile(conn, user)
        domains = _load_domains(conn)

        rows = _fetchall(
            conn,
            """
            SELECT c.*, u.full_name AS owner_name
            FROM contributions c
            JOIN users u ON u.id = c.user_id
            WHERE c.user_id = ? OR c.visibility = 'public'
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT 120
            """,
            (user["id"],),
        )
        contributions = [dict(row) for row in rows]

        for item in contributions:
            item["outline"] = _safe_json_load(str(item.get("outline_json", "") or ""), {})
            item["outline_ready"] = bool(item["outline"])
            item["outline_course_id"] = int(item.get("outline_course_id") or 0)
            item["allow_course_conversion"] = int(item.get("allow_course_conversion", 0) or 0)
            is_owner = int(item["user_id"]) == int(user["id"])
            is_publication = str(item.get("contribution_type", "")).strip().lower() == "publication"
            item["can_generate_outline"] = is_owner and is_publication
            item["can_start_learning"] = item["outline_course_id"] > 0 and (item["visibility"] == "public" or int(item["user_id"]) == int(user["id"]))

            review_rows = _fetchall(
                conn,
                """
                SELECT cr.*, u.full_name AS reviewer_name
                FROM contribution_reviews cr
                JOIN users u ON u.id = cr.reviewer_user_id
                WHERE cr.contribution_id = ?
                ORDER BY cr.created_at DESC
                """,
                (item["id"],),
            )
            item["reviews"] = [dict(r) for r in review_rows]

        can_verify = _can_human_verify(conn, user)
    finally:
        conn.close()

    return templates.TemplateResponse(
        "contributions.html",
        _context(
            request,
            profile=profile,
            domains=domains,
            contributions=contributions,
            can_verify=can_verify,
        ),
    )


@app.post("/contributions/create")
def contribution_create(
    request: Request,
    title: str = Form(...),
    summary: str = Form(""),
    domain: str = Form("ai"),
    contribution_type: str = Form("project"),
    visibility: str = Form("private"),
    is_open_source: str = Form(""),
    allow_course_conversion: str = Form(""),
    source_url: str = Form(""),
    content_text: str = Form(""),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    ctype = contribution_type.strip().lower()
    if ctype not in {"project", "publication", "article", "open_source", "final_project_report"}:
        ctype = "project"
    vis = visibility.strip().lower()
    if vis not in {"private", "public"}:
        vis = "private"
    open_src = 1 if str(is_open_source).strip().lower() in {"1", "true", "on", "yes"} else 0
    wants_course = 1 if str(allow_course_conversion).strip().lower() in {"1", "true", "on", "yes"} else 0
    allow_course = 1 if (ctype == "publication" and wants_course == 1) else 0
    domain_value = domain.strip().lower() or "ai"
    merged_content = f"{summary.strip()}\n\n{content_text.strip()}".strip()

    conn = get_connection()
    try:
        ref_rows = _fetchall(
            conn,
            """
            SELECT content_text, summary
            FROM contributions
            WHERE final_status IN ('VERIFIED', 'AI_VERIFIED', 'PENDING', 'FLAGGED')
              AND user_id != ?
              AND lower(domain) = ?
            """,
            (user["id"], domain_value),
        )
        refs = []
        for row in ref_rows:
            text = (str(row["content_text"] or "") + "\n" + str(row["summary"] or "")).strip()
            if text:
                refs.append(text)

        pre = ai_preverify_contribution(merged_content, refs)
        ai_status = pre["status"]
        final_status = "FLAGGED" if ai_status == "FLAGGED" else "AI_VERIFIED"

        _execute(
            conn,
            """
            INSERT INTO contributions
            (user_id, title, summary, domain, contribution_type, visibility, is_open_source,
             source_url, content_text, allow_course_conversion, ai_similarity, ai_novelty, ai_factual_confidence,
             ai_status, human_status, final_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (
                user["id"],
                title.strip(),
                summary.strip(),
                domain_value,
                ctype,
                vis,
                open_src,
                source_url.strip(),
                merged_content,
                allow_course,
                float(pre["similarity_pct"]),
                float(pre["novelty_pct"]),
                float(pre["factual_confidence_pct"]),
                ai_status,
                final_status,
            ),
        )

        _notify_domain_watchers(
            conn,
            domain_value,
            f"New contribution: {title.strip()}",
            f"A new {ctype} contribution was published.",
            link="/contributions",
        )
    finally:
        conn.close()

    return RedirectResponse("/contributions", status_code=303)


@app.post("/contributions/{contribution_id}/review")
def contribution_review(
    request: Request,
    contribution_id: int,
    decision: str = Form(...),
    confidence_score: float = Form(0.7),
    notes: str = Form(""),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    decision_norm = decision.strip().upper()
    if decision_norm not in {"APPROVE", "REJECT"}:
        return RedirectResponse("/contributions", status_code=303)

    conn = get_connection()
    try:
        if not _can_human_verify(conn, user):
            return RedirectResponse("/contributions", status_code=303)

        item = _fetchone(conn, "SELECT * FROM contributions WHERE id = ?", (contribution_id,))
        if not item:
            return RedirectResponse("/contributions", status_code=303)

        _execute(
            conn,
            """
            INSERT INTO contribution_reviews (contribution_id, reviewer_user_id, decision, confidence_score, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                contribution_id,
                user["id"],
                decision_norm,
                max(0.0, min(1.0, float(confidence_score))),
                notes.strip(),
            ),
        )

        new_human = "APPROVED" if decision_norm == "APPROVE" else "REJECTED"
        new_final = "VERIFIED" if decision_norm == "APPROVE" else "REJECTED"

        award = int(item["snapscore_awarded"] or 0)
        if decision_norm == "APPROVE" and award <= 0:
            award = max(10, min(40, int(round(float(item["ai_novelty"] or 0) * 0.35))))

        _execute(
            conn,
            """
            UPDATE contributions
            SET human_status = ?, final_status = ?, snapscore_awarded = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (new_human, new_final, award, contribution_id),
        )

        _notify_user(
            conn,
            int(item["user_id"]),
            "verification",
            f"Contribution review: {item['title']}",
            f"Decision: {decision_norm}. {notes.strip() or ''}".strip(),
            link="/contributions",
        )
    finally:
        conn.close()

    return RedirectResponse("/contributions", status_code=303)


@app.post("/contributions/{contribution_id}/generate-outline")
def contribution_generate_outline(
    request: Request,
    contribution_id: int,
    make_course: str = Form(""),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        item = _fetchone(conn, "SELECT c.*, u.full_name AS owner_name FROM contributions c JOIN users u ON u.id = c.user_id WHERE c.id = ?", (contribution_id,))
        if not item:
            return RedirectResponse("/contributions", status_code=303)

        item = dict(item)
        if int(item["user_id"]) != int(user["id"]):
            return RedirectResponse("/contributions", status_code=303)

        if str(item.get("contribution_type", "")).strip().lower() != "publication":
            return RedirectResponse("/contributions", status_code=303)

        goal_text = item["summary"] or item["title"]
        if str(item.get("content_text", "")).strip():
            goal_text = f"{goal_text}. {str(item['content_text'])[:550]}"

        outline = generate_journey_from_goal(
            goal_text=goal_text,
            domain=str(item["domain"] or "ai"),
            learner_level="intermediate",
        )

        allow_conversion = int(item.get("allow_course_conversion", 0) or 0)
        request_make_course = str(make_course).strip().lower() in {"1", "true", "on", "yes"}
        should_make_course = allow_conversion == 1 and request_make_course
        course_id = None
        if should_make_course:
            owner_for_course = _resolve_publication_course_owner(conn, int(item["user_id"]))
            title = f"Publication Course: {str(item['title'])[:70]}"
            description = f"AI-generated learning path from publication by {item['owner_name']}."
            cursor = _execute(
                conn,
                """
                INSERT INTO courses (title, description, professor_id)
                VALUES (?, ?, ?)
                """,
                (title, description, owner_for_course),
            )
            course_id = int(cursor.lastrowid)
            _execute(
                conn,
                """
                INSERT INTO course_documents (course_id, filename, raw_text)
                VALUES (?, ?, ?)
                """,
                (course_id, f"outline_from_contribution_{item['id']}.txt", _outline_to_text(outline)),
            )

            _execute(
                conn,
                """
                INSERT INTO snapscore_events (user_id, course_id, delta, reason)
                VALUES (?, ?, ?, ?)
                """,
                (
                    int(item["user_id"]),
                    course_id,
                    8,
                    f"Published AI learning outline from contribution #{item['id']}",
                ),
            )

        _execute(
            conn,
            """
            UPDATE contributions
            SET outline_json = ?, outline_course_id = ?, outline_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (json.dumps(outline), course_id, contribution_id),
        )

        if should_make_course and course_id:
            _notify_domain_watchers(
                conn,
                str(item["domain"] or "ai"),
                f"New course from publication: {item['title']}",
                "AI generated a learning outline and converted it into a course.",
                link=f"/student/course/{course_id}/dashboard",
            )
    finally:
        conn.close()

    return RedirectResponse("/contributions", status_code=303)


@app.post("/contributions/{contribution_id}/start-learning")
def contribution_start_learning(
    request: Request,
    contribution_id: int,
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        item = _fetchone(conn, "SELECT * FROM contributions WHERE id = ?", (contribution_id,))
        if not item:
            return RedirectResponse("/contributions", status_code=303)

        contribution = dict(item)
        course_id = int(contribution.get("outline_course_id") or 0)
        if course_id <= 0:
            return RedirectResponse("/contributions", status_code=303)

        _ensure_enrolled(conn, int(user["id"]), course_id)
        _execute(
            conn,
            """
            INSERT INTO snapscore_events (user_id, course_id, delta, reason)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(user["id"]),
                course_id,
                5,
                f"Started learning from publication outline #{contribution_id}",
            ),
        )

        owner_id = int(contribution["user_id"])
        if owner_id != int(user["id"]):
            _execute(
                conn,
                """
                INSERT INTO snapscore_events (user_id, course_id, delta, reason)
                VALUES (?, ?, ?, ?)
                """,
                (
                    owner_id,
                    course_id,
                    3,
                    f"Student started your publication course #{contribution_id}",
                ),
            )
    finally:
        conn.close()

    return RedirectResponse(f"/student/course/{course_id}/dashboard", status_code=303)


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        profile = _ensure_interest_profile(conn, user)
        rep = _compute_user_reputation(conn, int(user["id"]))
        courses = _fetchall(
            conn,
            """
            SELECT c.id, c.title, c.description
            FROM courses c
            LEFT JOIN enrollments e ON e.course_id = c.id AND e.user_id = ?
            WHERE c.professor_id = ? OR e.id IS NOT NULL
            ORDER BY c.created_at DESC
            LIMIT 40
            """,
            (user["id"], user["id"]),
        )
        course_cards = []
        for c in courses:
            cid = int(c["id"])
            snap = _course_snapscore_breakdown(conn, int(user["id"]), cid) if user["role"] == "student" else None
            course_cards.append(
                {
                    "id": cid,
                    "title": c["title"],
                    "description": c["description"],
                    "snap": snap,
                }
            )
    finally:
        conn.close()

    return templates.TemplateResponse(
        "account.html",
        _context(
            request,
            profile=profile,
            reputation=rep,
            course_cards=course_cards,
        ),
    )


@app.post("/account/profile")
def account_update_profile(
    request: Request,
    full_name: str = Form(...),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        _execute(
            conn,
            "UPDATE users SET full_name = ? WHERE id = ?",
            (full_name.strip(), user["id"]),
        )
    finally:
        conn.close()
    return RedirectResponse("/account", status_code=303)


@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    domain = request.query_params.get("domain", "").strip().lower()
    conn = get_connection()
    try:
        users = _fetchall(conn, "SELECT id, full_name, email, role FROM users ORDER BY full_name ASC")
        domain_rows = _load_domains(conn)
        all_domain_slugs = [str(d["slug"]).strip().lower() for d in domain_rows]
        rows: List[Dict[str, Any]] = []
        for user_row in users:
            user_id = int(user_row["id"])
            if _looks_like_non_real_account(str(user_row["full_name"]), str(user_row["email"])):
                continue
            domain_scores = _user_domain_scores(conn, user_id, all_domain_slugs)
            primary_domain = ""
            primary_domain_score = 0.0
            for key, val in domain_scores.items():
                if val > primary_domain_score:
                    primary_domain = key
                    primary_domain_score = val

            if domain:
                selected_score = float(domain_scores.get(domain, 0.0))
                if selected_score <= 0:
                    continue
                rep = _compute_user_reputation(conn, user_id, domain=domain)
                snap = round(min(100.0, float(rep["snapscore"]) + min(12.0, selected_score * 1.2)), 2)
            else:
                rep = _compute_user_reputation(conn, user_id, domain="")
                snap = float(rep["snapscore"])

            totals = rep["totals"]
            activity_signal = (
                int(totals.get("quiz_total", 0))
                + int(totals.get("contributions_total", 0))
                + int(totals.get("journeys_total", 0))
                + int(round(float(totals.get("endorsement_weight", 0))))
            )
            if activity_signal <= 0 and snap < 5:
                continue

            rows.append(
                {
                    "user_id": user_id,
                    "name": str(user_row["full_name"]),
                    "role": str(user_row["role"]),
                    "snapscore": snap,
                    "components": rep["components"],
                    "totals": totals,
                    "primary_domain": primary_domain or "unclassified",
                    "primary_domain_score": round(primary_domain_score, 2),
                    "selected_domain_score": round(float(domain_scores.get(domain, 0.0)), 2) if domain else 0.0,
                    "activity_signal": activity_signal,
                }
            )

        if domain:
            rows.sort(
                key=lambda item: (float(item["snapscore"]), float(item["selected_domain_score"]), float(item["components"]["project_completion"])),
                reverse=True,
            )
        else:
            rows.sort(
                key=lambda item: (float(item["snapscore"]), float(item["primary_domain_score"])),
                reverse=True,
            )
        for idx, row in enumerate(rows):
            row["rank"] = idx + 1
        domains = domain_rows
    finally:
        conn.close()

    return templates.TemplateResponse(
        "leaderboard.html",
        _context(
            request,
            rows=rows[:200],
            domains=domains,
            selected_domain=domain,
        ),
    )


@app.get("/explore", response_class=HTMLResponse)
def explore_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    q = request.query_params.get("q", "").strip().lower()
    domain = request.query_params.get("domain", "").strip().lower()
    content_type = request.query_params.get("content_type", "").strip().lower()
    verified_only = request.query_params.get("verified_only", "").strip() in {"1", "true", "on"}
    sort_by = request.query_params.get("sort", "recommended").strip().lower()

    conn = get_connection()
    try:
        profile = _ensure_interest_profile(conn, user)
        domains = _load_domains(conn)
        items: List[Dict[str, Any]] = []

        journey_rows = _fetchall(
            conn,
            """
            SELECT j.id, j.title, j.domain, j.learner_level, j.visibility, j.status, j.updated_at, u.full_name AS owner_name
            FROM learning_journeys j
            JOIN users u ON u.id = j.user_id
            WHERE j.visibility = 'public' OR j.user_id = ?
            ORDER BY j.updated_at DESC
            LIMIT 200
            """,
            (user["id"],),
        )
        for row in journey_rows:
            item = dict(row)
            items.append(
                {
                    "kind": "journey",
                    "type": "journey",
                    "id": item["id"],
                    "title": item["title"],
                    "summary": f"Learning journey by {item['owner_name']} ({item['learner_level']}).",
                    "domain": str(item["domain"]).lower(),
                    "difficulty": str(item["learner_level"]).lower(),
                    "verified": item["status"] in {"ACTIVE", "COMPLETED"},
                    "link": "/journeys",
                    "tags": ["upskill", "learning-path"],
                    "updated_at": item["updated_at"],
                }
            )

        contrib_rows = _fetchall(
            conn,
            """
            SELECT c.id, c.title, c.summary, c.domain, c.contribution_type, c.final_status, c.ai_novelty, c.updated_at, u.full_name AS owner_name
            FROM contributions c
            JOIN users u ON u.id = c.user_id
            WHERE c.visibility = 'public' OR c.user_id = ?
            ORDER BY c.updated_at DESC
            LIMIT 300
            """,
            (user["id"],),
        )
        for row in contrib_rows:
            item = dict(row)
            items.append(
                {
                    "kind": "contribution",
                    "type": str(item["contribution_type"]).lower(),
                    "id": item["id"],
                    "title": item["title"],
                    "summary": f"{item['summary']} (by {item['owner_name']})",
                    "domain": str(item["domain"]).lower(),
                    "difficulty": "intermediate",
                    "verified": str(item["final_status"]).upper() == "VERIFIED",
                    "link": "/contributions",
                    "tags": ["research", "project", "job-ready", "publication"],
                    "updated_at": item["updated_at"],
                    "quality": float(item["ai_novelty"] or 0.0),
                }
            )

        update_rows = _fetchall(
            conn,
            """
            SELECT domain, title, summary, created_at
            FROM tech_updates
            ORDER BY created_at DESC
            LIMIT 120
            """,
        )
        for row in update_rows:
            item = dict(row)
            items.append(
                {
                    "kind": "update",
                    "type": "publication",
                    "id": 0,
                    "title": item["title"],
                    "summary": item["summary"],
                    "domain": str(item["domain"]).lower(),
                    "difficulty": "advanced",
                    "verified": True,
                    "link": "/notifications",
                    "tags": ["research", "trend"],
                    "updated_at": item["created_at"],
                }
            )

        def _passes_filters(item: Dict[str, Any]) -> bool:
            if domain and item.get("domain", "") != domain:
                return False
            if content_type and item.get("type", "") != content_type and item.get("kind", "") != content_type:
                return False
            if verified_only and not item.get("verified", False):
                return False
            if q:
                text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('domain', '')}".lower()
                if q not in text:
                    return False
            return True

        filtered = [item for item in items if _passes_filters(item)]

        for item in filtered:
            item["interest_score"] = interest_match_score(profile, item)
            freshness_boost = 0.0
            if str(item.get("updated_at", "")).strip():
                freshness_boost = 0.08
            quality = float(item.get("quality", 0.0))
            item["rank_score"] = round(item["interest_score"] + freshness_boost + min(0.2, quality / 500.0), 4)

        if sort_by == "newest":
            filtered.sort(key=lambda it: str(it.get("updated_at", "")), reverse=True)
        elif sort_by == "popular":
            filtered.sort(key=lambda it: float(it.get("quality", 0.0)), reverse=True)
        else:
            filtered.sort(key=lambda it: float(it.get("rank_score", 0.0)), reverse=True)
    finally:
        conn.close()

    return templates.TemplateResponse(
        "explore.html",
        _context(
            request,
            profile=profile,
            domains=domains,
            items=filtered[:240],
            filters={
                "q": q,
                "domain": domain,
                "content_type": content_type,
                "verified_only": verified_only,
                "sort": sort_by,
            },
        ),
    )


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    publish_feedback = request.session.pop("publish_feedback", None)
    update_form = request.session.get("updates_publish_draft", {})
    if not isinstance(update_form, dict):
        update_form = {}

    conn = get_connection()
    try:
        profile = _ensure_interest_profile(conn, user)
        domains = _load_domains(conn)
        user_count_row = _fetchone(conn, "SELECT COUNT(*) AS total FROM users")
        total_users = int(user_count_row["total"] or 0) if user_count_row else 0
        if not update_form.get("domain"):
            update_form["domain"] = (domains[0]["slug"] if domains else "ai")
        if not update_form.get("severity"):
            update_form["severity"] = "medium"

        rows = _fetchall(
            conn,
            """
            SELECT *
            FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 200
            """,
            (user["id"],),
        )
        notifications = [dict(row) for row in rows]
        unread = sum(1 for n in notifications if int(n.get("is_read", 0)) == 0)
    finally:
        conn.close()

    return templates.TemplateResponse(
        "notifications.html",
        _context(
            request,
            profile=profile,
            domains=domains,
            notifications=notifications,
            unread_count=unread,
            total_users=total_users,
            publish_feedback=publish_feedback,
            update_form=update_form,
        ),
    )


@app.post("/notifications/read-all")
def notifications_read_all(request: Request):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    conn = get_connection()
    try:
        _execute(conn, "UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user["id"],))
    finally:
        conn.close()
    return RedirectResponse("/notifications", status_code=303)


@app.post("/updates/publish")
def publish_tech_update(
    request: Request,
    domain: str = Form(...),
    title: str = Form(...),
    summary: str = Form(...),
    source_url: str = Form(""),
    severity: str = Form("medium"),
):
    redirect = _require_auth(request)
    if redirect:
        return redirect

    user = _current_user(request)
    sev = severity.strip().lower()
    if sev not in {"low", "medium", "high"}:
        sev = "medium"
    domain_value = domain.strip().lower() or "ai"
    clean_title = title.strip()
    clean_summary = summary.strip()
    clean_source = source_url.strip()

    request.session["updates_publish_draft"] = {
        "domain": domain_value,
        "severity": sev,
        "title": clean_title,
        "source_url": clean_source,
        "summary": clean_summary,
    }

    if not clean_title or not clean_summary:
        request.session["publish_feedback"] = {
            "level": "error",
            "message": "Title and summary are required. Your typed values were kept.",
        }
        return RedirectResponse("/notifications", status_code=303)

    conn = get_connection()
    try:
        _execute(
            conn,
            """
            INSERT INTO tech_updates (domain, title, summary, source_url, severity, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (domain_value, clean_title, clean_summary, clean_source, sev, user["id"]),
        )

        delivered_count = _notify_domain_watchers(
            conn,
            domain_value,
            f"Tech update: {clean_title}",
            clean_summary,
            link="/explore",
        )
        _notify_user(
            conn,
            int(user["id"]),
            "system",
            "Update published successfully",
            f"Your tech update was delivered to {delivered_count} inboxes.",
            link="/notifications",
        )
        request.session.pop("updates_publish_draft", None)
        request.session["publish_feedback"] = {
            "level": "success",
            "message": f"Submitted. Broadcast sent to {delivered_count} users.",
        }
    except Exception as exc:
        request.session["publish_feedback"] = {
            "level": "error",
            "message": f"Publish failed. Your typed values were kept. Error: {str(exc)[:140]}",
        }
    finally:
        conn.close()

    return RedirectResponse("/notifications", status_code=303)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "provider": settings.llm_provider}
