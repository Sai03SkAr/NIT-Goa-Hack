#!/usr/bin/env bash
cd "$(dirname "$0")/../backend"
PY=../.venv/bin/python
[ -x ../.venv/Scripts/python.exe ] && PY=../.venv/Scripts/python.exe  # Windows (Git Bash)
exec "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
