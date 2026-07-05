"""
Session 57: External Terminal — 对标 VSCode externalTerminal contrib

提供"在外部终端中打开"功能:
  - GET  /external-terminal/open?path=...  — 在系统默认终端中打开路径
  - GET  /external-terminal/supported       — 检查是否支持外部终端

支持的终端:
  - Windows: PowerShell / CMD / Windows Terminal
  - macOS:   Terminal.app / iTerm2
  - Linux:   gnome-terminal / x-terminal-emulator
"""
import os
import platform
import subprocess
import shutil
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter(prefix="/external-terminal", tags=["external-terminal"])

_current_os = platform.system()


def _find_terminal() -> tuple[str | None, list[str]]:
    """找出当前系统可用的终端和参数示例"""
    if _current_os == "Windows":
        # 优先级: Windows Terminal > PowerShell > CMD
        wt_path = shutil.which("wt") or os.path.expandvars(
            "%LOCALAPPDATA%\\Microsoft\\WindowsApps\\wt.exe"
        )
        if wt_path and os.path.exists(wt_path):
            return wt_path, ["-d", "{path}"]
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if pwsh:
            return pwsh, ["-NoExit", "-Command", "Set-Location '{path}'"]
        cmd = shutil.which("cmd")
        if cmd:
            return cmd, ["/K", "cd /D", "{path}"]
        return None, []

    elif _current_os == "Darwin":
        # macOS: iTerm > Terminal.app
        iterm = shutil.which("iTerm") or shutil.which("iTerm2")
        if iterm:
            return "open", ["-a", "iTerm", "{path}"]
        return "open", ["-a", "Terminal", "{path}"]

    else:
        # Linux
        for term in ["gnome-terminal", "x-terminal-emulator", "konsole", "xfce4-terminal", "xterm"]:
            path = shutil.which(term)
            if path:
                if term == "gnome-terminal":
                    return path, ["--working-directory={path}"]
                elif term in ("konsole", "xfce4-terminal"):
                    return path, ["--workdir", "{path}"]
                else:
                    return path, ["--working-directory", "{path}"]
        return None, []


def _is_git_bash_available() -> bool:
    """检测 Git Bash (Windows)"""
    if _current_os != "Windows":
        return False
    paths = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
    ]
    return any(os.path.exists(p) for p in paths)


def _find_git_bash() -> str | None:
    for p in [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\bin\bash.exe"),
    ]:
        if os.path.exists(p):
            return p
    return None


@router.get("/supported")
async def check_supported():
    """检查当前系统是否支持外部终端"""
    terminal, _ = _find_terminal()
    git_bash = _is_git_bash_available()
    git_bash_path = _find_git_bash() if git_bash else None

    return {
        "supported": terminal is not None,
        "os": _current_os,
        "terminal": str(terminal) if terminal else None,
        "terminal_type": (os.path.basename(str(terminal)) if terminal else None),
        "git_bash_available": git_bash,
        "git_bash_path": git_bash_path,
        "terminals": _list_all_terminals(),
    }


@router.get("/open")
async def open_in_terminal(
    path: str = Query(..., description="要打开的文件路径或目录路径"),
    terminal_type: str = Query("default", description="终端类型: default | git-bash"),
):
    """
    在外部终端中打开指定路径。
    如果是文件路径 → 打开所在文件夹
    如果是目录路径 → 直接打开该目录
    """
    target_path = Path(path).resolve()
    if not target_path.exists():
        # 文件可能不在磁盘上(虚拟/临时)，尝试父目录
        target_path = target_path.parent
        if not target_path.exists():
            return {
                "success": False,
                "error": f"路径不存在: {path}",
                "resolved_path": str(target_path),
            }

    # 转换为目录
    if not target_path.is_dir():
        target_path = target_path.parent

    target_dir = str(target_path)

    # Git Bash 选项 (Windows only)
    if terminal_type == "git-bash" and _current_os == "Windows":
        git_bash = _find_git_bash()
        if git_bash:
            try:
                subprocess.Popen(
                    [git_bash],
                    cwd=target_dir,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return {
                    "success": True,
                    "terminal": "Git Bash",
                    "path": target_dir,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    # 默认终端
    terminal_exe, args_template = _find_terminal()

    if not terminal_exe:
        # 最后回退: 用 OS 默认方式打开目录
        try:
            if _current_os == "Windows":
                os.startfile(target_dir)
            elif _current_os == "Darwin":
                subprocess.Popen(["open", target_dir])
            else:
                subprocess.Popen(["xdg-open", target_dir])
            return {
                "success": True,
                "terminal": "os-default",
                "path": target_dir,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"无可用终端: {e}",
            }

    # 使用找到的终端执行
    try:
        args = [arg.replace("{path}", target_dir) for arg in args_template]
        cmd = [terminal_exe] + args

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "success": True,
            "terminal": os.path.basename(terminal_exe),
            "path": target_dir,
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "terminal": os.path.basename(terminal_exe),
        }


def _list_all_terminals() -> list[dict]:
    """列出系统上所有可用终端"""
    terminals: list[dict] = []

    if _current_os == "Windows":
        # Windows Terminal
        wt = os.path.expandvars("%LOCALAPPDATA%\\Microsoft\\WindowsApps\\wt.exe")
        if os.path.exists(wt):
            terminals.append({"name": "Windows Terminal", "path": wt, "id": "default"})
        # PowerShell
        for name, exe in [("PowerShell 7", "pwsh.exe"), ("PowerShell 5", "powershell.exe")]:
            p = shutil.which(exe)
            if p:
                terminals.append({"name": name, "path": p, "id": "default" if len(terminals)==0 else exe.split('.')[0]})
        # CMD
        cmd = shutil.which("cmd")
        if cmd:
            terminals.append({"name": "命令提示符", "path": cmd, "id": "cmd"})
        # Git Bash
        if _is_git_bash_available():
            terminals.append({"name": "Git Bash", "path": _find_git_bash() or "", "id": "git-bash"})

    elif _current_os == "Darwin":
        terminals.append({"name": "Terminal.app", "path": "/System/Applications/Utilities/Terminal.app", "id": "default"})
        if shutil.which("iTerm"):
            terminals.append({"name": "iTerm2", "path": shutil.which("iTerm") or "iTerm", "id": "iterm"})

    else:
        for term in ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
            p = shutil.which(term)
            if p:
                terminals.append({"name": term, "path": p, "id": "default" if len(terminals)==0 else term})
                if len(terminals) == 0:
                    break

    return terminals
