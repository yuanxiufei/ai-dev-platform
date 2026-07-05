"""
Tasks API — 构建任务配置与执行引擎

参考: VSCode workbench/contrib/tasks
端点:
  GET    /tasks                    — 列出任务配置
  POST   /tasks                    — 创建任务配置
  PUT    /tasks/{name}             — 更新任务配置
  DELETE /tasks/{name}             — 删除任务配置
  POST   /tasks/{name}/run         — 执行任务 (返回 execution_id)
  GET    /tasks/executions/{id}    — 查询执行状态
  POST   /tasks/executions/{id}/cancel — 取消执行
  GET    /tasks/executions/{id}/output — 获取执行输出
  WS     /tasks/executions/{id}/ws     — WebSocket 实时输出

任务类型:
  - shell: 执行 shell 命令
  - npm/build: npm/yarn/pnpm 构建脚本
  - python: Python 脚本执行
  - docker: Docker 构建/运行
  - custom: 自定义命令序列

安全: 基于 AutoCLI 安全策略, 受 PROJECT_ROOT 限制
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/tasks", tags=["Tasks"])

_ROOT = os.path.normpath(os.environ.get("PROJECT_ROOT", os.getcwd()))
_CONFIG_PATH = os.path.join(_ROOT, ".data", "tasks.json")

os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)


# ── 任务配置模型 ──

class TaskDefinition(BaseModel):
    name: str
    type: str = "shell"  # shell | npm | python | docker | custom
    command: str = ""
    args: list[str] = []
    cwd: str = "."
    env: dict[str, str] = {}
    problem_matcher: str | None = None  # 关联问题匹配器
    depends_on: list[str] = []  # 前置任务
    presentation: dict[str, Any] = {}  # 展示配置
    label: str = ""
    detail: str = ""
    is_build: bool = False
    is_test: bool = False
    is_watch: bool = False


# ── 执行状态模型 ──

class TaskExecution:
    def __init__(self, exe_id: str, task: TaskDefinition):
        self.id = exe_id
        self.task_name = task.name
        self.task = task
        self.status: str = "pending"  # pending|running|completed|failed|cancelled
        self.started_at: float = 0
        self.finished_at: float = 0
        self.exit_code: int | None = None
        self.output: str = ""
        self.error_output: str = ""
        self.process: asyncio.subprocess.Process | None = None
        self._ws_clients: list[WebSocket] = []

    def to_dict(self) -> dict:
        return {
            "execution_id": self.id,
            "task_name": self.task_name,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "output_length": len(self.output),
        }


_executions: dict[str, TaskExecution] = {}


def _load_configs() -> list[TaskDefinition]:
    """加载任务配置"""
    if not os.path.isfile(_CONFIG_PATH):
        return []
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [TaskDefinition(**t) for t in data.get("tasks", [])]
    except Exception:
        return []


def _save_configs(configs: list[TaskDefinition]) -> None:
    """保存任务配置"""
    data = {
        "version": "2.0.0",
        "tasks": [t.dict() for t in configs],
    }
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_path(rel: str) -> str:
    full = os.path.normpath(os.path.join(_ROOT, rel))
    if not full.startswith(os.path.normpath(_ROOT)):
        raise HTTPException(403, "Path traversal not allowed")
    return full


async def _run_task_async(exe: TaskExecution) -> None:
    """异步执行任务"""
    task = exe.task
    cwd = _resolve_path(task.cwd)

    # 构建命令
    if task.type == "npm":
        cmd = ["npm", "run", task.command] + task.args
    elif task.type == "pnpm":
        cmd = ["pnpm", "run", task.command] + task.args
    elif task.type == "yarn":
        cmd = ["yarn", "run", task.command] + task.args
    elif task.type == "python":
        script_path = _resolve_path(task.command)
        cmd = ["python", script_path] + task.args
    elif task.type == "shell":
        if os.name == "nt":
            cmd = ["cmd", "/c", task.command] + task.args
        else:
            cmd = ["bash", "-c", task.command] + task.args
    elif task.type == "custom":
        cmd = [task.command] + task.args
    else:
        exe.status = "failed"
        exe.error_output = f"Unknown task type: {task.type}"
        return

    env = {**os.environ, **task.env}

    exe.status = "running"
    exe.started_at = time.time()

    try:
        exe.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _read_stream(stream, key: str):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                if key == "stdout":
                    exe.output += decoded
                else:
                    exe.error_output += decoded

                # 广播到 WebSocket 客户端
                for ws in exe._ws_clients[:]:
                    try:
                        await ws.send_json({"type": key, "data": decoded.rstrip("\n")})
                    except Exception:
                        exe._ws_clients.remove(ws)

        asyncio.create_task(_read_stream(exe.process.stdout, "stdout"))
        asyncio.create_task(_read_stream(exe.process.stderr, "stderr"))

        exe.exit_code = await exe.process.wait()

        exe.status = "completed" if exe.exit_code == 0 else "failed"
        exe.finished_at = time.time()

        # 通知 WebSocket 客户端任务结束
        for ws in exe._ws_clients[:]:
            try:
                await ws.send_json({
                    "type": "end",
                    "exit_code": exe.exit_code,
                    "status": exe.status,
                })
            except Exception:
                pass

    except Exception as e:
        exe.status = "failed"
        exe.error_output += f"\nTask execution error: {e}"
        exe.finished_at = time.time()
        logger.exception("Task execution failed")


# ── 端点 ──


@router.get("", response_model=list[TaskDefinition])
async def list_tasks() -> list[TaskDefinition]:
    """列出所有任务配置"""
    return _load_configs()


@router.post("", response_model=TaskDefinition)
async def create_task(task: TaskDefinition) -> TaskDefinition:
    """创建任务配置"""
    configs = _load_configs()

    if any(t.name == task.name for t in configs):
        raise HTTPException(409, f"Task '{task.name}' already exists")

    configs.append(task)
    _save_configs(configs)
    return task


@router.put("/{task_name}", response_model=TaskDefinition)
async def update_task(task_name: str, task: TaskDefinition) -> TaskDefinition:
    """更新任务配置"""
    configs = _load_configs()
    idx = next((i for i, t in enumerate(configs) if t.name == task_name), None)
    if idx is None:
        raise HTTPException(404, f"Task '{task_name}' not found")

    configs[idx] = task
    _save_configs(configs)
    return task


@router.delete("/{task_name}")
async def delete_task(task_name: str) -> dict:
    """删除任务配置"""
    configs = _load_configs()
    configs = [t for t in configs if t.name != task_name]
    _save_configs(configs)
    return {"ok": True}


@router.post("/{task_name}/run")
async def run_task(task_name: str) -> dict:
    """执行任务"""
    configs = _load_configs()
    task = next((t for t in configs if t.name == task_name), None)
    if not task:
        raise HTTPException(404, f"Task '{task_name}' not found")

    # 处理依赖任务
    for dep_name in task.depends_on:
        dep_task = next((t for t in configs if t.name == dep_name), None)
        if dep_task:
            dep_exe_id = str(uuid.uuid4())[:12]
            dep_exe = TaskExecution(dep_exe_id, dep_task)
            _executions[dep_exe_id] = dep_exe
            dep_exe.status = "running"
            dep_exe.started_at = time.time()
            await _run_task_async(dep_exe)
            if dep_exe.status == "failed":
                raise HTTPException(400, f"Dependency task '{dep_name}' failed")

    exe_id = str(uuid.uuid4())[:12]
    exe = TaskExecution(exe_id, task)
    _executions[exe_id] = exe

    asyncio.create_task(_run_task_async(exe))

    return {"execution_id": exe_id, "status": "started"}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str) -> dict:
    """查询执行状态"""
    exe = _executions.get(execution_id)
    if not exe:
        raise HTTPException(404, "Execution not found")
    return exe.to_dict()


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str) -> dict:
    """取消执行"""
    exe = _executions.get(execution_id)
    if not exe:
        raise HTTPException(404, "Execution not found")
    if exe.status not in ("running", "pending"):
        raise HTTPException(400, f"Cannot cancel execution in status '{exe.status}'")

    if exe.process and exe.process.returncode is None:
        try:
            if os.name == "nt":
                exe.process.kill()
            else:
                exe.process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass

    exe.status = "cancelled"
    exe.finished_at = time.time()
    return {"ok": True}


@router.get("/executions/{execution_id}/output")
async def get_execution_output(execution_id: str, tail: int = Query(5000)) -> dict:
    """获取执行输出 (可选 tail 截断)"""
    exe = _executions.get(execution_id)
    if not exe:
        raise HTTPException(404, "Execution not found")

    output = exe.output
    error = exe.error_output
    if tail > 0:
        output = output[-tail:]
        error = error[-tail:]

    return {
        "execution_id": execution_id,
        "status": exe.status,
        "exit_code": exe.exit_code,
        "stdout": output,
        "stderr": error,
    }


@router.websocket("/executions/{execution_id}/ws")
async def execution_ws(ws: WebSocket) -> None:
    """WebSocket 实时输出流"""
    # 从路径提取 execution_id
    exec_id = ws.path_params.get("execution_id", "")
    if not exec_id:
        await ws.close()
        return

    await ws.accept()

    exe = _executions.get(exec_id)
    if not exe:
        await ws.send_json({"type": "error", "data": "Execution not found"})
        await ws.close()
        return

    exe._ws_clients.append(ws)

    # 发送已有输出
    if exe.output:
        await ws.send_json({"type": "stdout", "data": exe.output[-2000:]})
    if exe.error_output:
        await ws.send_json({"type": "stderr", "data": exe.error_output[-2000:]})

    try:
        while True:
            # 保持连接, 等待消息 (心跳)
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if ws in exe._ws_clients:
            exe._ws_clients.remove(ws)


@router.post("/auto-detect", response_model=list[TaskDefinition])
async def auto_detect_tasks(workspace_root: str = Query(".")) -> list[TaskDefinition]:
    """自动检测工作区的构建任务 (package.json, Makefile, etc.)"""
    ws = _resolve_path(workspace_root)
    tasks: list[TaskDefinition] = []

    # 检查 package.json
    pkg_json = os.path.join(ws, "package.json")
    if os.path.isfile(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            scripts = pkg.get("scripts", {})
            for name in scripts:
                is_build = name in ("build", "compile", "dist", "package")
                is_test = "test" in name.lower()
                is_watch = "watch" in name.lower() or "dev" in name.lower()
                tasks.append(TaskDefinition(
                    name=f"npm:{name}",
                    type="npm",
                    command=name,
                    label=f"npm run {name}",
                    detail=f"npm run {name}",
                    is_build=is_build,
                    is_test=is_test,
                    is_watch=is_watch,
                ))
        except Exception:
            pass

    # 检查 Makefile
    for mf in ["Makefile", "makefile", "GNUmakefile"]:
        makefile_path = os.path.join(ws, mf)
        if os.path.isfile(makefile_path):
            tasks.append(TaskDefinition(
                name="make:build",
                type="shell",
                command="make",
                args=["build"] if os.name != "nt" else [],
                label="make build",
                detail="Build with Makefile",
                is_build=True,
            ))
            tasks.append(TaskDefinition(
                name="make:clean",
                type="shell",
                command="make",
                args=["clean"] if os.name != "nt" else [],
                label="make clean",
                detail="Clean build artifacts",
            ))
            break

    # 检查 pyproject.toml
    pyproject = os.path.join(ws, "pyproject.toml")
    if os.path.isfile(pyproject):
        tasks.append(TaskDefinition(
            name="python:build",
            type="shell",
            command="pip install -e ." if os.name != "nt" else "pip install -e .",
            label="pip install (editable)",
            detail="Install Python package in development mode",
            is_build=True,
        ))

    return tasks
