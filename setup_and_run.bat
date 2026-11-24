@echo off
REM One-command setup + run for Windows: double-click or run  setup_and_run.bat
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements-dev.txt
if not exist .env copy .env.example .env
python manage.py migrate
echo.
echo Server starting at http://127.0.0.1:8000/  (Ctrl+C to stop)
python manage.py runserver
