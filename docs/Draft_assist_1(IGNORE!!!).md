# ReLearnAI Assisted Draft

## 1. Executive Summary
ReLearnAI is a global collaborative learning platform that unifies:
- adaptive learning for students
- governance and quality control for professors
- upskilling and contribution pathways for working professionals

The system combines learning-state modeling, contribution verification, and domain reputation ranking in one product.

## 2. Problem Statement
Learning systems capture abundant interaction data but still fail to deliver trustworthy, actionable next-step guidance.

Three persistent gaps:
- learners cannot clearly prioritize what to study next
- educators cannot trust ungoverned AI outputs for high-stakes decisions
- professional knowledge contributions are disconnected from structured learning pathways

## 3. Product Vision and Scope

### 3.1 Long-Term Vision
A **Learning + Contribution + Verification + Reputation** ecosystem where:
- users continuously learn and upskill
- projects/publications become learnable pathways
- contributions are verified by AI + humans
- expertise is ranked by domain and impact

### 3.2 Implemented Scope in Current Build
Implemented features include:
- role-based authentication and account/profile settings
- multi-document course ingestion (PDF/TXT)
- AI skill map generation with prerequisite suggestions
- professor validation/editing of skill map
- AI quiz bank generation and professor approval/editing
- student diagnostic and targeted quiz flows
- mastery/risk/grading/SnapScore updates per attempt
- grounded tutor flow with citation support
- learning tools: summary, relearn concept, solved examples
- AI learning journey generation and checkpoint tracking
- final project draft generation and report upload
- contribution/publication submission
- AI pre-verification + human review
- publication outline generation and optional conversion to course
- discovery via Explore (search/filter/sort)
- domain/global leaderboard ranking
- platform-wide notifications and tech update broadcasts

## 4. Users and Role Behavior

### 4.1 Student
- enrolls in courses
- completes adaptive quiz loops
- receives next-step recommendations
- uses tutor and learning tools

### 4.2 Professor
- uploads course knowledge
- validates curriculum structure
- approves assessments
- governs risk and grading overrides
- verifies contributions

### 4.3 Working Professional (Profile-Based)
- configures professional profile in settings/interests
- creates domain journeys from goals
- submits project/publication contributions
- participates in verification and reputation loop

## 5. System Architecture

### 5.1 Application Layer
- FastAPI backend
- Jinja template frontend
- session-based authentication and role access controls

### 5.2 AI Layer
Supported providers:
- OpenAI
- Azure OpenAI
- Hugging Face
- Mock fallback

AI tasks:
- skill map generation
- quiz generation
- tutor response generation
- learning content generation (summary/relearn/examples)
- journey generation
- contribution pre-verification scoring

### 5.3 Retrieval Layer
- document chunking
- lexical retrieval over uploaded material
- tutor and quiz context grounding
- citation metadata persistence in chat flow
- optional online context augmentation via env settings

### 5.4 Data Layer
- local mode: SQLite
- deployed mode: Postgres (`DATABASE_URL`)
- recommended deployment: Render + Postgres for persistent multi-user operation

## 6. Core Modeling and Algorithms

### 6.1 Learning-State Tracking
Per-topic state tracks:
- attempts
- correctness
- response latency
- wrong streak patterns

Mastery and struggle scores are updated after each quiz attempt.

### 6.2 Risk and Grade Logic
- risk flags are generated from topic trend behavior
- grading recommendations are produced from attempt outcomes
- professor review can confirm or override final decision

### 6.3 SnapScore and Reputation
SnapScore combines learning and contribution indicators, including:
- mastery and quiz quality
- engagement and improvement behavior
- project/contribution outcomes
- originality and impact signals

Leaderboard supports domain-focused and global ranking contexts.

### 6.4 Contribution Verification Rule
AI pre-verification computes:
- similarity percentage
- novelty estimate
- factual confidence estimate

Current threshold behavior:
- similarity > 40% -> flagged for review

Final acceptance/rejection requires human decision.

## 7. End-to-End Platform Workflows

### 7.1 Course Intelligence Workflow
1. Professor creates course and uploads docs
2. AI creates skill map and quiz bank
3. Professor validates and approves
4. Student completes adaptive quiz loop
5. System updates mastery/risk/grading/SnapScore
6. Professor governs high-impact overrides

### 7.2 Journey Workflow
1. User submits domain goal
2. AI creates journey modules/milestones/checkpoints
3. User advances checkpoints
4. Final project and report flow connects to contribution system

### 7.3 Contribution Workflow
1. User submits contribution/publication
2. AI pre-verification runs
3. human review finalizes decision
4. publication can become learning outline/course
5. reputation signals update leaderboard impact

### 7.4 Knowledge Update Workflow
1. User publishes tech update
2. notification broadcast reaches all users
3. updates appear in inbox and discovery feed

## 8. Human-in-the-Loop Design
Human checkpoints implemented in production code:
- skill map validation/editing
- quiz question approval/editing
- risk override
- grade finalization
- contribution verification

These controls preserve accountability for educational decisions.

## 9. Responsible AI
- Explainability via grounded context and citation surfaces
- Deterministic fallback (`mock`) for reproducibility
- Human authority over consequential decisions
- role-based access and limited data collection
- explicit separation of implemented scope vs roadmap

## 10. Deployment and Operations
Recommended hackathon deployment:
- Render web service
- Postgres database
- API keys in environment variables only

Operational outcomes:
- persistent data across redeploys
- multi-user shared testing by judges and teammates
- secret-safe architecture (no keys in repo)

## 11. Limitations (Current)
Not fully implemented yet:
- Canvas LMS integration
- vector retrieval index (Azure AI Search)
- Neo4j graph reasoning layer
- autonomous external research ingestion

## 12. Planned Evolution
- vector + graph hybrid knowledge stack
- LMS sync and institutional workflows
- stronger verification governance and audit trails
- longitudinal fairness and drift monitoring for education contexts
