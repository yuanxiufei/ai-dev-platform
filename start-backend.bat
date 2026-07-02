@echo off
chcp 65001 >nul
cd /d "%~dp0backend"

echo Killing all processes on port 18000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":18000.*LISTENING"') do (
    taskkill /F /PID %%a 2>nul && echo Killed PID %%a
)

timeout /t 2 /nobreak >nul

echo.
echo Starting backend on port 18000...
python -m uvicorn app.main:app --host 0.0.0.0 --port 18000 --log-level info

pause
