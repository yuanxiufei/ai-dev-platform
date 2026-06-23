@echo off
chcp 65001 >nul 2>&1
title 安装 DDNS 开机自启服务
echo ============================================
echo   将阿里云DDNS注册为 Windows 开机自启任务
echo   AI Fullstack Platform — Standalone WOL 套件
echo ============================================
echo.

set SCRIPT_DIR=%~dp0
set TASK_NAME=AliDDNS-Updater
set BAT_PATH="%SCRIPT_DIR%run_aliddns.bat"

echo 脚本目录: %SCRIPT_DIR%
echo 任务名称: %TASK_NAME%
echo 启动文件: %BAT_PATH%
echo.

REM 检查是否已有同名任务
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [发现] 已有同名任务，正在删除...
    schtasks /delete /f /tn "%TASK_NAME%"
    echo.
)

echo [安装] 创建计划任务（开机自动运行，延迟60秒启动）...
echo.

schtasks /create /f /tn "%TASK_NAME%" /tr "%BAT_PATH%" /sc onstart /delay 0001:00 /rl HIGHEST /it

if %errorlevel% equ 0 (
    echo.
    echo ✅ 安装成功！
    echo.
    echo   任务信息:
    echo   - 名称: %TASK_NAME%
    echo   - 触发器: 用户登录时自动启动
    echo   - 延迟: 60秒（等待网络就绪）
    echo   - 脚本: %BAT_PATH%
    echo.
    echo   其他操作:
    echo   - 查看任务:  schtasks /query /tn "%TASK_NAME%" /v
    echo   - 手动运行:  schtasks /run /tn "%TASK_NAME%"
    echo   - 删除任务:  schtasks /delete /f /tn "%TASK_NAME%"
    echo.
    echo   现在可以关闭此窗口。电脑开机后会自动运行DDNS更新。
) else (
    echo.
    echo ❌ 安装失败！可能需要管理员权限。
    echo   请右键 → 以管理员身份运行此脚本。
)

echo.
pause
