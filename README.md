# DL-Week-26
exe.stoppedworking

# ReLearnAI – Adaptive Learning & Verified Contribution Platform 🧩

*Project entry for Deep Learning Week 2026 – a system that does much more
than quizzes. It models learning, recommends next steps, and preserves trust
through human oversight and reputation.*

---

## 📘 Background
Students and professionals interact with countless digital learning systems
(Blackboard, MOOCs, coding platforms, etc.). These platforms capture rich
signals—question attempts, timestamps, scores, tags—but users are left
asking:

> • What concepts am I genuinely weak at versus careless mistakes?
> • Am I improving, stagnating or regressing over time?
> • What should I focus on if I only have limited study time?
> • Why do I struggle with the same question types repeatedly?

Learning is non‑linear: there are gaps, bursts of effort, and external
resources. Without a cohesive model of a learner’s state, guidance is generic
and uninspiring.

---

## 🧩 Problem Statement
Design an AI-powered solution that continually models a student’s evolving
learning state and delivers personalized, actionable guidance to improve
outcomes. Important aspects include:

- Structuring, interpreting and tracking interaction data over time.
- Generating clear, explainable recommendations.
- Adapting to long-term behavior changes (inactivity, acceleration).
- Delivering an interface (dashboard, tutor bot, analytics) that helps users
  understand, act, and feel supported.

Our answer: **ReLearnAI**—an adaptive loop with built‑in human oversight,
verified contributions, and a global skill reputation.

---

## 💡 Core Solution
Users ingest course materials or publications; AI diagnoses prerequisite gaps
and generates targeted quizzes and tutoring. Student responses update mastery
and a dynamic **SnapScore** that drives the next-best-action recommendation.

A trust layer ensures recommendation credibility:

- **AI pre‑verification** checks similarity, novelty, and factual confidence.
- **Human verification** (professors or domain experts) audit and override
  decisions, with logged rationale.
- **Reputation engine** tracks contributions (courses, quiz items, validations)
  and awards skill‑based SnapScores and leaderboard positions.

Combined, this yields:

```
Upload material → AI diagnosis → Quiz/Tutor → Auto‑grade → Mastery update →
Professor audit → Reputation growth → Next recommendation
```

---

## 🧑‍🤝‍🧑 Who Uses It

- **Students:** get an adaptive tutor + quiz system and a transparent learning
  path.
- **Working professionals:** upload project goals, receive an AI‑crafted
  learning journey and milestones.
- **Publishers/researchers:** publish content that can automatically convert
  into courses; contributions are verified and enhance reputation.
- **Professors/experts:** maintain control via human-in-the-loop panels,
  override flags, and ensure fairness.

---

## 🔑 MVP Features (implemented in this repo)

1. Upload a course PDF plus assessment dataset (CSV) or use provided
   Kaggle data.
2. NLP‑based *AI tutor* answering questions with citations from material.
3. Skill inference engine that diagnoses prerequisite weaknesses.
4. Generation of **targeted micro‑quizzes** addressing weak skills.
5. Free‑text answer **auto‑grading** and feedback.
6. Mastery & SnapScore update driving next recommendation list.
7. Professor dashboard for verifying skill maps, overriding risk flags, and
   confirming grades—all with audit trails.
8. Public APIs (FastAPI) for programmatic access.
9. Optional Colab notebook demonstrating an entire run.

---

## 🏁 Getting Started (Local)

```powershell
cd "c:\Users\user\DL-Week-26\New project"
python -m venv .venv
# activate
.\.venv\Scripts\activate    # Windows
# install
pip install -r requirements.txt
```

### Run the Student/Professor UI

```powershell
streamlit run frontend/streamlit_app.py
```

Browse to `http://localhost:8501` and follow the numbered workflow:
(see testbench guide). This walkthrough serves as the core demo for judges.

### API Server (optional)

```powershell
uvicorn backend.fastapi_app:app --reload --port 8000
curl http://127.0.0.1:8000/health
```

### Colab Notebook
Open `DLW26_LearnLoop_MVP.ipynb` and run cells sequentially for the same demo
in notebook form.

---

## 🧠 Alignment with Judging Criteria (Round 1)

| Theme | Why ReLearnAI Shines |
|------|----------------------|
| *Innovation & Creativity* | Merges adaptive learning, human-in-loop trust,and a global skill reputation. Not just a quiz app—it's a learning intelligence platform. |
| *Technical Implementation* | Python backend, Streamlit/REST frontend,modular `src/` library. Uses LLMs, RAG, skill inference; code quality maintained with tests. |
| *Impact & Viability* | Addresses a pervasive gap in ed‑tech; scalable to courses, professional upskilling, and research publication. |
| *Presentation & Documentation* | Comprehensive README (this file), demo notebook, proposals, and judge testbench with clear run instructions. |
| *Microsoft Track* | Provides actionable guidance, explicable reasoning, supports long‑term learning, and puts human agency at the core. |

Responsible AI considerations are baked in:
- Explanations accompany all recommendations.
- Faculty overrides ensure fairness.
- Data usage limited to needed signals; no PII stored.
- Outputs are deterministic given the same inputs.

---

## 📁 Repository Overview

- **Documentation**: `PROPOSAL_FINAL.md`, `FINAL_SHORT_PROPOSAL.md`,
  `COLAB_GUIDE.md`, `SUBMISSION_CHECKLIST.md`.
- **Notebook**: `DLW26_LearnLoop_MVP.ipynb`.
- **Source code** (`src/`): `ai_tutor.py`, `learning_state.py`, `rag_store.py`.
- **Frontend**: `frontend/streamlit_app.py` (student + professor dashboards).
- **Backend**: `backend/fastapi_app.py` (API endpoints).
- **Testbench**: `testbench/SETUP_AND_RUN.md` and checklist for judges.

---

## 🎥 Demo Suggestions
Record a short walkthrough showing:
1. Uploading PDF & dataset.
2. Asking a question and seeing citations.
3. Generating and completing a quiz with auto‑grade.
4. Mastery update and next-action recommendation.
5. Switching to professor view and making an override.

Highlight the audit logs and SnapScore leaderboard to emphasize trust and
reputation.

---

## ⚠️ Notes & Tips

- No `OPENAI_API_KEY`? Fall back to template generation—flow still works.
- Initial data indexing may take a couple minutes.
- The demo is built around **one course and one student journey**; focus on
  completeness rather than breadth.


Good luck in Deep Learning Week 2026—aim to show judges a system that not
only works, but feels like the future of adaptive, trustworthy learning! 🌟
