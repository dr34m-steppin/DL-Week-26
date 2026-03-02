# ReLearnAI Project Documentation

## 1. Problem and Motivation

Students produce rich interaction data but still lack a clear answer to: *what should I do next?* Existing tools answer questions but rarely maintain an evolving, explainable learning state over time.

## 2. Proposed Solution

ReLearnAI is an AI-assisted learning loop for one course:

1. Ingest course material
2. Build skill map + prerequisites
3. Generate diagnostic quiz
4. Auto-grade and update learning state
5. Recommend next action
6. Keep professor in control for validation and overrides

## 3. System Design

### 3.1 Components
- **Course Knowledge Base**: uploaded course document stored as text
- **Retriever (RAG-lite)**: lexical chunk retrieval with citation references
- **Quiz Generator**: configurable LLM provider (Azure/OpenAI/HF/mock)
- **Mastery Engine**: topic-level mastery + struggle + risk computation
- **SnapScore**: motivation and consistency score
- **Professor HITL Layer**:
  - skill map validation
  - quiz approval/editing
  - risk flag overrides
  - grade confirmation/override

### 3.2 Data Model
Core entities:
- users
- courses
- course_documents
- skill_map
- quiz_questions
- quiz_attempts
- student_topic_state
- snapscore_events
- risk_flags
- grading_reviews
- chat_messages

## 4. Learning-State Modeling

Per topic:
- `mastery = (correct + 1) / (attempts + 2)`
- `struggle = weighted(low mastery, response latency, wrong streak)`

Risk policy:
- LOW: insufficient data or healthy trajectory
- MEDIUM: moderate mastery/struggle concern
- HIGH: persistently low mastery with enough attempts

This makes progression explainable and deterministic.

## 5. Human-in-the-Loop Controls

Professor controls are explicit and auditable:
- Validate/edit skill map topics and prerequisites
- Approve/edit each AI-generated quiz question
- Override risk flags with status + rationale
- Confirm or override AI grade recommendation

This satisfies agency and trust requirements in education.

## 6. Responsible AI Considerations

- **Explainability**: citations in tutor responses and visible score formulas
- **Consistency**: deterministic fallback mode (`mock`) for reproducible runs
- **Bias mitigation**: professor review gates for all high-impact outputs
- **Privacy**: minimal local storage, no unnecessary personal data
- **Human agency**: override mechanisms throughout grading/risk flows

## 7. Implementation Completeness (MVP)

Implemented:
- auth + role separation
- upload 1 document
- chat with citations
- quiz generation
- auto grading
- evolving score updates
- student dashboard
- professor dashboard with HITL controls

## 8. Limitations

- Current retriever is lexical, not embedding-based
- Single-instance SQLite (not production scale)
- No full LMS sync in MVP (Canvas integration planned)
- Skill graph is relationally represented (Neo4j is next phase)

## 9. Future Work

- Canvas API sync for assignments and gradebook
- Azure AI Search embedding retrieval
- Neo4j concept graph for richer prerequisite paths
- longitudinal drift detection across semesters
- cohort fairness analytics

## 10. Reproducibility

All setup and test steps are in:
- `README.md`
- `testbench/SETUP_AND_RUN.md`
- `testbench/SMOKE_TEST_CHECKLIST.md`

