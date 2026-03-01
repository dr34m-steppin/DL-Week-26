# Cell 1: Install dependencies
# !pip -q install kagglehub pandas numpy scikit-learn plotly openai pypdf

# Cell 2: Imports
import io
import json
import re
from pathlib import Path

import kagglehub
import numpy as np
import pandas as pd
from pypdf import PdfReader

try:
    from google.colab import files  # type: ignore
except Exception:
    files = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# Cell 3: Download dataset
path = kagglehub.dataset_download("nicolaswattiez/skillbuilder-data-2009-2010")
dataset_path = Path(path)
csv_files = list(dataset_path.glob("*.csv"))
main_csv = max(csv_files, key=lambda p: p.stat().st_size)
df = pd.read_csv(main_csv, low_memory=False)
print("Dataset loaded:", df.shape)


# Cell 4: Preprocess
def preprocess(df):
    w = df.copy()
    for col in ["start_time", "end_time", "first_action"]:
        if col in w.columns:
            w[col] = pd.to_datetime(w[col], errors="coerce")

    w["event_time"] = pd.NaT
    if "start_time" in w.columns:
        w["event_time"] = w["start_time"]
    if "end_time" in w.columns:
        w["event_time"] = w["event_time"].fillna(w["end_time"])
    if "first_action" in w.columns:
        w["event_time"] = w["event_time"].fillna(w["first_action"])

    for col in ["correct", "hint_count", "attempt_count", "ms_first_response", "actions"]:
        if col in w.columns:
            w[col] = pd.to_numeric(w[col], errors="coerce")
        else:
            w[col] = 0

    w["correct"] = w["correct"].fillna(0).clip(0, 1)
    w["skill"] = w["skill"].fillna("UNKNOWN").astype(str)
    w["user_id"] = pd.to_numeric(w["user_id"], errors="coerce")
    w = w.dropna(subset=["user_id"]).copy()
    w["user_id"] = w["user_id"].astype(int)
    for col in ["hint_count", "attempt_count", "ms_first_response", "actions"]:
        w[col] = w[col].fillna(0)
    return w.sort_values(["user_id", "event_time"], na_position="last").reset_index(drop=True)


events = preprocess(df.sample(min(len(df), 150000), random_state=42))
print("Events:", events.shape)


# Cell 5: Time-decay mastery
def add_mastery(data, half_life_days=21.0):
    lam = np.log(2.0) / half_life_days
    recs = []
    for (_, _), grp in data.groupby(["user_id", "skill"], sort=False):
        state, weight, prev_t = 0.0, 0.0, None
        for row in grp.itertuples():
            t = row.event_time
            if prev_t is not None and pd.notna(t) and pd.notna(prev_t):
                dt = max((t - prev_t).total_seconds() / 86400.0, 0.0)
                decay = np.exp(-lam * dt)
                state *= decay
                weight *= decay
            state += float(row.correct)
            weight += 1.0
            recs.append((row.Index, state / max(weight, 1e-6)))
            prev_t = t
    m = pd.Series({i: v for i, v in recs}, name="mastery")
    out = data.join(m, how="left")
    out["mastery"] = out["mastery"].fillna(out["correct"])
    return out


events = add_mastery(events)
print(events[["user_id", "skill", "correct", "mastery"]].head())


# Cell 6: Build skill summary + gap diagnosis
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
    lambda r: gap_type(r["accuracy"], r["avg_hints"], r["avg_attempts"], r["median_response_ms"]), axis=1
)
summary["priority_score"] = (1 - summary["last_mastery"]) + 0.15 * summary["avg_hints"] + 0.10 * summary["avg_attempts"]


def snapscore(student_events):
    if student_events.empty:
        return 40.0
    active_days = student_events["event_time"].dt.date.dropna().nunique()
    acc = float(student_events["correct"].mean())
    consistency = min(active_days * 1.5, 18.0)
    perf = max((acc - 0.5) * 40.0, -10.0)
    last = student_events["event_time"].max()
    penalty = 0.0
    if pd.notna(last):
        idle_days = max((pd.Timestamp.utcnow().tz_localize(None) - last).days, 0)
        penalty = min(max(idle_days - 7, 0) * 1.5, 20.0)
    return float(np.clip(50 + consistency + perf - penalty, 0, 100))


user_id = int(events["user_id"].iloc[0])
user_summary = summary[summary["user_id"] == user_id].sort_values("priority_score", ascending=False)
print("Student:", user_id, "SnapScore:", round(snapscore(events[events["user_id"] == user_id]), 2))
display(user_summary.head(10)[["skill", "accuracy", "last_mastery", "gap_type", "priority_score"]])


