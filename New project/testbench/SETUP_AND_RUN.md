# Testbench Setup and Run Guide

This document is for graders to reproduce the LearnLoop AI MVP quickly.

## 1) Environment

- OS tested: macOS / Linux
- Python: 3.10+
- Network: required for Kaggle download and optional OpenAI calls

## 2) Clone and install

```bash
git clone <YOUR_PUBLIC_REPO_URL>
cd <YOUR_REPO_NAME>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3) Optional API key setup (recommended)

```bash
export OPENAI_API_KEY="<YOUR_OPENAI_KEY>"
```

If no key is provided, fallback logic is used for quiz and grading.

## 4) Run Streamlit MVP (recommended judging path)

```bash
streamlit run frontend/streamlit_app.py
```

Open the local URL shown by Streamlit (usually `http://localhost:8501`).

## 5) End-to-end demo flow (required features)

1. Click `1) Load Assessment Dataset`.
2. Upload one course PDF in `Upload Course Material`.
3. Click `2) Build Course Knowledge Base`.
4. Enter a student doubt and click `3) Ask Tutor`.
5. Check answer + citations.
6. Click `4) Generate Targeted Micro-Quiz`.
7. Enter student answer and click `5) Auto-Grade + Update Mastery`.
8. In Professor Dashboard:
   - save skill map
   - save risk override
   - confirm or override grade

This proves the full loop:
Upload PDF -> Chat with citations -> Prerequisite quiz -> Auto-grade -> Mastery update -> Professor override.

## 6) Run API (optional)

```bash
uvicorn backend.fastapi_app:app --reload --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## 7) Colab path (optional)

- Open `DLW26_LearnLoop_MVP.ipynb`
- Run all cells in order (1 to 13)

## 8) Expected artifacts

- Professor decisions log: `data/professor_overrides.json`
- Working mastery updates in UI metrics and recommendation list

## 9) Troubleshooting

- Kaggle errors: authenticate Kaggle in Colab/local before download.
- Slow first run: dataset preprocessing and index building can take a few minutes.
- No OpenAI key: fallback mode still demonstrates the complete system loop.

