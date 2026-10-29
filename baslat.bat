@echo off
cd /d "%~dp0"
if not exist .venv (
    echo Ilk kurulum yapiliyor...
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python app.py
