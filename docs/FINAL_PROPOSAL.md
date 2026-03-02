# ReLearnAI Final Proposal (Short Version)

## Title
**ReLearnAI: Human-Governed Adaptive Learning Loop **

## Problem
Students generate lots of interaction data, but still lack clear, trustworthy guidance on what to study next. Most AI tutors answer questions but do not track evolving mastery over time.

## Solution
ReLearnAI builds a closed learning loop for one course:
1. Professor uploads course material
2. AI generates skill map and diagnostic quiz bank
3. Professor validates skill map and approves quiz items (human in loop)
4. Student takes quiz and chats with grounded tutor
5. System auto-grades and updates topic mastery, struggle, risk, and SnapScore
6. Dashboard recommends exact next actions
7. Professor reviews risk alerts and confirms/overrides grading

## Why this is aligned to judging criteria
- **Clarity & Alignment**: One focused loop from diagnosis to action.
- **Execution & Completeness**: End-to-end student + professor workflows implemented.
- **Impact & Risk Awareness**: Students get actionable next steps; professors control high-impact decisions.
- **Human in the Loop**: Validation, approval, override, and confirmation are built-in checkpoints.
- **Transparency**: Tutor answers include citations; scoring and risk logic are visible and deterministic.

## Technical Approach
- FastAPI web app + SQLite
- RAG-lite retrieval over uploaded course doc for grounded tutor answers
- Configurable LLM provider (Azure OpenAI / OpenAI / Hugging Face / mock fallback)
- Topic-level mastery model with risk flags and recommendation logic

## Innovation
The system does not stop at “answering questions.” It continuously models learning state, verifies improvement through repeated quizzes, and keeps educators in control.

## MVP Scope (Hackathon-Realistic)
- Upload 1 document
- Chat with citations
- Generate prerequisite quiz
- Auto-grade attempts
- Update score and gap map
- Professor dashboard with HITL controls

## Future Extensions
- Canvas LMS sync
- Azure AI Search embeddings
- Neo4j knowledge graph for prerequisite paths
- Longitudinal fairness and drift analytics
