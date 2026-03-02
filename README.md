# ReLearnAI – Adaptive Learning Loop with Human Oversight
**Team: exe.stoppedworking** | Microsoft AI Learning & Education Hackathon

---

## 🎯 The Problem

Students generate rich interaction data—quiz attempts, timestamps, question types, misconceptions—yet learning platforms remain **largely blind** to evolving mastery. Students ask:

- *Which concepts am I truly weak in versus careless mistakes?*
- *Am I actually improving over time?*
- *What should I study next if I have limited time?*
- *Why do I struggle with the same types of problems repeatedly?*

Without a transparent, adaptive model of learning state, guidance is **generic, uninspiring, and untrustworthy**.

---

## 💡 The Solution: ReLearnAI

A closed-loop learning system that **continuously models student mastery**, generates **AI-powered quizzes and tutoring**, and keeps **educators in control** via human oversight and verification.

### The Core Loop

```
Upload Lecture Material
        ↓
AI Diagnoses Prerequisite Gaps
        ↓
Professor Approves/Edits Skill Map & Quiz Items (Human-in-Loop)
        ↓
Student Takes Adaptive Quiz + Chats with Grounded AI Tutor
        ↓
System Auto-Grades & Updates Mastery Scores
        ↓
Dashboard Recommends Next-Best Actions (with explanations)
        ↓
Professor Reviews Alerts & Confirms/Overrides Decisions (Audit Trail)
        ↓
Loop Repeats with Refined Understanding
```

---

## ✨ Key Features

### 🤖 AI Tutor with Grounded Answers
- Chat interface powered by RAG (Retrieval-Augmented Generation)
- All answers cite specific sections from uploaded course material
- Fallback to template-based responses if no API key is provided
- Real-time feedback on student questions

### 📊 Intelligent Skill Diagnostics
- Automatically infers prerequisite skill map from course material
- Identifies knowledge gaps from quiz performance
- Tracks **mastery** (understanding), **struggle** (difficulty), and **risk** (concerning patterns)
- Generates **SnapScore**—a dynamic recommendation score based on learning state

### 🎓 Adaptive Quiz Generation
- AI-generated quiz items targeting weak prerequisite skills
- Human verification before deployment
- Free-text answer grading with detailed feedback
- Repeated assessments detect improvement or regression

### 👨‍🏫 Professor Dashboard
- **Skill Map Viewer**: approve/edit inferred prerequisites
- **Risk Alerts**: flag at-risk students with actionable insights
- **Grade Review**: see reasoning behind autograding decisions
- **Override Controls**: change scores and recommendations with logged rationale
- **Audit Trail**: track all human interventions and why

### 📈 Transparent Recommendations
- Next-best-action suggestions with clear explanations
- Risk scores justify professor alerts
- Deterministic logic (same inputs → same outputs)
- No black-box decisions

---

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python)
- **Database**: SQLite for efficient local deployment
- **NLP & Grading**: OpenAI API / Azure OpenAI / Hugging Face (configurable)
- **Retrieval**: Lexical search over course material chunks
- **Frontend**: Jinja2 templates + vanilla JavaScript + Bootstrap
- **API**: RESTful endpoints with CORS support

---

## 🚀 Quick Start

### Local Run

#### Prerequisites
- Python 3.11 or 3.12
- Optional: `OPENAI_API_KEY` or Azure OpenAI credentials (falls back to mock if not set)

#### Installation

```bash
# Clone or navigate to repo
cd DL-Week-26

# Create virtual environment
python -m venv .venv

# If PowerShell script policy blocks activation, run this first
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1
# Or on macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

If you hit a `psycopg2-binary` build error on newer Python versions, use Python 3.11/3.12.

#### Run the Application

```bash
uvicorn app.main:app --reload --port 8000
```

Keep this terminal running while using the app.
Open `http://127.0.0.1:8000` in your browser.
Press `Ctrl + C` in the terminal to stop the server.

The web UI will launch with:
1. **Student Interface**: Register -> Upload/select course -> Take quiz -> Chat with tutor -> View progress
2. **Professor Interface**: Login -> Review skill map -> Approve items -> Audit grades -> Override decisions

---

## 📁 Project Structure

