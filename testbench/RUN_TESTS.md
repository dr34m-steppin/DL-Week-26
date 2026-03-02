# Commands for Judges

```bash
cd /Users/amalthomasmanoj/Documents/ReLearnAI
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m py_compile app/main.py app/config.py app/db.py app/security.py app/services/*.py
python3 scripts/smoke_test.py
uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000`.
