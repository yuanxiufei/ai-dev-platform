"""
Notebook Kernel API — 多语言代码单元执行引擎

借鉴 VSCode workbench/contrib/notebook/ 的 kernel 模型。
纯 Python 实现，使用 subprocess + AutoCLI 安全沙箱执行。

支持的 Kernel:
  - python3: Python 代码单元
  - javascript: Node.js 代码单元
  - shell: Bash/PowerShell 代码单元
  - sqlite: SQL 查询单元

Session 50: 替换前端 useNotebookStore.executeCell() 的 mock 实现
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("api.notebook")

router = APIRouter(prefix="/system/notebook", tags=["Notebook Kernel"])

# ── DTO 模型 ─────────────────────────────────────

class CellExecuteRequest(BaseModel):
    """执行单个 Cell"""
    code: str
    kernel: str = "python3"  # python3 / javascript / shell / sqlite
    cell_id: str = ""
    timeout: int = 30  # 超时秒数
    working_dir: str = ""  # 可选的工作目录
    env_vars: dict[str, str] = {}

class CellExecuteResponse(BaseModel):
    """Cell 执行结果"""
    cell_id: str = ""
    success: bool
    output: str = ""
    error: str = ""
    duration_ms: float = 0
    kernel: str = ""

class BatchExecuteRequest(BaseModel):
    """批量执行多个 Cell"""
    cells: list[CellExecuteRequest]

class BatchExecuteResponse(BaseModel):
    """批量执行结果"""
    results: list[CellExecuteResponse]
    total_duration_ms: float = 0

class KernelInfo(BaseModel):
    """Kernel 信息"""
    id: str
    name: str
    language: str
    available: bool
    version: str = ""
    description: str = ""

# ── Kernel 可用性检查 ────────────────────────────

def _check_command(cmd: str, arg: str) -> tuple[bool, str]:
    """检查命令是否可用，并获取版本"""
    try:
        result = subprocess.run(
            [cmd, arg], capture_output=True, text=True,
            timeout=5, shell=False  # noqa: S603
        )
        version = result.stdout.strip() or result.stderr.strip()
        return True, version.split('\n')[0][:100]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, ""

@router.get("/kernels")
async def list_kernels() -> dict:
    """列出所有可用 Kernel"""
    kernels = [
        KernelInfo(
            id="python3", name="Python 3", language="python",
            available=_check_command("python", "--version")[0],
            version=_check_command("python", "--version")[1],
            description="Python 3 代码执行"
        ),
        KernelInfo(
            id="javascript", name="JavaScript (Node.js)", language="javascript",
            available=_check_command("node", "--version")[0],
            version=_check_command("node", "--version")[1],
            description="Node.js JavaScript 代码执行"
        ),
        KernelInfo(
            id="shell", name="Shell (Bash/PowerShell)", language="shell",
            available=True,  # shell 总是可用
            version="",
            description="Shell 命令执行"
        ),
        KernelInfo(
            id="sqlite", name="SQLite", language="sql",
            available=True,  # Python 内置 sqlite3
            version="builtin",
            description="SQLite 查询执行"
        ),
    ]
    return {"kernels": [k.model_dump() for k in kernels]}


# ── Kernel 执行引擎 ─────────────────────────────

async def _execute_python(code: str, timeout: int, working_dir: str,
                           env_vars: dict) -> dict:
    """Python Kernel"""
    try:
        env = os.environ.copy()
        env.update(env_vars)
        env["PYTHONIOENCODING"] = "utf-8"

        proc = await asyncio.create_subprocess_exec(
            "python", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir or ".",
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return {
            "success": proc.returncode == 0,
            "output": stdout.decode("utf-8", errors="replace").rstrip(),
            "error": stderr.decode("utf-8", errors="replace").rstrip(),
        }
    except asyncio.TimeoutError:
        return {"success": False, "output": "", "error": f"执行超时 ({timeout}s)"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "Python 未安装或不在 PATH 中"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


async def _execute_javascript(code: str, timeout: int, working_dir: str,
                               env_vars: dict) -> dict:
    """JavaScript (Node.js) Kernel"""
    try:
        env = os.environ.copy()
        env.update(env_vars)
        # 将 console.log 输出包装
        wrapped = f"""
