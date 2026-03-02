# Commands for Judges

## A) Hosted deployment validation (recommended)
1. Open deployed Render URL
2. Verify `/health` returns `status: ok`
3. Execute functional smoke checklist in `testbench/SMOKE_TEST_CHECKLIST.md`

## B) Local fallback commands
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Optional: choose LLM provider in .env
# LLM_PROVIDER=openai|azure_openai|huggingface|mock

python3 -m py_compile app/main.py app/config.py app/db.py app/security.py app/services/*.py
python3 scripts/smoke_test.py
uvicorn app.main:app --reload
```

Open local app: `http://127.0.0.1:8000`

## C) Suggested validation order
1. Professor course workflow
2. Student adaptive workflow
3. HITL risk and grading review
4. Journey and contribution workflows
5. Notification broadcast and leaderboard checks
