# Deploy ReLearnAI on Render

This deploy keeps your OpenAI key private. Do not commit `.env` or any real keys to GitHub.

## 1) Create Postgres Database
Preferred for your case: Render Free PostgreSQL trial (1GB, trial period).

Option A (Render Postgres):
1. In Render dashboard, create a PostgreSQL database.
2. Copy its internal/external connection string URL.

Option B (Supabase Postgres):
1. Create a project in Supabase.
2. Open **Project Settings -> Database**.
3. Copy connection string (URI), usually transaction pooler.

## 2) Create Web Service
1. Go to Render dashboard.
2. Click **New +** -> **Web Service**.
3. Connect `dr34m-steppin/DL-Week-26`.
4. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## 3) Set Environment Variables
Add these in Render -> Environment:

- `SECRET_KEY` = long random string
- `DATABASE_URL` = your Postgres URL (Render or Supabase)
- `DB_FALLBACK_TO_SQLITE` = `1` (optional fail-safe so app still boots if DB URL is broken)
- `LLM_PROVIDER` = `openai`
- `OPENAI_API_KEY` = your real key
- `OPENAI_MODEL` = `gpt-4o-mini`
- `ENABLE_ONLINE_CONTEXT` = `1`
- `ONLINE_CONTEXT_MAX_TOPICS` = `4`
- `ONLINE_CONTEXT_CHARS_PER_TOPIC` = `550`

## 4) Deploy and Share
1. Click **Deploy**.
2. Open generated public URL.
3. Share URL with teammates and judges.

## 5) Why data now persists
- App uses `DATABASE_URL` when provided.
- All users, courses, leaderboard, quiz history are stored in Supabase Postgres.
- Redeploying Render no longer resets data.
- If Supabase is temporarily unreachable, app can fallback to SQLite when `DB_FALLBACK_TO_SQLITE=1`.

If using Render Postgres, replace \"Supabase\" above with \"Render Postgres\"; behavior is the same.

## 6) Safety Checklist
- Keep login enabled.
- Set usage limits on your OpenAI account.
- Rotate keys if you accidentally expose one.
