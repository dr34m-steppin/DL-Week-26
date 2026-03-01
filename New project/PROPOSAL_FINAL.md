# LearnLoop AI: Adaptive Learning Copilot with Human-in-the-Loop

## 1) Problem
Students generate rich learning traces (attempts, hints, timestamps, confidence), but still lack clear answers to:
- What is my true gap vs a careless mistake?
- Am I improving or stagnating over time?
- What should I study next with limited time?

## 2) Solution (Core Loop)
LearnLoop AI runs a continuous loop for one course:

1. Student uploads course material / asks a question.
2. AI retrieves grounded context (RAG) and diagnoses prerequisite gaps.
3. AI generates a targeted micro-quiz.
4. System grades performance and updates a time-aware mastery model.
5. Student gets next-best recommendation + motivation score (SnapScore).
6. Professor dashboard shows risk flags and can override AI decisions.

This is not just Q&A. It is a diagnose -> quiz -> evaluate -> update loop.

## 3) Why This Fits Microsoft Track Criteria

### Effective support for learning
- Personalized next-step recommendations per student and per skill.
- Gap type labels: conceptual gap, procedure gap, or careless mistake.
- Time-aware trend tracking for long inactivity and revision bursts.

### Clarity of design and justification
- Vector retrieval handles semantic course context.
- Skill graph handles prerequisites and structured curriculum logic.
- EJM-style tracker converts interactions into explainable learning state.

### Transparency and interpretability
- Every recommendation includes: weak skill, evidence, and prerequisite path.
- Quiz generation returns source citations from course material.
- Dashboard exposes model signals, not just opaque scores.

### Creativity and innovation
- Agentic loop (diagnoser + planner + evaluator) instead of single response bot.
- Motivation-aware SnapScore to reward consistency, not only correctness.
- Human-in-the-loop controls for grading and risk decisions.

### Real-world applicability
- Works with LMS workflow (Canvas API for roster/assignments/grades).
- Handles long-term usage via decayed mastery updates.
- Scales from one course POC to multi-course deployment.

## 4) Responsible AI in Education
- Explainability: evidence-backed recommendations with citations.
- Consistency: low-temperature deterministic generation for assessment tasks.
- Fairness: monitor bias across engagement patterns and class sections.
- Privacy: anonymized student IDs, minimum necessary data retention.
- Human agency: professors validate, override, and audit AI outputs.

## 5) MVP Scope (Hackathon-feasible)
- Single course only.
- One uploaded PDF corpus for RAG.
- Student chat + prerequisite micro-quiz generation.
- Mastery tracking + weak-skill recommendations.
- Professor dashboard with override and notes.

## 6) Tech Stack
- LLM: OpenAI API (`gpt-4.1-mini`, `text-embedding-3-small`) or Azure OpenAI equivalent.
- Retrieval: local vector index (POC) -> Azure AI Search (production path).
- Data: Pandas + optional Azure Blob/Cosmos in deployment.
- Graph: Neo4j for skill/prerequisite graph.
- Backend: FastAPI (can move to Azure Functions).
- Frontend: Streamlit dashboard (can move to React later).
- LMS: Canvas API integration endpoints.

## 7) Execution Plan

### Phase 1 (Day 1): Data and modeling
- Load Skill Builder dataset.
- Build per-student per-skill mastery with time decay.
- Implement gap diagnosis and recommendation ranking.

### Phase 2 (Day 1-2): AI loop
- Add RAG over course documents.
- Generate targeted micro-quizzes and explanations.
- Track quiz outcomes and update mastery state.

### Phase 3 (Day 2): Demo and HITL
- Build student view (ask -> quiz -> feedback).
- Build professor dashboard (risk flags, overrides).
- Prepare short walkthrough with one student journey.

## 8) Risks and Mitigations
- Hallucinations -> grounded retrieval + citation requirement.
- Over-automation in grading -> professor approval gate.
- Dataset mismatch to local curriculum -> allow manual skill-map edits.
- Time constraints -> focus on one-course core loop only.

