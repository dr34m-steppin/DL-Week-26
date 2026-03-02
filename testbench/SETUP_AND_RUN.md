# Testbench Setup and Run Guide

## 1. Environment setup
```bash
cd /Users/amalthomasmanoj/Documents/ReLearnAI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 2. Launch app
```bash
uvicorn app.main:app --reload
```
Open: `http://127.0.0.1:8000`

## 3. Basic seeded flow (manual)
1. Register professor account
2. Create one course
3. Upload `docs/sample_course_doc.txt`
4. Generate skill map
5. Generate quiz bank
6. Approve at least 5 quiz questions
7. Register student account
8. Enroll in course
9. Submit quiz
10. Verify dashboard updates
11. Verify professor risk and grading review actions

## 4. Optional AI provider config
Configure `.env` with Azure/OpenAI/HF values and restart app.

## 5. Health check
`GET /health` should return JSON with provider name.
