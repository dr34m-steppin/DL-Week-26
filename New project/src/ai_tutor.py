from __future__ import annotations

import json
import os
from typing import List

from openai import OpenAI


def _fallback_quiz(skill: str, gap_type: str, context_snippets: List[str]) -> dict:
    context = context_snippets[0][:280] if context_snippets else "Course context not provided."
    return {
        "skill": skill,
        "gap_type": gap_type,
        "question": f"Explain the key idea of {skill} and solve one example step-by-step.",
        "difficulty": "medium",
        "options": [],
        "answer_format": "Short answer with steps",
        "answer_key": f"A strong answer defines {skill}, explains steps, and gives a valid worked example.",
        "hint": f"Revisit prerequisite concepts before solving {skill}.",
        "explanation": "Use concept definition, method steps, and a worked example.",
        "sources": [context],
    }


def generate_micro_quiz(
    skill: str,
    gap_type: str,
    context_snippets: List[str] | None = None,
    model: str = "gpt-4.1-mini",
    openai_api_key: str | None = None,
) -> dict:
    context_snippets = context_snippets or []
    key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return _fallback_quiz(skill, gap_type, context_snippets)

    client = OpenAI(api_key=key)
    context_block = "\n\n".join([f"- {c}" for c in context_snippets[:3]]) or "- No external context provided."

    system_prompt = (
        "You are an educational assessment assistant. "
        "Return strict JSON with fields: "
        "skill, gap_type, question, difficulty, options, answer_format, answer_key, hint, explanation, sources. "
        "Keep question concise, avoid unsafe/biased content, and make explanation clear."
    )
    user_prompt = (
        f"Create one targeted micro-quiz.\n"
        f"Skill: {skill}\n"
        f"Gap type: {gap_type}\n"
        f"Context snippets:\n{context_block}\n"
        "Constraints:\n"
        "- If gap_type is Conceptual gap: ask conceptual reasoning.\n"
        "- If gap_type is Procedure gap: ask step-sequencing.\n"
        "- If gap_type is Careless mistakes: ask attention-check style question.\n"
        "- Include one short hint.\n"
        "- Include concise explanation.\n"
        "- Put context snippets used into sources list."
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = completion.choices[0].message.content or "{}"
        result = json.loads(content)
        required = [
            "skill",
            "gap_type",
            "question",
            "difficulty",
            "options",
            "answer_format",
            "answer_key",
            "hint",
            "explanation",
            "sources",
        ]
        for key_name in required:
            result.setdefault(key_name, "" if key_name not in ("options", "sources") else [])
        return result
    except Exception:
        return _fallback_quiz(skill, gap_type, context_snippets)


def answer_with_citations(
    question: str,
    retrieved_snippets: List[str],
    model: str = "gpt-4.1-mini",
    openai_api_key: str | None = None,
) -> dict:
    key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        if retrieved_snippets:
            answer = (
                "Based on the provided course material, start from the core definition, then "
                "apply the method step by step. See citations below."
            )
        else:
            answer = "No course context available yet. Upload material and try again."
        return {"answer": answer, "citations": retrieved_snippets[:3]}

    client = OpenAI(api_key=key)
    context_block = "\n\n".join([f"[{i+1}] {c}" for i, c in enumerate(retrieved_snippets[:4])])
    system_prompt = (
        "You are an academic tutor. Use only provided context. "
        "Return strict JSON with keys: answer, citations."
    )
    user_prompt = (
        f"Student question: {question}\n\n"
        f"Context snippets:\n{context_block}\n\n"
        "Rules:\n"
        "- Explain clearly in <=120 words.\n"
        "- If context is insufficient, say what is missing.\n"
        "- Return citations as list entries tied to snippets."
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
        payload.setdefault("answer", "No answer generated.")
        payload.setdefault("citations", retrieved_snippets[:3])
        return payload
    except Exception:
        return {
            "answer": "I could not call the model. Using retrieved context only.",
            "citations": retrieved_snippets[:3],
        }


def auto_grade_answer(
    question: str,
    answer_key: str,
    student_answer: str,
    model: str = "gpt-4.1-mini",
    openai_api_key: str | None = None,
) -> dict:
    key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        key_terms = set([w.lower() for w in answer_key.split() if len(w) > 4])
        student_terms = set(student_answer.lower().split())
        overlap = len(key_terms & student_terms)
        score = min(100, max(0, int(40 + overlap * 8)))
        return {
            "score": score,
            "is_correct": score >= 60,
            "feedback": "Heuristic grading used because API key is missing.",
        }

    client = OpenAI(api_key=key)
    system_prompt = (
        "You are a strict but fair grader. Return strict JSON with keys: score, is_correct, feedback. "
        "score is integer 0-100."
    )
    user_prompt = (
        f"Question: {question}\n"
        f"Reference answer: {answer_key}\n"
        f"Student answer: {student_answer}\n"
        "Grade for conceptual correctness and reasoning clarity."
    )
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        out = json.loads(resp.choices[0].message.content or "{}")
        score = int(out.get("score", 0))
        score = max(0, min(100, score))
        return {
            "score": score,
            "is_correct": bool(out.get("is_correct", score >= 60)),
            "feedback": str(out.get("feedback", "")),
        }
    except Exception:
        return {
            "score": 50,
            "is_correct": False,
            "feedback": "Auto-grading fallback used due to API/model issue.",
        }
