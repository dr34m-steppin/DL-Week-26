# LearnLoop AI (Microsoft Track) - Short Final Proposal

## Problem
Learning platforms capture many signals (attempts, hints, timestamps, scores), but students still do not know what to study next, whether they are improving, or why they repeatedly fail similar questions.

## Core Solution
We build an adaptive learning loop for one course that models evolving mastery over time and gives actionable next-step guidance:

Upload course PDF -> Student asks doubt -> AI diagnoses prerequisite gap -> AI generates targeted micro-quiz -> Auto-grades and updates mastery -> Recommends next action -> Professor dashboard validates/overrides.

## MVP Scope (Hackathon)
- Upload 1 PDF (course material)
- Chat with grounded citations
- Prerequisite gap diagnosis
- Targeted micro-quiz generation
- Auto-grading + SnapScore update
- Professor dashboard (human-in-the-loop)

## Why This Meets Judging Criteria
- Effective support: precise, student-specific next actions instead of generic tutoring.
- Clarity and alignment: explicit diagnose -> quiz -> evaluate -> update architecture.
- Transparency: recommendations and answers are citation-backed and explainable.
- Innovation: adapts over time (including inactivity), not just one-shot correctness prediction.
- Real-world applicability: designed for LMS integration and long-term learning analytics.

## Human-in-the-Loop Integration
Professors are active decision-makers, not passive viewers:
- Validate skill/prerequisite map
- Override risk flags
- Confirm or override AI grading

## Responsible AI
- Explainability with citations and reason codes
- Deterministic settings for grading workflows
- Privacy-aware design (minimal required student data, anonymized IDs)
- Human override and audit logs for high-impact decisions

## Tech Stack (MVP)
- OpenAI API (`gpt-4.1-mini`, `text-embedding-3-small`) using student credits
- Python, FastAPI, Streamlit, Pandas
- Local vector retrieval for MVP; Azure AI Search as scale-up path
- Optional Neo4j prerequisite graph + Canvas LMS integration path

