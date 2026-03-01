from __future__ import annotations

import json
import re
from pathlib import Path
import sys
from typing import Dict, List

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.ai_tutor import answer_with_citations, auto_grade_answer, generate_micro_quiz
from src.learning_state import (
    add_time_decay_mastery,
    append_quiz_result_and_recompute,
    build_student_insight,
    build_student_skill_summary,
    download_skillbuilder_dataset,
    load_skillbuilder_dataframe,
    preprocess_skillbuilder,
)
from src.rag_store import LocalRAGStore, chunk_text, extract_pdf_text


st.set_page_config(page_title="LearnLoop AI", page_icon="🎯", layout="wide")
st.title("LearnLoop AI MVP")
st.caption("Upload PDF -> Ask doubt -> Diagnose gap -> Quiz -> Auto-grade -> Update mastery -> Professor override")


@st.cache_data(show_spinner=False)
def load_demo_data(sample_rows: int = 120000):
    dataset_path = download_skillbuilder_dataset()
    raw = load_skillbuilder_dataframe(dataset_path)
    if len(raw) > sample_rows:
        raw = raw.sample(sample_rows, random_state=42).copy()
    processed = preprocess_skillbuilder(raw)
    events = add_time_decay_mastery(processed, half_life_days=21.0)
    summary = build_student_skill_summary(events)
    return events, summary


