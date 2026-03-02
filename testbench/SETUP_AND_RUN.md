# Testbench Setup and Run Guide (Render-First)

## 1) Preferred judge path: hosted deployment
Use the deployed Render URL first so multi-user collaboration can be validated.

### Validate these pages on hosted app
- `/health`
- `/prof`
- `/student`
- `/journeys`
- `/contributions`
- `/explore`
- `/leaderboard`
- `/notifications`

## 2) Hosted test flow

### Professor path
1. Register professor
2. Create course
3. Upload multiple documents
4. Generate skill map
5. Validate/edit skill entries
6. Generate quiz bank
7. Approve questions

### Student path
1. Register student
2. Enroll in course
3. Open dashboard
4. Run diagnostic quiz and submit
5. Verify result metrics + recommendations
6. Open tutor and ask follow-up
7. Use learning tools

### Collaborative platform path
1. Create journey from goal
2. Submit contribution/publication
3. Complete human review action
4. Publish tech update
5. Confirm notification appears in all test-user inboxes
6. Check leaderboard/explore updates

## 3) Local fallback (if hosted site unavailable)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Open: `http://127.0.0.1:8000`

## 4) Optional provider config
Use one provider in `.env`:
- `openai`
- `azure_openai`
- `huggingface`
- `mock`

## 5) Quick technical checks
```bash
python3 -m py_compile app/main.py app/config.py app/db.py app/security.py app/services/*.py
python3 scripts/smoke_test.py
```
