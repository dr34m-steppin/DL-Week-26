# Beginner Guide (Render-First, Team Demo Ready)

## Goal
This guide helps you run ReLearnAI as a shared website for judges and teammates.

## Part 1: Deploy first (recommended)

### 1) Push code to GitHub
- Use a public repository
- Do not commit `.env` or API keys

### 2) Create Postgres database
Use one:
- Render PostgreSQL
- Supabase PostgreSQL

Copy the full connection string and replace any `[YOUR-PASSWORD]` placeholder.

### 3) Create Render Web Service
Use:
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

Set Python version:
- `PYTHON_VERSION=3.12.8`

### 4) Add environment variables on Render
```env
SECRET_KEY=<long-random-string>
DATABASE_URL=<postgres-connection-uri>
DB_FALLBACK_TO_SQLITE=0

LLM_PROVIDER=openai
OPENAI_API_KEY=<your-openai-key>
OPENAI_MODEL=gpt-4o-mini

ENABLE_ONLINE_CONTEXT=1
ONLINE_CONTEXT_MAX_TOPICS=4
ONLINE_CONTEXT_CHARS_PER_TOPIC=550
```

### 5) Deploy
After deploy, open:
- `/health`
- `/notifications`

Confirm service is up.

## Part 2: Demo flow for judges

### A) Professor setup
1. Register as professor
2. Create course
3. Upload multiple docs
4. Generate skill map
5. Validate/edit prerequisites
6. Generate quiz bank
7. Approve questions

### B) Student learning loop
1. Register as student
2. Enroll in course
3. Open dashboard
4. Start diagnostic quiz
5. Submit answers
6. Show results, mastery delta, and next actions
7. Ask tutor follow-up
8. Use learning tools (summary/relearn/examples)

### C) Collaborative platform layer
1. Create learning journey from goal
2. Submit contribution/publication
3. Run human review decision
4. Publish tech update
5. Show that update appears in other users' inboxes
6. Show leaderboard and explore views

## Part 3: Local fallback (only if needed)
If deployment is unavailable, run locally:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000`

## Part 4: Submission checklist
Ensure these are present and consistent:
- `docs/FINAL_PROPOSAL.md`
- `docs/ARCHITECTURE.md`
- `docs/JUDGING_ALIGNMENT.md`
- `docs/PROJECT_DOCUMENTATION.md`
- `docs/PROJECT_DOCUMENTATION.pdf`
- `docs/VIDEO_SCRIPT.md`
- `docs/DEPLOY_RENDER.md`
- `testbench/SETUP_AND_RUN.md`
- `testbench/SMOKE_TEST_CHECKLIST.md`
- `testbench/RUN_TESTS.md`
