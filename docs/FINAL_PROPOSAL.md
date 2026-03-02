# ReLearnAI Final Proposal

## Title
**ReLearnAI: Global Human-Governed Collaborative Learning Platform**

## Core Problem
Learners generate large amounts of activity data, but they still do not receive trustworthy, action-focused guidance on what to do next.

At the same time, educators and experts need governance over AI outputs in high-impact workflows such as risk and grading decisions.

## Core Vision
ReLearnAI is a **global collaborative learning environment** where:
- students learn adaptively
- professors govern and validate AI outputs
- working professionals upskill and contribute domain knowledge
- publications/projects become structured learning pathways
- verified contributions build domain reputation over time

This is not only an LMS helper. It is a **Learning + Contribution + Verification + Reputation** system.

## What Is Implemented Now

### 1) Adaptive Course Intelligence Loop
- Professor creates course and uploads multiple documents (PDF/TXT)
- AI generates skill map and prerequisite relationships
- Professor validates/edits the skill map (HITL)
- AI generates quiz bank and professor approves/edit questions (HITL)
- Student takes diagnostic/targeted quiz and uses grounded tutor
- System updates mastery, struggle, risk, and SnapScore
- Dashboard recommends exact next actions
- Professor reviews risk and confirms/overrides grading decisions

### 2) Cross-Role Collaboration Layer
- Interest/profile settings support student, professor, and professional usage
- Learning journeys generated from goals/domains
- Contributions/publications submitted for AI pre-verification + human review
- Publication outline generation with optional conversion into a course
- Discoverability via Explore (search/filter/sort)
- Domain/global reputation via Leaderboard
- Platform-wide notifications for updates

## Why This Matches Judging Criteria
- **Clarity and Alignment**: explicit loop from diagnose -> intervene -> reassess -> govern
- **Execution and Completeness**: end-to-end role workflows are implemented
- **Impact and Risk Awareness**: actionable learner guidance with professor oversight on high-stakes outputs
- **Human in the Loop**: validation, approval, override, and verification gates are built-in
- **Transparency**: grounded tutor responses + visible decision logic + auditable review actions

## AI Pattern Justification
- **RAG-style grounding** for tutor and quiz generation context
- **Agentic generation** for skill maps, quiz banks, summaries, relearn prompts, examples, and journeys
- **Maker-checker loop** for contribution verification (AI pre-check + human decision)
- **HITL governance** for curriculum, risk, and grade decisions

## Technical Approach
- FastAPI web app with role-based flows
- SQLite (local) or Postgres (deployment) persistence
- Configurable LLM provider: Azure OpenAI / OpenAI / Hugging Face / Mock fallback
- Topic-level mastery + risk modeling with recommendation engine
- Discovery + notification + ranking subsystems for platform behavior

## Innovation
ReLearnAI does not stop at answering questions.
It continuously models evolving learning state, adapts interventions over time, validates contributions, and connects learning outcomes to global domain reputation.

## Current MVP Boundaries (No Overclaim)
Not fully implemented yet:
- Canvas LMS sync
- Vector retrieval with Azure AI Search
- Neo4j knowledge graph prerequisite engine
- Automated external research ingestion pipeline

## Next Extensions
- LMS integration (Canvas)
- vector + graph hybrid retrieval stack
- longitudinal fairness and drift analytics
- stronger verifier marketplace and contribution governance tools
