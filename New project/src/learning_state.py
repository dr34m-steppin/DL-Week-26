from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


DEFAULT_DATASET = "nicolaswattiez/skillbuilder-data-2009-2010"


@dataclass
class StudentInsight:
    user_id: int
    snapscore: float
    weak_skills: List[dict]
    recommendations: List[dict]


def download_skillbuilder_dataset(dataset_slug: str = DEFAULT_DATASET) -> Path:
    import kagglehub

    path = kagglehub.dataset_download(dataset_slug)
    return Path(path)


def _find_main_csv(dataset_path: Path) -> Path:
    csv_files = list(dataset_path.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {dataset_path}")
    return max(csv_files, key=lambda p: p.stat().st_size)


def load_skillbuilder_dataframe(dataset_path: Path | str) -> pd.DataFrame:
    dataset_path = Path(dataset_path)
    csv_path = _find_main_csv(dataset_path)
    df = pd.read_csv(csv_path, low_memory=False)
    return df


def preprocess_skillbuilder(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()

    if "problem_log_id" not in work.columns and "problemlogid" in work.columns:
        work["problem_log_id"] = work["problemlogid"]

    if "skill" not in work.columns:
        raise ValueError("Expected a 'skill' column in dataset.")
    if "correct" not in work.columns:
        raise ValueError("Expected a 'correct' column in dataset.")

    for col in ["start_time", "end_time", "first_action"]:
        if col in work.columns:
            work[col] = pd.to_datetime(work[col], errors="coerce")

    work["event_time"] = pd.NaT
    if "start_time" in work.columns:
        work["event_time"] = work["start_time"]
    if "end_time" in work.columns:
        work["event_time"] = work["event_time"].fillna(work["end_time"])
    if "first_action" in work.columns:
        work["event_time"] = work["event_time"].fillna(work["first_action"])

    for col in ["correct", "hint_count", "attempt_count", "ms_first_response", "actions"]:
        if col in work.columns:
            work[col] = pd.to_numeric(work[col], errors="coerce")

    work["correct"] = work["correct"].fillna(0).clip(0, 1)
    work["skill"] = work["skill"].fillna("UNKNOWN").astype(str).str.strip()
    work["user_id"] = pd.to_numeric(work["user_id"], errors="coerce")
    work = work.dropna(subset=["user_id"])
    work["user_id"] = work["user_id"].astype(int)

    for col in ["hint_count", "attempt_count", "ms_first_response", "actions"]:
        if col in work.columns:
            work[col] = work[col].fillna(0)
        else:
            work[col] = 0

    work = work.sort_values(["user_id", "event_time"], na_position="last").reset_index(drop=True)
    return work


def add_time_decay_mastery(df: pd.DataFrame, half_life_days: float = 21.0) -> pd.DataFrame:
    if half_life_days <= 0:
        raise ValueError("half_life_days must be > 0.")

    decay_lambda = np.log(2.0) / half_life_days
    records: List[Tuple[int, float]] = []

    grouped = df.groupby(["user_id", "skill"], sort=False)
    for (_, _), group in grouped:
        state = 0.0
        weight = 0.0
        prev_t = None

        for row in group.itertuples():
            curr_t = row.event_time
            if prev_t is not None and pd.notna(curr_t) and pd.notna(prev_t):
                dt_days = max((curr_t - prev_t).total_seconds() / 86400.0, 0.0)
                decay = np.exp(-decay_lambda * dt_days)
                state *= decay
                weight *= decay

            state += float(row.correct)
            weight += 1.0
            mastery = float(state / max(weight, 1e-6))
            records.append((row.Index, mastery))
            prev_t = curr_t

    mastery_series = pd.Series({idx: val for idx, val in records}, name="mastery")
    out = df.join(mastery_series, how="left")
    out["mastery"] = out["mastery"].fillna(out["correct"])
    return out


def _gap_type(accuracy: float, hints: float, attempts: float, response_ms: float) -> str:
    if accuracy < 0.45 and (hints >= 1.0 or attempts >= 2.0):
        return "Conceptual gap"
    if 0.45 <= accuracy < 0.70 and attempts >= 1.8:
        return "Procedure gap"
    if accuracy < 0.80 and response_ms > 0 and response_ms < 10000 and hints < 0.5:
        return "Careless mistakes"
    return "Stable"


def build_student_skill_summary(df: pd.DataFrame) -> pd.DataFrame:
    work = df.sort_values(["user_id", "skill", "event_time"])

    agg = (
        work.groupby(["user_id", "skill"], as_index=False)
        .agg(
            attempts=("correct", "size"),
            accuracy=("correct", "mean"),
            avg_hints=("hint_count", "mean"),
            avg_attempts=("attempt_count", "mean"),
            median_response_ms=("ms_first_response", "median"),
            last_mastery=("mastery", "last"),
            last_seen=("event_time", "max"),
        )
    )

    trend_records: List[Tuple[int, str, float]] = []
    for (uid, skill), group in work.groupby(["user_id", "skill"], sort=False):
        vals = group["correct"].astype(float).to_numpy()
        if len(vals) >= 10:
            prev = np.mean(vals[-10:-5])
            recent = np.mean(vals[-5:])
            trend = float(recent - prev)
        elif len(vals) >= 5:
            trend = float(np.mean(vals[-5:]) - np.mean(vals[:-5])) if len(vals[:-5]) > 0 else 0.0
        else:
            trend = 0.0
        trend_records.append((uid, skill, trend))

    trend_df = pd.DataFrame(trend_records, columns=["user_id", "skill", "trend"])
    summary = agg.merge(trend_df, on=["user_id", "skill"], how="left")
    summary["trend"] = summary["trend"].fillna(0.0)

    summary["gap_type"] = summary.apply(
        lambda r: _gap_type(
            float(r["accuracy"]),
            float(r["avg_hints"]),
            float(r["avg_attempts"]),
            float(r["median_response_ms"]) if pd.notna(r["median_response_ms"]) else 0.0,
        ),
        axis=1,
    )

    summary["priority_score"] = (
        (1.0 - summary["last_mastery"].fillna(summary["accuracy"]))
        + 0.15 * summary["avg_hints"].fillna(0.0)
        + 0.10 * summary["avg_attempts"].fillna(0.0)
        - 0.25 * summary["trend"].fillna(0.0)
    )
    return summary


def compute_snapscore(student_events: pd.DataFrame) -> float:
    if student_events.empty:
        return 40.0

    work = student_events.copy()
    work["day"] = work["event_time"].dt.date
    active_days = work["day"].dropna().nunique()
    accuracy = float(work["correct"].mean()) if "correct" in work.columns else 0.0
    consistency_bonus = min(active_days * 1.5, 18.0)
    performance_bonus = max((accuracy - 0.5) * 40.0, -10.0)

    last_seen = work["event_time"].max()
    inactivity_penalty = 0.0
    if pd.notna(last_seen):
        idle_days = max((pd.Timestamp.utcnow().tz_localize(None) - last_seen).days, 0)
        inactivity_penalty = min(max(idle_days - 7, 0) * 1.5, 20.0)

    score = 50.0 + consistency_bonus + performance_bonus - inactivity_penalty
    return float(np.clip(score, 0.0, 100.0))


def recommend_actions(
    summary_df: pd.DataFrame,
    user_id: int,
    prereq_map: Dict[str, List[str]] | None = None,
    top_k: int = 5,
) -> List[dict]:
    if prereq_map is None:
        prereq_map = {}

    user_rows = summary_df[summary_df["user_id"] == user_id].copy()
    if user_rows.empty:
        return []

    user_rows = user_rows.sort_values("priority_score", ascending=False).head(top_k)
    recs = []
    for row in user_rows.itertuples():
        prereqs = prereq_map.get(row.skill, [])
        recs.append(
            {
                "skill": row.skill,
                "gap_type": row.gap_type,
                "current_mastery": round(float(row.last_mastery), 3),
                "priority_score": round(float(row.priority_score), 3),
                "recommended_prerequisites": prereqs,
                "next_action": (
                    f"Practice 3 questions on {row.skill}"
                    if not prereqs
                    else f"Revise {', '.join(prereqs[:2])} then attempt 3 questions on {row.skill}"
                ),
            }
        )
    return recs


def build_student_insight(
    events_with_mastery: pd.DataFrame,
    summary_df: pd.DataFrame,
    user_id: int,
    prereq_map: Dict[str, List[str]] | None = None,
    top_k: int = 5,
) -> StudentInsight:
    user_events = events_with_mastery[events_with_mastery["user_id"] == user_id]
    user_summary = summary_df[summary_df["user_id"] == user_id].sort_values(
        "priority_score", ascending=False
    )
    weak_skills = user_summary.head(top_k).to_dict(orient="records")
    recommendations = recommend_actions(
        summary_df=summary_df, user_id=user_id, prereq_map=prereq_map, top_k=top_k
    )

    return StudentInsight(
        user_id=user_id,
        snapscore=round(compute_snapscore(user_events), 2),
        weak_skills=weak_skills,
        recommendations=recommendations,
    )


def append_quiz_result_and_recompute(
    events_df: pd.DataFrame,
    user_id: int,
    skill: str,
    score: float,
    half_life_days: float = 21.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Append one quiz interaction and recompute mastery + summary."""
    is_correct = 1.0 if score >= 60.0 else 0.0
    new_event = {
        "user_id": int(user_id),
        "skill": str(skill),
        "correct": float(is_correct),
        "hint_count": 0.0,
        "attempt_count": 1.0,
        "ms_first_response": 0.0,
        "actions": 1.0,
        "event_time": pd.Timestamp.utcnow().tz_localize(None),
    }

    updated = pd.concat([events_df, pd.DataFrame([new_event])], ignore_index=True)
    updated = updated.sort_values(["user_id", "event_time"], na_position="last").reset_index(drop=True)
    updated = add_time_decay_mastery(updated, half_life_days=half_life_days)
    summary = build_student_skill_summary(updated)
    return updated, summary
