#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

if ! python3 - <<'PY' >/dev/null 2>&1
import fastapi  # noqa: F401
PY
then
  pip install -r requirements.txt
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
fi

uvicorn app.main:app --reload --env-file .env