```
DL-Week-26/
├── app/                          # FastAPI application
│   ├── main.py                   # App entry point + all routes
│   ├── config.py                 # Settings & LLM provider config
│   ├── db.py                     # SQLite schema & queries
│   ├── security.py               # Authentication & hashing
│   ├── services/                 # Core business logic
│   │   ├── llm.py                # LLM abstraction (OpenAI, Azure, HF, mock)
│   │   ├── mastery.py            # Mastery computation & scoring
│   │   ├── pdf_utils.py          # PDF text extraction
│   │   ├── platform.py           # AI verification, journeys, reputation
│   │   ├── retrieval.py          # RAG & text chunking
│   │   └── skill_map.py          # Skill inference & prerequisites
│   ├── templates/                # HTML pages (student, professor, auth)
│   └── static/                   # JavaScript & CSS
├── docs/                         # Detailed documentation
│   ├── FINAL_PROPOSAL.md         # Solution overview
│   ├── JUDGING_ALIGNMENT.md      # How we meet judging criteria
│   ├── ARCHITECTURE.md           # Technical architecture
│   ├── PROJECT_DOCUMENTATION.md  # Deep dive
│   ├── STEP_BY_STEP_BEGINNER.md  # Tutorial for first run
│   └── DEPLOY_RENDER.md          # Production deployment guide
├── testbench/                    # Smoke tests & judge run scripts
├── requirements.txt              # Python dependencies
├── README.md                     # This file
└── run.sh                        # Helper launch script
```

---

## 🧪 Testing & Validation

Run the smoke test suite:

```bash
python scripts/smoke_test.py
```

Check the testbench guide for step-by-step judge demo workflow:

```bash
cat testbench/SETUP_AND_RUN.md
```

---

## 📚 Documentation

- **[FINAL_PROPOSAL.md](docs/FINAL_PROPOSAL.md)** – Full problem & solution narrative
- **[JUDGING_ALIGNMENT.md](docs/JUDGING_ALIGNMENT.md)** – How we meet judging criteria
- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** – Technical deep dive & design decisions
- **[STEP_BY_STEP_BEGINNER.md](docs/STEP_BY_STEP_BEGINNER.md)** – First-time user guide
- **[DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md)** – Cloud deployment instructions

---

## 🎓 Real-World Impact

### For Students
- ✅ Transparent, adaptive learning path
- ✅ AI tutor grounded in actual course material
- ✅ Immediate feedback on understanding
- ✅ Motivation via mastery tracking & SnapScore

### For Educators
- ✅ Automated skill diagnostics (saves time)
- ✅ Human control over high-impact decisions
- ✅ Risk alerts for struggling students
- ✅ Audit-ready intervention logs

### For Institutions
- ✅ Scalable to multiple courses
- ✅ Integrable with existing LMS (Canvas, Blackboard)
- ✅ Responsible AI: explainable, verifiable, fair

---

## 🔐 Responsible AI Built-In

- **Transparency**: Every recommendation includes reasoning
- **Human Oversight**: Professors approve quizzes, override grades, confirm alerts
- **Fairness**: Risk flags are based on mastery data, not demographics
- **Data Privacy**: Only interaction signals stored; no PII
- **Auditability**: All decisions logged with timestamps & rationale

---

## 🤔 Frequently Asked Questions

**Q: Do I need an OpenAI API key?**  
A: No! The system falls back to template-based responses if no key is set. Full functionality works either way.

**Q: How long does the first run take?**  
A: Initial data indexing and schema setup: ~1–2 minutes. Demo quiz generation: ~30 seconds (depending on LLM provider).

**Q: Can I deploy this to the cloud?**  
A: Yes! See [DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md) for step-by-step Render deployment.

**Q: Is this just another quiz app?**  
A: No. ReLearnAI continuously models *evolving* mastery over time and recommends *personalized* next steps. It's a learning intelligence platform, not a question bank.

---

## 📊 What Makes This a Better Solution

| Criterion | Evidence |
|-----------|----------|
| **Innovation** | Human-in-loop AI + continuous mastery modeling + explainable recommendations = not seen before in ed-tech |
| **Execution** | End-to-end student + professor workflows fully implemented; real LLM integration; working UI |
| **Impact** | Addresses real gap in digital learning; scales to courses, professional upskilling, institutions |
| **Clarity** | Clear problem statement, focused scope (1 course, 1 journey), transparent design |
| **Microsoft Alignment** | Responsible AI principles baked in; actionable guidance; human agency paramount |

---