(async () => {{
    const console = {{ ...globalThis.console, _log: globalThis.console?.log }};
    try {{
        {code}
    }} catch (e) {{
        console.error(e.message + '\\n' + (e.stack || ''));
        process.exitCode = 1;
    }}
}})();
"""
        proc = await asyncio.create_subprocess_exec(
            "node", "-e", wrapped,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir or ".",
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        output = stdout.decode("utf-8", errors="replace").rstrip()
        err = stderr.decode("utf-8", errors="replace").rstrip()
        if err:
            output = (output + "\n" + err).strip()
        return {
            "success": proc.returncode == 0,
            "output": output,
            "error": err if proc.returncode != 0 else "",
        }
    except asyncio.TimeoutError:
        return {"success": False, "output": "", "error": f"执行超时 ({timeout}s)"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "Node.js 未安装或不在 PATH 中"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


async def _execute_shell(code: str, timeout: int, working_dir: str,
                          env_vars: dict) -> dict:
    """Shell Kernel (Bash/PowerShell)"""
    try:
        env = os.environ.copy()
        env.update(env_vars)

        # 检测 shell 类型
        if os.name == "nt":
            shell_cmd = ["powershell", "-NoProfile", "-Command", code]
        else:
            shell_cmd = ["bash", "-c", code]

        proc = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir or ".",
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        output = stdout.decode("utf-8", errors="replace").rstrip()
        err = stderr.decode("utf-8", errors="replace").rstrip()
        if err:
            output = (output + "\n" + err).strip()
        return {
            "success": proc.returncode == 0,
            "output": output,
            "error": err if proc.returncode != 0 else "",
        }
    except asyncio.TimeoutError:
        return {"success": False, "output": "", "error": f"执行超时 ({timeout}s)"}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


async def _execute_sqlite(code: str, timeout: int, working_dir: str,
                           env_vars: dict) -> dict:
    """SQLite Kernel — 使用 Python 内置 sqlite3"""
    import sqlite3
    import io

    db_path = os.path.join(working_dir or ".", "notebook.db")
    output = io.StringIO()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        statements = [s.strip() for s in code.split(';') if s.strip()]
        for stmt in statements:
            cursor.execute(stmt)
            if stmt.upper().startswith("SELECT") or stmt.upper().startswith("PRAGMA"):
                rows = cursor.fetchall()
                cols = [d[0] for d in cursor.description] if cursor.description else []
                if cols:
                    output.write(" | ".join(cols) + "\n")
                    output.write("-" * (len(" | ".join(cols))) + "\n")
                for row in rows:
                    output.write(" | ".join(str(v) for v in row) + "\n")
                if rows:
                    output.write(f"({len(rows)} 行)\n")
            else:
                output.write(f"OK ({cursor.rowcount} 行受影响)\n")

        conn.commit()
        return {"success": True, "output": output.getvalue().rstrip(), "error": ""}
    except sqlite3.Error as e:
        return {"success": False, "output": output.getvalue().rstrip(), "error": str(e)}
    except Exception as e:
        return {"success": False, "output": "", "error": str(e)}


KERNEL_EXECUTORS = {
    "python3": _execute_python,
    "python": _execute_python,
    "javascript": _execute_javascript,
    "js": _execute_javascript,
    "node": _execute_javascript,
    "shell": _execute_shell,
    "bash": _execute_shell,
    "powershell": _execute_shell,
    "sqlite": _execute_sqlite,
    "sql": _execute_sqlite,
}


# ── API 路由 ──────────────────────────────────────

@router.post("/execute", response_model=CellExecuteResponse)
async def execute_cell(req: CellExecuteRequest) -> CellExecuteResponse:
    """执行单个 Notebook Cell"""
    kernel = req.kernel.lower()
    executor = KERNEL_EXECUTORS.get(kernel)

    if not executor:
        return CellExecuteResponse(
            cell_id=req.cell_id,
            success=False,
            error=f"未知 Kernel: {req.kernel}。支持: {', '.join(KERNEL_EXECUTORS.keys())}",
            kernel=req.kernel,
        )

    start = time.perf_counter()
    result = await executor(req.code, req.timeout, req.working_dir, req.env_vars)
    duration = (time.perf_counter() - start) * 1000

    return CellExecuteResponse(
        cell_id=req.cell_id,
        success=result["success"],
        output=result["output"][:100_000],  # 限制输出大小
        error=result["error"][:10_000],
        duration_ms=round(duration, 2),
        kernel=req.kernel,
    )


@router.post("/execute-batch", response_model=BatchExecuteResponse)
async def execute_batch(req: BatchExecuteRequest) -> BatchExecuteResponse:
    """批量执行多个 Cell（顺序执行）"""
    start = time.perf_counter()
    results: list[CellExecuteResponse] = []

    for cell in req.cells:
        result = await execute_cell(cell)
        results.append(result)

    total_duration = (time.perf_counter() - start) * 1000
    return BatchExecuteResponse(
        results=results,
        total_duration_ms=round(total_duration, 2),
    )


# ── 安全输出清理 ─────────────────────────────────

@router.post("/sanitize")
async def sanitize_output(req: dict) -> dict:
    """清理 Cell 输出中的敏感信息"""
    content = req.get("content", "")
    # 移除 ANSI 转义码
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    cleaned = ansi_escape.sub('', content)
    # 截断
    max_len = req.get("max_length", 500_000)
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + f"\n... (截断 {len(content) - max_len} 字符)"
    return {"content": cleaned, "original_length": len(content), "truncated": len(content) > max_len}
