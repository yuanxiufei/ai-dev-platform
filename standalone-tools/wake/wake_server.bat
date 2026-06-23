@echo off
REM ========================================================
REM  一键唤醒家里电脑 — 双击即可使用
REM  目标: 家里电脑 (有线网卡)
REM ========================================================

chcp 65001 >nul
setlocal enabledelayedexpansion

REM ═══════════════════════════════════════════
REM  配置区域（按你的实际情况修改）
REM ═══════════════════════════════════════════

set "TARGET_MAC=34:5A:60:7F:2B:96"
set "TARGET_HOST=wake.reginyuan.com"
set "TARGET_PORT=9"

REM ═══════════════════════════════════════════

echo.
echo   ┌─────────────────────────────────────┐
echo   │     🖥️  远程唤醒 - 家里电脑           │
echo   └─────────────────────────────────────┘
echo.
echo   目标 MAC : %TARGET_MAC%
echo   唤醒地址 : %TARGET_HOST%:%TARGET_PORT%
echo.

python "%~dp0wake_server.py" --mac %TARGET_MAC% --broadcast %TARGET_HOST% --port %TARGET_PORT%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo   ✅ 魔术包已发送！电脑将在 10-60 秒内启动。
    echo.
    timeout /t 8 /nobreak > nul
) else (
    echo.
    echo   ❌ 发送失败，请检查网络连接。
    echo.
    pause
)

endlocal
