@echo off
chcp 65001 >nul 2>&1
title 阿里云 DDNS 自动更新
echo ============================================
echo   阿里云 DDNS 动态域名更新工具
echo   AI Fullstack Platform — Standalone WOL 套件
echo ============================================
echo.

cd /d "%~dp0"

REM 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

REM 检查配置文件
if not exist "aliddns_config.json" (
    echo [提示] 首次运行，进入配置向导...
    echo.
    python aliddns.py --setup
    if %errorlevel% neq 0 (
        echo.
        echo [错误] 配置失败，请检查后重试
        pause
        exit /b 1
    )
)

echo [启动] DDNS 守护进程...
echo         按 Ctrl+C 停止
echo.

python aliddns.py

pause
