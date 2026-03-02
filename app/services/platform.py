import json
import math
import re
from typing import Any, Dict, List, Tuple


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> List[str]:
    return [tok for tok in re.findall(r"[a-z0-9]+", _normalize_text(text)) if tok]


def _token_set(text: str) -> set:
    return set(_tokens(text))


def jaccard_similarity(a: str, b: str) -> float:
    sa = _token_set(a)
    sb = _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa.intersection(sb)) / len(sa.union(sb))


def ai_preverify_contribution(content: str, reference_texts: List[str]) -> Dict[str, Any]:
    best_similarity = 0.0
    for ref in reference_texts:
        sim = jaccard_similarity(content, ref)
        if sim > best_similarity:
            best_similarity = sim

    similarity_pct = round(best_similarity * 100, 1)
    novelty_pct = round(max(0.0, 100.0 - similarity_pct), 1)

    content_tokens = _tokens(content)
    token_count = len(content_tokens)
    unique_ratio = (len(set(content_tokens)) / max(1, token_count)) if token_count else 0.0

    factual_conf = 45.0
    if token_count >= 180:
        factual_conf += 18
    if token_count >= 420:
        factual_conf += 10
    factual_conf += min(12.0, unique_ratio * 20)
    factual_conf = round(min(96.0, factual_conf), 1)

    status = "FLAGGED" if similarity_pct > 40.0 else "PASS"
    reason = (
        f"Similarity {similarity_pct}% exceeds threshold (40%). Needs human review."
        if status == "FLAGGED"
        else "AI pre-verification passed for similarity threshold."
    )

    return {
        "similarity_pct": similarity_pct,
        "novelty_pct": novelty_pct,
        "factual_confidence_pct": factual_conf,
        "status": status,
        "reason": reason,
    }