def _safe_tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def lexical_retrieve(chunks: List[str], question: str, top_k: int = 3) -> List[str]:
    q_tokens = set(_safe_tokenize(question))
    if not q_tokens:
        return chunks[:top_k]
    scored = []
    for c in chunks:
        c_tokens = set(_safe_tokenize(c))
        overlap = len(q_tokens & c_tokens)
        scored.append((overlap, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for score, c in scored[:top_k] if score > 0] or chunks[:top_k]


def compute_risk_flags(insight: Dict, weak_df: pd.DataFrame) -> List[str]:
    flags = []
    if float(insight["snapscore"]) < 45:
        flags.append("Low motivation / performance risk (SnapScore < 45)")
    conceptual_count = int((weak_df["gap_type"] == "Conceptual gap").sum()) if not weak_df.empty else 0
    if conceptual_count >= 2:
        flags.append("Multiple conceptual gaps detected")
    if weak_df.shape[0] > 0 and float(weak_df["last_mastery"].mean()) < 0.5:
        flags.append("Average mastery below 0.5 in top weak skills")
    return flags


if "events" not in st.session_state:
    st.session_state.events = None
if "summary" not in st.session_state:
    st.session_state.summary = None
if "rag_store" not in st.session_state:
    st.session_state.rag_store = None
if "rag_chunks" not in st.session_state:
    st.session_state.rag_chunks = []
if "current_quiz" not in st.session_state:
    st.session_state.current_quiz = None
if "last_grade" not in st.session_state:
    st.session_state.last_grade = None
if "last_chat" not in st.session_state:
    st.session_state.last_chat = None
if "prereq_map" not in st.session_state:
    st.session_state.prereq_map = {}


with st.sidebar:
    st.header("Setup")
    sample_rows = st.slider("Dataset sample rows", 20000, 200000, 100000, 10000)
    if st.button("1) Load Assessment Dataset"):
        with st.spinner("Loading and modeling learning state..."):
            events_df, summary_df = load_demo_data(sample_rows)
            st.session_state.events = events_df
            st.session_state.summary = summary_df
        st.success("Dataset loaded.")
    openai_key = st.text_input("OpenAI API Key (optional but recommended)", type="password")


if st.session_state.events is None:
    st.info("Start in sidebar: click `1) Load Assessment Dataset`.")
    st.stop()

events_df: pd.DataFrame = st.session_state.events
summary_df: pd.DataFrame = st.session_state.summary

st.markdown("## Core Loop Demo")
users = sorted(events_df["user_id"].dropna().astype(int).unique().tolist())
selected_user = st.selectbox("Student ID", options=users, index=0)

insight_obj = build_student_insight(
    events_with_mastery=events_df,
    summary_df=summary_df,
    user_id=int(selected_user),
    prereq_map=st.session_state.prereq_map,
    top_k=5,
)
insight = {
    "user_id": insight_obj.user_id,
    "snapscore": insight_obj.snapscore,
    "weak_skills": insight_obj.weak_skills,
    "recommendations": insight_obj.recommendations,
}
weak_df = pd.DataFrame(insight["weak_skills"])

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("SnapScore", f"{insight['snapscore']:.1f}/100")
metric_col2.metric("Tracked Skills", str(len(summary_df[summary_df["user_id"] == selected_user])))
metric_col3.metric("Top Recommendations", str(len(insight["recommendations"])))

student_col, prof_col = st.columns([2, 1])

with student_col:
    st.markdown("### 1) Upload Course Material (One PDF)")
    uploaded_pdf = st.file_uploader("Upload course PDF", type=["pdf"], accept_multiple_files=False)
    if st.button("2) Build Course Knowledge Base"):
        if uploaded_pdf is None:
            st.error("Upload one PDF first.")
        else:
            data_dir = ROOT / "data"
            data_dir.mkdir(exist_ok=True)
            pdf_path = data_dir / "course_material.pdf"
            pdf_path.write_bytes(uploaded_pdf.getbuffer())
            raw_text = extract_pdf_text(pdf_path)
            chunks = chunk_text(raw_text, chunk_size=900, overlap=120)[:80]
            st.session_state.rag_chunks = chunks

            if openai_key.strip():
                with st.spinner("Creating vector index..."):
                    st.session_state.rag_store = LocalRAGStore.from_texts(
                        texts=chunks,
                        openai_api_key=openai_key.strip(),
                    )
                st.success(f"Indexed {len(chunks)} chunks with embeddings.")
            else:
                st.session_state.rag_store = None
                st.warning(
                    "No API key. Using lexical retrieval fallback (still works for demo, but weaker than embeddings)."
                )

    st.markdown("### 2) Student Asks Doubt -> Chat with Citations")
    question = st.text_input("Ask a concept doubt", value="")
    if st.button("3) Ask Tutor"):
        if not st.session_state.rag_chunks:
            st.error("Build knowledge base first.")
        else:
            if st.session_state.rag_store is not None and openai_key.strip():
                retrieved = st.session_state.rag_store.query(
                    question,
                    openai_api_key=openai_key.strip(),
                    top_k=3,
                )
                snippets = [r.text for r in retrieved]
            else:
                snippets = lexical_retrieve(st.session_state.rag_chunks, question, top_k=3)

            answer_payload = answer_with_citations(
                question=question,
                retrieved_snippets=snippets,
                openai_api_key=openai_key.strip() if openai_key.strip() else None,
            )
            st.session_state.last_chat = {
                "question": question,
                "answer": answer_payload.get("answer", ""),
                "citations": answer_payload.get("citations", snippets),
            }

    if st.session_state.last_chat is not None:
        st.write("**AI Answer**")
        st.write(st.session_state.last_chat["answer"])
        st.write("**Citations**")
        for i, cit in enumerate(st.session_state.last_chat["citations"][:3], start=1):
            st.write(f"[{i}] {cit}")

    st.markdown("### 3) Diagnose Gap -> Generate Prerequisite Quiz")
    if not weak_df.empty:
        st.dataframe(
            weak_df[["skill", "accuracy", "last_mastery", "gap_type", "priority_score"]],
            use_container_width=True,
        )

        top_rec = insight["recommendations"][0] if insight["recommendations"] else None
        if top_rec:
            prereqs = top_rec.get("recommended_prerequisites", [])
            target_skill = prereqs[0] if prereqs else top_rec["skill"]
            st.write(
                f"Diagnosed gap: **{top_rec['skill']}** ({top_rec['gap_type']}). "
                f"Quiz target: **{target_skill}**"
            )

            if st.button("4) Generate Targeted Micro-Quiz"):
                snippets = []
                if st.session_state.last_chat is not None:
                    snippets = st.session_state.last_chat["citations"][:3]
                quiz = generate_micro_quiz(
                    skill=target_skill,
                    gap_type=top_rec["gap_type"],
                    context_snippets=snippets,
                    openai_api_key=openai_key.strip() if openai_key.strip() else None,
                )
                st.session_state.current_quiz = quiz

    if st.session_state.current_quiz is not None:
        quiz = st.session_state.current_quiz
        st.write("**Quiz Question**")
        st.write(quiz.get("question", ""))
        st.caption(f"Hint: {quiz.get('hint', '')}")

        student_answer = st.text_area("Student answer", height=120, key="student_answer_text")
        if st.button("5) Auto-Grade + Update Mastery"):
            grade = auto_grade_answer(
                question=quiz.get("question", ""),
                answer_key=quiz.get("answer_key", quiz.get("explanation", "")),
                student_answer=student_answer,
                openai_api_key=openai_key.strip() if openai_key.strip() else None,
            )
            st.session_state.last_grade = {
                "user_id": int(selected_user),
                "skill": quiz.get("skill", ""),
                "ai_score": int(grade["score"]),
                "ai_correct": bool(grade["is_correct"]),
                "feedback": grade["feedback"],
                "status": "pending_prof_review",
            }
            updated_events, updated_summary = append_quiz_result_and_recompute(
                events_df=st.session_state.events,
                user_id=int(selected_user),
                skill=quiz.get("skill", ""),
                score=float(grade["score"]),
            )
            st.session_state.events = updated_events
            st.session_state.summary = updated_summary
            st.success(f"AI Score: {grade['score']}/100")
            st.write(f"Feedback: {grade['feedback']}")
            st.info("Mastery and recommendations updated.")

with prof_col:
    st.markdown("### Professor Dashboard (Human-in-the-Loop)")
    st.write("Validate skill map, override risk flags, confirm grading.")

    st.markdown("#### A) Validate Skill Map")
    top_skills = weak_df["skill"].head(6).tolist() if not weak_df.empty else []
    rows = []
    for skill in top_skills:
        prereqs = st.session_state.prereq_map.get(skill, [])
        rows.append({"skill": skill, "prerequisites_csv": ",".join(prereqs)})
    edit_df = pd.DataFrame(rows) if rows else pd.DataFrame([{"skill": "", "prerequisites_csv": ""}])
    edited = st.data_editor(edit_df, use_container_width=True, hide_index=True)
    if st.button("Save Skill Map"):
        new_map: Dict[str, List[str]] = dict(st.session_state.prereq_map)
        for row in edited.to_dict(orient="records"):
            skill = str(row.get("skill", "")).strip()
            if not skill:
                continue
            prereqs = [x.strip() for x in str(row.get("prerequisites_csv", "")).split(",") if x.strip()]
            new_map[skill] = prereqs
        st.session_state.prereq_map = new_map
        st.success("Skill map updated.")

    st.markdown("#### B) Override Risk Flags")
    risk_flags = compute_risk_flags(insight, weak_df)
    if risk_flags:
        selected_flag = st.selectbox("Risk flag", options=risk_flags)
        risk_decision = st.selectbox("Decision", options=["keep", "downgrade", "escalate"])
        risk_note = st.text_area("Risk note", key="risk_note")
        if st.button("Save Risk Decision"):
            path = ROOT / "data" / "professor_overrides.json"
            path.parent.mkdir(exist_ok=True)
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            existing.append(
                {
                    "type": "risk_override",
                    "user_id": int(selected_user),
                    "flag": selected_flag,
                    "decision": risk_decision,
                    "note": risk_note,
                }
            )
            path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            st.success("Risk override saved.")
    else:
        st.caption("No active risk flags for this student.")

    st.markdown("#### C) Confirm / Override Auto-Grading")
    if st.session_state.last_grade is not None:
        g = st.session_state.last_grade
        st.write(
            f"Pending review -> user `{g['user_id']}`, skill `{g['skill']}`, AI score `{g['ai_score']}`"
        )
        prof_decision = st.selectbox("Grade decision", options=["approve_ai_grade", "override_grade"])
        final_score = st.slider("Final score", 0, 100, int(g["ai_score"]))
        grade_note = st.text_area("Grading note", key="grade_note")
        if st.button("Save Grade Decision"):
            path = ROOT / "data" / "professor_overrides.json"
            path.parent.mkdir(exist_ok=True)
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            existing.append(
                {
                    "type": "grading_confirmation",
                    "user_id": int(g["user_id"]),
                    "skill": g["skill"],
                    "ai_score": int(g["ai_score"]),
                    "prof_decision": prof_decision,
                    "final_score": int(final_score),
                    "note": grade_note,
                }
            )
            path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

            if prof_decision == "override_grade" and int(final_score) != int(g["ai_score"]):
                # Manual override is logged as an adjustment event to reflect professor authority.
                updated_events, updated_summary = append_quiz_result_and_recompute(
                    events_df=st.session_state.events,
                    user_id=int(g["user_id"]),
                    skill=g["skill"],
                    score=float(final_score),
                )
                st.session_state.events = updated_events
                st.session_state.summary = updated_summary
            st.success("Grade decision saved.")
    else:
        st.caption("No pending auto-graded quiz yet.")

    st.markdown("#### Recent Professor Decisions")
    log_path = ROOT / "data" / "professor_overrides.json"
    if log_path.exists():
        logs = json.loads(log_path.read_text(encoding="utf-8"))
        if logs:
            st.dataframe(pd.DataFrame(logs).tail(8), use_container_width=True)
        else:
            st.caption("No decisions logged yet.")
    else:
        st.caption("No decisions logged yet.")

