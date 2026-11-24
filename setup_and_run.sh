#!/usr/bin/env bash
# One-command setup + run for Mac / Linux:   bash setup_and_run.sh
set -e
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
[ -f .env ] || cp .env.example .env
python manage.py migrate
echo ""
echo "Server starting at http://127.0.0.1:8000/  (Ctrl+C to stop)"
python manage.py runserver
