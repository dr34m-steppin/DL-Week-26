from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.ai_tutor import generate_micro_quiz
from src.learning_state import (
    build_student_insight,
    build_student_skill_summary,
    download_skillbuilder_dataset,
    load_skillbuilder_dataframe,
    preprocess_skillbuilder,
    add_time_decay_mastery,
)


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
OVERRIDE_FILE = DATA_DIR / "professor_overrides.json"


app = FastAPI(title="LearnLoop AI API", version="0.1.0")

events_df: Optional[pd.DataFrame] = None
summary_df: Optional[pd.DataFrame] = None


class LoadDatasetRequest(BaseModel):
    dataset_slug: str = "nicolaswattiez/skillbuilder-data-2009-2010"
    sample_rows: int = Field(default=200000, ge=1000)
    half_life_days: float = Field(default=21.0, gt=1.0, le=120.0)


class QuizRequest(BaseModel):
    skill: str
    gap_type: str = "Conceptual gap"
    context_snippets: List[str] = []


class OverrideRequest(BaseModel):
    user_id: int
    skill: str
    action: str = "override"
    decision: str
    note: str = ""


def _require_loaded() -> None:
    if events_df is None or summary_df is None:
        raise HTTPException(status_code=400, detail="Dataset not loaded. Call /load-dataset first.")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/load-dataset")
def load_dataset(req: LoadDatasetRequest) -> Dict[str, str]:
    global events_df, summary_df

    dataset_path = download_skillbuilder_dataset(req.dataset_slug)
    raw = load_skillbuilder_dataframe(dataset_path)
    if len(raw) > req.sample_rows:
        raw = raw.sample(req.sample_rows, random_state=42).copy()

    processed = preprocess_skillbuilder(raw)
    with_mastery = add_time_decay_mastery(processed, half_life_days=req.half_life_days)
    summary = build_student_skill_summary(with_mastery)

    events_df = with_mastery
    summary_df = summary

    return {
        "message": "Dataset loaded.",
        "rows": str(len(events_df)),
        "users": str(events_df["user_id"].nunique()),
        "skills": str(events_df["skill"].nunique()),
    }


@app.get("/students")
def list_students(limit: int = 25) -> Dict[str, List[int]]:
    _require_loaded()
    users = events_df["user_id"].dropna().astype(int).unique().tolist()  # type: ignore[index]
    users = sorted(users)[:limit]
    return {"user_ids": users}


@app.get("/student/{user_id}")
def get_student_insight(user_id: int, top_k: int = 5) -> Dict:
    _require_loaded()
    insight = build_student_insight(
        events_with_mastery=events_df,  # type: ignore[arg-type]
        summary_df=summary_df,  # type: ignore[arg-type]
        user_id=user_id,
        prereq_map={},
        top_k=top_k,
    )
    if len(insight.weak_skills) == 0:
        raise HTTPException(status_code=404, detail=f"No records found for user_id={user_id}")
    return {
        "user_id": insight.user_id,
        "snapscore": insight.snapscore,
        "weak_skills": insight.weak_skills,
        "recommendations": insight.recommendations,
    }


@app.post("/quiz")
def create_quiz(req: QuizRequest) -> Dict:
    quiz = generate_micro_quiz(
        skill=req.skill,
        gap_type=req.gap_type,
        context_snippets=req.context_snippets,
    )
    return {"quiz": quiz}


@app.post("/professor/override")
def professor_override(req: OverrideRequest) -> Dict[str, str]:
    row = req.model_dump()
    existing = []
    if OVERRIDE_FILE.exists():
        existing = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
    existing.append(row)
    OVERRIDE_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return {"message": "Override saved."}


@app.get("/professor/overrides")
def list_overrides() -> Dict[str, List[Dict]]:
    if not OVERRIDE_FILE.exists():
        return {"items": []}
    data = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
    return {"items": data}

