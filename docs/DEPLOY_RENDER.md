# Deploy ReLearnAI on Render (Persistent + Multi-User)

This guide deploys a public website where all users share one backend and one database.

## 1) Create database first (required for persistence)
Use one of:
- Render PostgreSQL
- Supabase PostgreSQL

Copy the full connection URI and replace `[YOUR-PASSWORD]` with the real password.

## 2) Create Render web service
1. New Web Service -> connect your GitHub repo
2. Build command:
   ```bash
   pip install -r requirements.txt
   ```
3. Start command:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

## 3) Set Python version to avoid wheel build issues
In Render environment/settings, set:
- `PYTHON_VERSION=3.12.8`

Reason: some builds fail on Python 3.14 due missing wheels for transitive deps.

## 4) Environment variables
Set these in Render:

```env
SECRET_KEY=<long-random-string>
DATABASE_URL=<postgres-uri-with-real-password>
DB_FALLBACK_TO_SQLITE=0

LLM_PROVIDER=openai
OPENAI_API_KEY=<your-openai-key>
OPENAI_MODEL=gpt-4o-mini

ENABLE_ONLINE_CONTEXT=1
ONLINE_CONTEXT_MAX_TOPICS=4
ONLINE_CONTEXT_CHARS_PER_TOPIC=550
```

Notes:
- `DB_FALLBACK_TO_SQLITE=0` is recommended in production so DB misconfiguration fails loudly.
- Keep all keys only in Render environment variables, never in git.

## 5) Deploy + verify
After deploy:
1. Open `/health`
2. Register at least 2 accounts
3. Publish a tech update in `/notifications`
4. Confirm all accounts receive the update in inbox
5. Redeploy once and confirm users/data still exist

## 6) Troubleshooting

### Build fails on `pydantic-core` / Rust
- Set `PYTHON_VERSION=3.12.8`
- Clear build cache and redeploy

### App exits with status 3
- Ensure start command includes `--host 0.0.0.0 --port $PORT`
- Check env vars are present and valid

### No data persistence
- Verify `DATABASE_URL` points to Postgres
- Confirm password placeholder is replaced
- Confirm service can connect to DB (same region/network when possible)

### Notification issues
- Confirm user count on notifications page
- Publish a new update and check success message recipient count

## 7) Security checklist
- Do not commit `.env` / `.env.save`
- Rotate keys if exposed
- Set OpenAI usage limits
- Keep app login enabled