def _unique_ordered(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        norm = value.strip().lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(value.strip())
    return out


def generate_journey_from_goal(goal_text: str, domain: str, learner_level: str = "intermediate") -> Dict[str, Any]:
    text = (goal_text or "").strip()
    if not text:
        text = f"Build practical capability in {domain}."

    level_hint = (learner_level or "intermediate").strip().lower()
    pacing = "steady"
    if level_hint == "beginner":
        pacing = "guided"
    elif level_hint == "advanced":
        pacing = "accelerated"

    key_terms = _unique_ordered([t.capitalize() for t in _tokens(text)[:12]])
    if not key_terms:
        key_terms = [domain, "Foundations", "Evaluation"]

    foundations = _unique_ordered(
        [
            f"{domain} foundations",
            "Core concepts and terminology",
            "Data handling fundamentals",
            "Evaluation metrics",
        ]
        + key_terms[:2]
    )[:5]

    intermediate = _unique_ordered(
        [
            "Applied problem decomposition",
            "Modeling and implementation workflow",
            "Error analysis and optimization",
            "Robustness and fairness checks",
        ]
        + key_terms[2:6]
    )[:5]

    applied = _unique_ordered(
        [
            "Production-style project implementation",
            "Performance validation benchmark",
            "Documentation and reproducibility",
            "Impact and risk review",
        ]
        + key_terms[6:10]
    )[:5]

    milestones = [
        {
            "title": "Milestone 1: Baseline readiness",
            "description": "Finish foundational modules and pass a baseline diagnostic.",
            "checkpoint": "Diagnostic score >= 60%",
        },
        {
            "title": "Milestone 2: Applied prototype",
            "description": "Build a working prototype aligned with the goal statement.",
            "checkpoint": "Prototype demo + test evidence submitted",
        },
        {
            "title": "Milestone 3: Verified contribution",
            "description": "Publish project write-up and complete verification cycle.",
            "checkpoint": "AI pre-check + human review approved",
        },
    ]

    modules = [
        {"phase": "Foundational Knowledge", "items": foundations},
        {"phase": "Intermediate Knowledge", "items": intermediate},
        {"phase": "Applied Skills", "items": applied},
    ]

    return {
        "goal": text,
        "domain": domain,
        "learner_level": learner_level,
        "pacing": pacing,
        "modules": modules,
        "milestones": milestones,
        "micro_projects": [
            "Create a focused mini-implementation for one core concept.",
            "Run an ablation or comparison and document tradeoffs.",
            "Ship a public or private contribution with verification metadata.",
        ],
        "verification_checkpoints": [
            "Prerequisite quiz completion",
            "Milestone artifact review",
            "Contribution originality verification",
        ],
        "final_project": {
            "title": f"{domain.title()} Final Project: {text[:72]}".strip(),
            "objective": f"Deliver a validated end-to-end solution aligned with goal: {text}",
            "deliverables": [
                "Architecture diagram and technical design notes",
                "Implementation artifact (code/notebook/prototype)",
                "Evaluation report with metrics and limitations",
                "Risk and fairness review",
                "Publication-ready summary",
            ],
            "verification_rubric": [
                "Technical correctness",
                "Originality and novelty",
                "Reproducibility and evidence",
                "Real-world impact",
            ],
        },
    }


def interest_match_score(profile: Dict[str, Any], item: Dict[str, Any]) -> float:
    user_domains = {d.strip().lower() for d in profile.get("domains", []) if d.strip()}
    user_goals = {g.strip().lower() for g in profile.get("goals", []) if g.strip()}
    level = str(profile.get("skill_level", "intermediate")).strip().lower()
    style = str(profile.get("learning_style", "projects")).strip().lower()

    item_domain = str(item.get("domain", "")).strip().lower()
    item_type = str(item.get("type", "")).strip().lower()
    item_difficulty = str(item.get("difficulty", "intermediate")).strip().lower()
    tags = {t.strip().lower() for t in item.get("tags", []) if t.strip()}

    score = 0.0
    if item_domain and item_domain in user_domains:
        score += 0.45
    elif item_domain:
        score += 0.12

    if item_difficulty == level:
        score += 0.2
    elif {item_difficulty, level} <= {"beginner", "intermediate"} or {item_difficulty, level} <= {"intermediate", "advanced"}:
        score += 0.12

    if style == "projects" and item_type in {"project", "journey"}:
        score += 0.15
    elif style == "quizzes" and item_type in {"quiz", "journey"}:
        score += 0.15
    elif style == "reading" and item_type in {"publication", "summary"}:
        score += 0.15

    if user_goals.intersection(tags):
        score += 0.2

    return round(min(1.0, score), 4)


def reputation_components(metrics: Dict[str, float]) -> Dict[str, float]:
    mastery = float(metrics.get("mastery_avg_pct", 0.0))
    quiz_accuracy = float(metrics.get("quiz_accuracy_pct", 0.0))
    project_completion = float(metrics.get("project_completion_pct", 0.0))
    peer_validation = float(metrics.get("peer_validation_pct", 0.0))
    originality = float(metrics.get("publication_originality_pct", 0.0))
    impact = float(metrics.get("contribution_impact_pct", 0.0))

    weighted = (
        mastery * 0.24
        + quiz_accuracy * 0.16
        + project_completion * 0.18
        + peer_validation * 0.14
        + originality * 0.14
        + impact * 0.14
    )

    trend_boost = min(6.0, math.log1p(max(0.0, float(metrics.get("recent_activity_count", 0.0)))) * 2.2)
    snapscore = round(min(100.0, weighted + trend_boost), 2)

    return {
        "mastery": round(mastery, 2),
        "quiz_accuracy": round(quiz_accuracy, 2),
        "project_completion": round(project_completion, 2),
        "peer_validation": round(peer_validation, 2),
        "originality": round(originality, 2),
        "impact": round(impact, 2),
        "trend_boost": round(trend_boost, 2),
        "snapscore": snapscore,
    }


def split_csv_values(raw: str) -> List[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def parse_json_list(raw: str, fallback: List[str] | None = None) -> List[str]:
    fallback = fallback or []
    if not raw:
        return fallback
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return fallback
