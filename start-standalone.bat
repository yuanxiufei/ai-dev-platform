@echo off
REM ════════════════════════════════════════════════════════
REM AI Fullstack Platform — Standalone Quick Launch (Windows)
REM ════════════════════════════════════════════════════════
REM 双击此文件即可启动独立运行环境
REM ════════════════════════════════════════════════════════

setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║     AI Fullstack Platform - Standalone Launcher      ║
echo ╚══════════════════════════════════════════════════════╝
echo.

REM ── 检查 Python ──
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11+
    pause
    exit /b 1
)
python --version

REM ── 检查 .env 文件 ──
if not exist ".env" (
    echo [WARN] .env file not found, creating from template...
    copy .env.standalone .env
    echo [INFO] Created .env from .env.standalone — please edit with your settings.
)

REM ── 设置环境变量 ──
set STANDALONE_MODE=1
set PROJECT_NAME=AI Fullstack Platform (Standalone)

REM ── 允许通过参数传递选项 ──
set EXTRA_ARGS=%*

echo.
echo [INFO] Starting standalone runtime...
echo        Use Ctrl+C to stop.
echo        Options: --no-watchdog --no-sleep --no-auth --port 8080
echo.

python standalone.py %EXTRA_ARGS%

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Standalone runtime exited with code %ERRORLEVEL%
    pause
)
endlocal
