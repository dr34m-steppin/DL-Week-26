# LearnLoop AI - Project Documentation Template (Export to PDF)

Use this template for the required PDF deliverable.

## 1. Team and Project
- Team name:
- Members:
- Track: Microsoft Track
- Project title: LearnLoop AI

## 2. Problem Statement
- What student pain points are addressed?
- Why existing LMS analytics are insufficient?

## 3. Solution Overview
- Core loop:
  - Upload course material
  - Student asks doubt
  - AI diagnoses prerequisite gap
  - Generates targeted micro-quiz
  - Auto-grades and updates mastery
  - Adjusts recommendation
  - Professor validates/overrides
- Why this loop is practical for one-course MVP

## 4. Architecture and Components
- Student interface (chat + quiz)
- Learning state model (time-decay mastery + SnapScore)
- RAG layer (PDF chunks + retrieval + citation output)
- Auto-grading component
- Professor dashboard (skill map validation, risk override, grade confirmation)
- Data storage used (logs/overrides)

## 5. Dataset and Data Processing
- Dataset: Skill Builder 2009-2010 (Kaggle)
- Key columns used:
  - `user_id`, `skill`, `correct`, `hint_count`, `attempt_count`, `ms_first_response`, timestamps
- Cleaning and preprocessing steps
- Assumptions and limitations

## 6. Methodology
- Gap diagnosis rules
- Time-aware mastery update
- Recommendation ranking logic
- Human-in-the-loop policy

## 7. Implementation Details
- Stack:
  - Python, Streamlit, FastAPI, Pandas
  - OpenAI (`gpt-4.1-mini`, `text-embedding-3-small`)
- Files and roles:
  - `frontend/streamlit_app.py`
  - `src/learning_state.py`
  - `src/ai_tutor.py`
  - `src/rag_store.py`
  - `backend/fastapi_app.py`

## 8. Results and Demo Evidence
- Screenshots of each loop stage
- Example student before/after mastery update
- Example professor override record

## 9. Testing Procedure
- Reference: `testbench/SETUP_AND_RUN.md`
- What scenarios were tested?
- What passed/failed?

## 10. Responsible AI and Risk Awareness
- Explainability via citations and recommendation reason
- Deterministic settings for grading
- Human override for high-impact decisions
- Privacy minimization and anonymization notes
- Failure modes and mitigations

## 11. Impact and Viability
- Why this can scale from one course to many
- LMS integration path (Canvas)
- Cost and deployment considerations

## 12. Limitations and Future Work
- Current MVP boundaries
- Planned improvements (Azure AI Search, Neo4j graph, LMS automation)

## 13. References (IEEE Style Preferred)
- Include all third-party APIs, datasets, docs, and libraries used.

