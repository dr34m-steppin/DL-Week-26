# ReLearnAI Architecture (Implemented + Roadmap)

## 1) Platform Positioning
ReLearnAI is a **global collaborative learning platform** across three user groups:
- students
- professors
- working professionals

It combines adaptive learning, contribution verification, and reputation ranking into one system.

## 2) Implemented System Layers

```text
Frontend (FastAPI + Jinja templates)
  -> Role Experiences: Student / Professor / Professional profile
  -> Adaptive Engines: Skill map, quiz gen, mastery/risk/snapscore, tutor
  -> Collaboration Engines: Journeys, contributions, human review
  -> Platform Engines: Explore, notifications, leaderboard, account analytics
  -> Data Layer: SQLite (local) or Postgres (Render/Supabase)
```

## 3) Operational Loops

### A) Adaptive Learning Loop (Implemented)
1. Professor creates course and uploads multiple documents
2. AI generates skill map and prerequisite links
3. Professor validates skill map (HITL)
4. AI generates quiz bank
5. Professor approves/edits quiz questions (HITL)
6. Student runs diagnostic/targeted quiz
7. System updates mastery, struggle, risk, grade, SnapScore
8. Dashboard recommends next actions and tutor support
9. Professor reviews risk and grading overrides (HITL)

### B) Learning Journey Loop (Implemented)
1. User submits goal and domain
2. AI builds journey (modules, milestones, checkpoints)
3. User tracks checkpoint progress
4. User generates final project and uploads report
5. Flow connects into contribution verification

### C) Contribution and Publication Loop (Implemented)
1. User submits project/publication/article/open-source contribution
2. AI pre-verification runs (similarity/novelty/factual confidence)
3. Human verifier/professor approves or rejects
4. Publication owner can generate learning outline
5. Optional conversion to course for other learners
6. SnapScore and leaderboard impact updates

### D) Knowledge Update Loop (Implemented)
1. User publishes technology update
2. System broadcasts notification to all platform users
3. Users discover updates via inbox and explore feed

## 4) AI Layer Design

### Supported providers
- OpenAI
- Azure OpenAI
- Hugging Face
- Mock fallback

### AI functions in current build
- Skill map generation
- Quiz generation
- Tutor answer generation
- Summary/relearn/example generation
- Journey generation
- Contribution pre-verification metrics

### Grounding method
- Course documents are chunked
- Lexical retrieval selects relevant chunks
- Tutor/quiz generation uses retrieved context
- Citation snippets stored and rendered in chat flow
- Optional online context enabled via env vars

## 5) Data Model (Implemented)
Key entities:
- users, user_interest_profiles
- courses, course_documents, enrollments
- skill_map, quiz_questions, quiz_attempts, student_topic_state
- risk_flags, grading_reviews, snapscore_events
- chat_messages
- learning_journeys, journey_checkpoints
- contributions, contribution_reviews
- tech_updates, notifications
- domains

## 6) Decision and Scoring
- Topic mastery and struggle are updated per attempt
- Risk levels derived from trend signals
- Grade recommendation generated per attempt window
- SnapScore combines learning quality, activity, and contribution impact
- Domain/global ranking computed for leaderboard visibility

## 7) Human-in-the-Loop Control Points
- Skill map validation/editing
- Quiz bank approval/editing
- Risk override decisions with rationale
- Final grade confirmation/override
- Contribution verification decisions

## 8) Deployment Architecture
- Preferred: Render web service + Postgres
- Local fallback: SQLite for rapid development
- Secrets managed through environment variables

## 9) Current Limitations (Explicit)
- No Canvas LMS sync yet
- Retrieval is lexical (no vector index yet)
- No Neo4j prerequisite graph service yet
- No autonomous external research crawler yet

## 10) Roadmap to Full Vision
- Azure AI Search vector retrieval
- Neo4j graph-based prerequisite reasoning
- LMS integrations
- stronger verifier reputation and audit trails
- fairness/drift monitoring over long-term cohorts
