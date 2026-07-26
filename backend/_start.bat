@echo off
cd /d d:\code\ai-fullstack-platform\backend
python -u -m uvicorn app.main:app --host 0.0.0.0 --port 18000 > d:\code\ai-fullstack-platform\backend-stderr3.log 2>&1
