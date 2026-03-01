# DLW26 Hackathon Starter (LearnLoop AI)

This repo contains a complete starter for your hackathon idea:
- Proposal ready for submission/pitch: [`PROPOSAL_FINAL.md`](./PROPOSAL_FINAL.md)
- Submission-ready short proposal: [`FINAL_SHORT_PROPOSAL.md`](./FINAL_SHORT_PROPOSAL.md)
- Beginner click-by-click Colab workflow: [`COLAB_GUIDE.md`](./COLAB_GUIDE.md)
- Ready notebook file: [`DLW26_LearnLoop_MVP.ipynb`](./DLW26_LearnLoop_MVP.ipynb)
- Reusable code modules in `src/`
- Optional demo apps:
  - FastAPI backend: `backend/fastapi_app.py`
  - Streamlit dashboard (student + professor HITL): `frontend/streamlit_app.py`
- Judge testbench docs:
  - [`testbench/SETUP_AND_RUN.md`](./testbench/SETUP_AND_RUN.md)
  - [`testbench/TESTBENCH_CHECKLIST.md`](./testbench/TESTBENCH_CHECKLIST.md)
- Submission helper: [`SUBMISSION_CHECKLIST.md`](./SUBMISSION_CHECKLIST.md)

## MVP Features Implemented

- Upload 1 course PDF
- Chat with citations from uploaded material
- Diagnose weak prerequisite skills from assessment data
- Generate targeted micro-quiz
- Auto-grade student answer
- Update mastery + SnapScore and refresh next recommendation
- Professor human-in-the-loop panel:
  - Validate skill map
  - Override risk flags
  - Confirm/override grading

## Quick Local Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run backend:

```bash
uvicorn backend.fastapi_app:app --reload --port 8000
```

Run dashboard:

```bash
streamlit run frontend/streamlit_app.py
```

## Notes

- If `OPENAI_API_KEY` is not set, the app still works with template quiz generation.
- The first dataset load may take a few minutes in Colab or local.
- Keep the MVP scope to one course and one end-to-end student journey for demo.