# Cell 7: Upload one PDF and build retrieval chunks
def extract_text_from_pdf_bytes(pdf_bytes: bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    txt = []
    for p in reader.pages:
        txt.append(p.extract_text() or "")
    return "\n".join(txt)


def chunk_text(text, chunk_size=900, overlap=120):
    text = " ".join(text.split())
    chunks = []
    i = 0
    while i < len(text):
        j = min(i + chunk_size, len(text))
        chunks.append(text[i:j])
        if j == len(text):
            break
        i = max(0, j - overlap)
    return chunks


if files is not None:
    uploaded = files.upload()  # pick one PDF
    first_name = list(uploaded.keys())[0]
    pdf_bytes = uploaded[first_name]
    course_text = extract_text_from_pdf_bytes(pdf_bytes)
    course_chunks = chunk_text(course_text)[:80]
    print("PDF loaded:", first_name, "| chunks:", len(course_chunks))
else:
    course_chunks = []
    print("Not running in Colab; skip upload cell.")


# Cell 8: Retrieval (embedding or lexical fallback)
def lexical_retrieve(chunks, query, top_k=3):
    q = set(re.findall(r"[a-zA-Z0-9_]+", query.lower()))
    scored = []
    for c in chunks:
        ct = set(re.findall(r"[a-zA-Z0-9_]+", c.lower()))
        scored.append((len(q & ct), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored[:top_k] if s > 0] or chunks[:top_k]


OPENAI_API_KEY = ""  # set your key here if not using Colab secrets
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and OpenAI else None

if client is not None and course_chunks:
    emb = []
    for c in course_chunks:
        emb.append(client.embeddings.create(model="text-embedding-3-small", input=c).data[0].embedding)
    emb = np.array(emb, dtype=np.float32)
    emb = emb / np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-10, None)

    def retrieve(query, top_k=3):
        q = client.embeddings.create(model="text-embedding-3-small", input=query).data[0].embedding
        q = np.array(q, dtype=np.float32)
        q = q / np.clip(np.linalg.norm(q), 1e-10, None)
        score = emb @ q
        idx = np.argsort(score)[::-1][:top_k]
        return [course_chunks[i] for i in idx]
else:
    def retrieve(query, top_k=3):
        return lexical_retrieve(course_chunks, query, top_k=top_k)


# Cell 9: Chat with citations
student_question = "What should I revise first before solving gradient descent problems?"
snippets = retrieve(student_question, top_k=3)

if client is not None:
    prompt = f"""
Answer the student using only context snippets.
Question: {student_question}
Snippets:
{chr(10).join([f"- {s}" for s in snippets])}
Return concise answer with citations list in JSON: {{ "answer": "...", "citations": ["..."] }}
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    chat = json.loads(resp.choices[0].message.content)
else:
    chat = {"answer": "Fallback answer from retrieved context.", "citations": snippets}

print("Answer:", chat["answer"])
print("Citations:")
for c in chat["citations"][:3]:
    print("-", c[:180], "...")


# Cell 10: Generate prerequisite quiz
top = user_summary.iloc[0]
quiz_skill = top["skill"]
quiz_gap = top["gap_type"]

if client is not None:
    prompt = f"""
Create one targeted micro-quiz JSON for skill {quiz_skill}, gap {quiz_gap}.
Fields: question, answer_key, hint, explanation
Use snippets:
{chr(10).join([f"- {s}" for s in snippets])}
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    quiz = json.loads(resp.choices[0].message.content)
else:
    quiz = {
        "question": f"Explain core concept of {quiz_skill} and solve one mini-example.",
        "answer_key": f"Define {quiz_skill}, apply steps correctly, include worked example.",
        "hint": "Start with definition, then sequence of steps.",
        "explanation": "Strong answers include concept + method + example.",
    }

print("Quiz:", quiz["question"])
print("Hint:", quiz["hint"])


# Cell 11: Auto-grade answer
student_answer = "Gradient descent updates weights using learning rate and loss gradient repeatedly."

if client is not None:
    prompt = f"""
Grade the answer in JSON: score (0-100), is_correct (true/false), feedback.
Question: {quiz["question"]}
Answer key: {quiz["answer_key"]}
Student answer: {student_answer}
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    grade = json.loads(resp.choices[0].message.content)
else:
    grade = {"score": 72, "is_correct": True, "feedback": "Good base idea, add more step detail."}

print("Auto-grade:", grade)


# Cell 12: Update mastery + next recommendation (learning state update)
new_event = {
    "user_id": int(user_id),
    "skill": str(quiz_skill),
    "correct": 1.0 if int(grade["score"]) >= 60 else 0.0,
    "hint_count": 0.0,
    "attempt_count": 1.0,
    "ms_first_response": 0.0,
    "actions": 1.0,
    "event_time": pd.Timestamp.utcnow().tz_localize(None),
}
events2 = pd.concat([events, pd.DataFrame([new_event])], ignore_index=True)
events2 = add_mastery(events2)
summary2 = (
    events2.groupby(["user_id", "skill"], as_index=False)
    .agg(
        attempts=("correct", "size"),
        accuracy=("correct", "mean"),
        avg_hints=("hint_count", "mean"),
        avg_attempts=("attempt_count", "mean"),
        median_response_ms=("ms_first_response", "median"),
        last_mastery=("mastery", "last"),
    )
)
summary2["priority_score"] = (1 - summary2["last_mastery"]) + 0.15 * summary2["avg_hints"] + 0.10 * summary2["avg_attempts"]
next_recs = summary2[summary2["user_id"] == user_id].sort_values("priority_score", ascending=False).head(5)
print("Updated SnapScore:", round(snapscore(events2[events2["user_id"] == user_id]), 2))
display(next_recs[["skill", "accuracy", "last_mastery", "priority_score"]])


# Cell 13: Professor human-in-the-loop
prof_decision = {
    "user_id": int(user_id),
    "skill": str(quiz_skill),
    "risk_flag": "Low mastery trend" if float(top["last_mastery"]) < 0.5 else "None",
    "risk_decision": "keep",
    "ai_score": int(grade["score"]),
    "final_score": int(grade["score"]),  # change if professor overrides
    "grading_decision": "approve_ai_grade",
    "note": "Professor validated recommendation and grade.",
}
print("Professor decision log:")
print(json.dumps(prof_decision, indent=2))

# End: This notebook demonstrates the full MVP loop for one course.
