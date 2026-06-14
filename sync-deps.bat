@echo off
cd /d d:\code\ai-fullstack-platform
echo Installing dependencies...
uv sync
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Dependencies installed successfully!
) else (
    echo.
    echo ❌ uv sync failed with error code %ERRORLEVEL%
)
pause
