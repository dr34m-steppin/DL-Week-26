# Google Colab Guide (Beginner -> Advanced)

This is a click-by-click path. Follow in order.
If you want one long end-to-end code block, use: [`COLAB_FULL_LOOP_CODE.py`](./COLAB_FULL_LOOP_CODE.py)

## 0) What to open first

1. Open [https://colab.research.google.com](https://colab.research.google.com)
2. Click `New Notebook`
3. Rename notebook to `DLW26_LearnLoop_MVP.ipynb`
4. Runtime: `CPU` is enough for MVP
5. Run each cell below top-to-bottom

---

## 1) Install packages

```python
!pip -q install kagglehub pandas numpy scikit-learn plotly openai
```

---

## 2) Download Kaggle dataset

```python
import kagglehub
from pathlib import Path
import pandas as pd

path = kagglehub.dataset_download("nicolaswattiez/skillbuilder-data-2009-2010")
dataset_path = Path(path)
print("Dataset path:", dataset_path)

csv_files = list(dataset_path.glob("*.csv"))
print("CSV files:", [f.name for f in csv_files])
main_csv = max(csv_files, key=lambda p: p.stat().st_size)
print("Main CSV:", main_csv.name)

df = pd.read_csv(main_csv, low_memory=False)
print("Shape:", df.shape)
print("Columns:", list(df.columns))
df.head(3)
```

---

## 3) Clean and prepare

```python
import numpy as np

work = df.copy()

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
    else:
        work[col] = 0

work["correct"] = work["correct"].fillna(0).clip(0, 1)
work["skill"] = work["skill"].fillna("UNKNOWN").astype(str).str.strip()
work["user_id"] = pd.to_numeric(work["user_id"], errors="coerce")
work = work.dropna(subset=["user_id"]).copy()
work["user_id"] = work["user_id"].astype(int)

for col in ["hint_count", "attempt_count", "ms_first_response", "actions"]:
    work[col] = work[col].fillna(0)

work = work.sort_values(["user_id", "event_time"], na_position="last").reset_index(drop=True)

print("Cleaned shape:", work.shape)
work[["user_id", "skill", "correct", "hint_count", "attempt_count", "event_time"]].head(5)
```

---

## 4) Build time-aware mastery model

This captures improvement + decay after inactivity.

```python
def add_time_decay_mastery(df, half_life_days=21.0):
    decay_lambda = np.log(2.0) / half_life_days
    records = []
    
    for (_, _), group in df.groupby(["user_id", "skill"], sort=False):
        state, weight = 0.0, 0.0
        prev_t = None
        for row in group.itertuples():
            t = row.event_time
            if prev_t is not None and pd.notna(t) and pd.notna(prev_t):
                dt_days = max((t - prev_t).total_seconds() / 86400.0, 0.0)
                decay = np.exp(-decay_lambda * dt_days)
                state *= decay
                weight *= decay

            state += float(row.correct)
            weight += 1.0
            mastery = state / max(weight, 1e-6)
            records.append((row.Index, mastery))
            prev_t = t
    
    mastery_series = pd.Series({idx: val for idx, val in records}, name="mastery")
    out = df.join(mastery_series, how="left")
    out["mastery"] = out["mastery"].fillna(out["correct"])
    return out

events = add_time_decay_mastery(work, half_life_days=21.0)
events[["user_id", "skill", "correct", "mastery"]].head(10)
```

---

## 5) Gap diagnosis + actionable summary

```python
def gap_type(accuracy, hints, attempts, response_ms):
    if accuracy < 0.45 and (hints >= 1.0 or attempts >= 2.0):
        return "Conceptual gap"
    if 0.45 <= accuracy < 0.70 and attempts >= 1.8:
        return "Procedure gap"
    if accuracy < 0.80 and response_ms > 0 and response_ms < 10000 and hints < 0.5:
        return "Careless mistakes"
    return "Stable"

summary = (
    events.groupby(["user_id", "skill"], as_index=False)
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

summary["gap_type"] = summary.apply(
    lambda r: gap_type(r["accuracy"], r["avg_hints"], r["avg_attempts"], r["median_response_ms"]),
    axis=1
)

summary["priority_score"] = (
    (1 - summary["last_mastery"])
    + 0.15 * summary["avg_hints"]
    + 0.10 * summary["avg_attempts"]
)

summary.head(10)
```

---

## 6) Student-level recommendations

```python
def snapscore(student_events):
    if student_events.empty:
        return 40.0
    active_days = student_events["event_time"].dt.date.dropna().nunique()
    accuracy = float(student_events["correct"].mean())
    consistency_bonus = min(active_days * 1.5, 18.0)
    performance_bonus = max((accuracy - 0.5) * 40.0, -10.0)
    last_seen = student_events["event_time"].max()
    inactivity_penalty = 0.0
    if pd.notna(last_seen):
        idle_days = max((pd.Timestamp.utcnow().tz_localize(None) - last_seen).days, 0)
        inactivity_penalty = min(max(idle_days - 7, 0) * 1.5, 20.0)
    score = 50 + consistency_bonus + performance_bonus - inactivity_penalty
    return float(np.clip(score, 0, 100))

sample_user = int(events["user_id"].iloc[0])
user_summary = summary[summary["user_id"] == sample_user].sort_values("priority_score", ascending=False)
user_events = events[events["user_id"] == sample_user]

print("User:", sample_user)
print("SnapScore:", round(snapscore(user_events), 2))
display(user_summary.head(8)[["skill", "attempts", "accuracy", "last_mastery", "gap_type", "priority_score"]])
```

---

## 7) Optional: LLM micro-quiz generation (OpenAI credits)

1. In Colab, click `Secrets` (left sidebar key icon).
2. Add secret named `OPENAI_API_KEY`.
3. Run:

```python
import os
import json
from openai import OpenAI
from google.colab import userdata

OPENAI_API_KEY = userdata.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

top_skill = user_summary.iloc[0]["skill"]
top_gap = user_summary.iloc[0]["gap_type"]

prompt = f"""
Create one targeted micro-quiz in strict JSON.
skill: {top_skill}
gap_type: {top_gap}
fields: question, options, answer, hint, explanation
Keep concise and educational.
"""

resp = client.chat.completions.create(
    model="gpt-4.1-mini",
    temperature=0.2,
    response_format={"type": "json_object"},
    messages=[
        {"role": "system", "content": "You create clear educational quizzes."},
        {"role": "user", "content": prompt},
    ],
)

quiz = json.loads(resp.choices[0].message.content)
quiz
```

---

## 8) Optional: Professor human-in-the-loop table

```python
prof_view = user_summary.head(10).copy()
prof_view["prof_decision"] = "pending"
prof_view["prof_note"] = ""
prof_view[["skill", "gap_type", "priority_score", "prof_decision", "prof_note"]].head(10)
```

For the live demo, say:
- AI suggests
- Professor validates/overrides
- Final recommendation is updated

---

## 9) Demo script you can speak

1. Student asks a doubt.
2. System diagnoses weak prerequisite skill.
3. System generates micro-quiz.
4. Student answers; mastery updates.
5. SnapScore changes.
6. Professor reviews risk flag and can override.

This directly matches judging criteria for personalization, interpretability, and human-in-the-loop.
