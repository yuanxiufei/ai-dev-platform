@echo off
cd /d d:\code\ai-fullstack-platform\backend
echo [1/3] Creating virtual environment...
D:\app\Python\Python312\python.exe -m venv .venv
echo [2/3] Installing main dependencies...
.venv\Scripts\python.exe -m pip install -e . -q
echo [3/3] Installing RAG extras...
.venv\Scripts\python.exe -m pip install sentence-transformers faiss-cpu psycopg[binary] aiohttp aiosqlite -q
echo.
echo === Done! Starting backend... ===
start "Backend-18000" .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 18000 --reload
echo Backend started on http://localhost:18000
pause
