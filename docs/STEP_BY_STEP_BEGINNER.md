# Step-by-Step Beginner Guide (Zero to Demo)

## Part A: What to open first
1. Open Terminal
2. Run:
   ```bash
   cd /Users/amalthomasmanoj/Documents/ReLearnAI
   ```
3. Open this folder in your editor (VS Code recommended)
4. Keep one terminal tab for running the app

## Part B: Run locally
1. Create virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure env:
   ```bash
   cp .env.example .env
   ```
4. Start server:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Open browser: `http://127.0.0.1:8000`

## Part C: Configure Azure OpenAI (optional but recommended)

### 1. In Azure portal / AI Foundry
1. Create Azure OpenAI resource (student credits)
2. Deploy one chat model (example: `gpt-4o-mini`)
3. Copy:
   - endpoint URL
   - API key
   - deployment name

### 2. Put in `.env`
```env
LLM_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_DEPLOYMENT=<deployment-name>
AZURE_OPENAI_API_VERSION=2024-10-21
```

### 3. Restart server
Stop and rerun:
```bash
uvicorn app.main:app --reload
```

## Part D: Exact demo order

### Professor side
1. Register as professor
2. Create course
3. Upload `docs/sample_course_doc.txt` (or your own PDF)
4. Click `Generate Skill Map`
5. Validate a few skill nodes
6. Click `Generate Quiz Bank`
7. Approve at least 5 questions

### Student side
1. Register as student (new browser/incognito)
2. Enroll in same course
3. Start diagnostic quiz
4. Submit answers
5. Open dashboard
6. Ask tutor question

### Human-in-loop proof
1. Back to professor page
2. Override one risk flag
3. Confirm/override one grading review

## Part E: GitHub submission prep
1. Initialize git (if needed):
   ```bash
   git init
   git add .
   git commit -m "Initial hackathon submission"
   ```
2. Create public GitHub repo
3. Push code
4. Confirm these files exist:
   - `README.md`
   - `testbench/SETUP_AND_RUN.md`
   - `testbench/SMOKE_TEST_CHECKLIST.md`
   - `docs/PROJECT_DOCUMENTATION.pdf`
   - `docs/VIDEO_SCRIPT.md`

## Part F: 1-2 min video recording flow
1. Start on login page
2. Professor flow (upload + generate + approve)
3. Student flow (quiz + dashboard + tutor)
4. Professor HITL override
5. Close with impact statement

## Part G: If AI key is not ready
Use default mock provider.
The full workflow still runs and is valid for end-to-end demonstration.
