# Deploy ReLearnAI on Render

This deploy keeps your OpenAI key private. Do not commit `.env` or any real keys to GitHub.

## 1) Create Web Service
1. Go to Render dashboard.
2. Click **New +** -> **Web Service**.
3. Connect `dr34m-steppin/DL-Week-26`.
4. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## 2) Set Environment Variables
Add these in Render -> Environment:

- `SECRET_KEY` = long random string
- `DB_PATH` = `/var/data/relearnai.db`
- `LLM_PROVIDER` = `openai`
- `OPENAI_API_KEY` = your real key
- `OPENAI_MODEL` = `gpt-4o-mini`
- `ENABLE_ONLINE_CONTEXT` = `1`
- `ONLINE_CONTEXT_MAX_TOPICS` = `4`
- `ONLINE_CONTEXT_CHARS_PER_TOPIC` = `550`

## 3) Persist Data Across Deploys (Important)
Without a persistent disk, users/leaderboard/progress will reset on deploy.

1. Open Render service -> **Disks**.
2. Add a persistent disk:
   - Mount path: `/var/data`
   - Size: `1 GB` (or higher)
3. Confirm `DB_PATH=/var/data/relearnai.db` exists in Environment.
4. Redeploy.

## 4) Deploy and Share
1. Click **Deploy**.
2. Open generated public URL.
3. Share URL with teammates and judges.

## 5) Safety Checklist
- Keep login enabled.
- Set usage limits on your OpenAI account.
- Rotate keys if you accidentally expose one.
