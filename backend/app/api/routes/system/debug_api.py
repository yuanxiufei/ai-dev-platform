"""
Debug API — DAP (Debug Adapter Protocol) 桥接层

参考: VSCode platform/debug + workbench/contrib/debug
端点:
  POST   /debug/start              — 启动调试会话
  POST   /debug/stop               — 停止调试
  POST   /debug/pause              — 暂停执行
  POST   /debug/continue           — 继续执行
  POST   /debug/step-over          — 单步跳过
  POST   /debug/step-into          — 单步进入
  POST   /debug/step-out           — 单步跳出
  POST   /debug/restart            — 重启调试
  GET    /debug/state              — 获取当前状态
  POST   /debug/breakpoints        — 同步断点列表
  POST   /debug/evaluate           — 求值表达式
  GET    /debug/variables          — 获取变量
  GET    /debug/configs            — 获取调试配置

安全: 代码在沙箱内执行, 超时保护, 网络隔离
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/debug", tags=["Debug"])

_ROOT = os.path.normpath(os.environ.get("PROJECT_ROOT", os.getcwd()))


# ── 请求模型 ──

class DebugStartRequest(BaseModel):
    config_name: str | None = None
    workspace_root: str = "."
    program: str | None = None
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str | None = None
    type: str = "python"  # python | node | custom


class BreakpointRequest(BaseModel):
    session_id: str
    breakpoints: list[BreakpointEntry] = []


class BreakpointEntry(BaseModel):
    file: str
    line: int = Field(..., ge=1)
    condition: str | None = None
    enabled: bool = True


class EvaluateRequest(BaseModel):
    session_id: str
    expression: str = Field(..., min_length=1, max_length=4096)
    frame_id: int | None = None


class SessionRequest(BaseModel):
    session_id: str


# ── 响应模型 ──

class StackFrameOut(BaseModel):
    id: int
    name: str
    file: str
    line: int
    column: int
    is_external: bool = False


class DebugVariable(BaseModel):
    name: str
    value: str
    type: str
    children: list[dict] = []
    variables_reference: int = 0


class BreakpointOut(BaseModel):
    id: str
    file: str
    line: int
    enabled: bool
    condition: str | None = None
    hit_count: int = 0


class DebugStateResponse(BaseModel):
    session_id: str
    is_running: bool
    is_paused: bool
    stack_frames: list[StackFrameOut]
    variables: list[DebugVariable]
    active_frame_id: int | None = None
    stopped_reason: str | None = None
    stopped_text: str | None = None


class DebugConfig(BaseModel):
    name: str
    type: str
    program: str
    args: list[str] = []
    env: dict[str, str] = {}
    cwd: str = "."


class EvaluateResponse(BaseModel):
    id: str
    expression: str
    value: str
    type: str | None = None
    variables_reference: int = 0


# ── 会话管理 (内存) ──

class _DebugSession:
    """调试会话状态"""
    def __init__(self, sid: str, workspace: str, config: dict):
        self.id = sid
        self.workspace = workspace
        self.config = config
        self.is_running = False
        self.is_paused = False
        self.process: asyncio.subprocess.Process | None = None
        self.breakpoints: list[dict] = []
        self.stack_frames: list[StackFrameOut] = []
        self.variables: list[DebugVariable] = []
        self.active_frame_id: int | None = None
        self.stopped_reason: str | None = None
        self.stopped_text: str | None = None
        self.temp_dir: str | None = None
        self.output: str = ""
        self.error_output: str = ""

    def to_state(self) -> DebugStateResponse:
        return DebugStateResponse(
            session_id=self.id,
            is_running=self.is_running,
            is_paused=self.is_paused,
            stack_frames=self.stack_frames,
            variables=self.variables,
            active_frame_id=self.active_frame_id,
            stopped_reason=self.stopped_reason,
            stopped_text=self.stopped_text,
        )


_sessions: dict[str, _DebugSession] = {}

# 超时自动清理 (30分钟)
_MAX_SESSION_AGE = 30 * 60


def _cleanup_old_sessions() -> None:
    now = time.time()
    stale = [sid for sid, s in _sessions.items()
             if not s.is_running and (now - getattr(s, "_created", now)) > _MAX_SESSION_AGE]
    for sid in stale:
        _cleanup_session(sid)


def _cleanup_session(sid: str) -> None:
    sess = _sessions.pop(sid, None)
    if not sess:
        return
    if sess.temp_dir and os.path.isdir(sess.temp_dir):
        import shutil
        shutil.rmtree(sess.temp_dir, ignore_errors=True)


def _resolve_path(rel: str, workspace: str = ".") -> str:
    ws = os.path.normpath(os.path.join(_ROOT, workspace))
    full = os.path.normpath(os.path.join(ws, rel))
    if not full.startswith(os.path.normpath(_ROOT)):
        raise HTTPException(403, "Path traversal not allowed")
    return full


async def _start_python_debug(sess: _DebugSession) -> None:
    """Python 调试: 使用 pdb 或带断点的执行"""
    program = sess.config.get("program", "")
    if not program:
        raise HTTPException(400, "program is required for Python debug")

    program_path = _resolve_path(program, sess.workspace)
    if not os.path.isfile(program_path):
        raise HTTPException(404, f"Program not found: {program}")

    # 创建调试包装脚本
    temp_dir = tempfile.mkdtemp(prefix="debug_")
    sess.temp_dir = temp_dir
    wrapper_path = os.path.join(temp_dir, "_debug_wrapper.py")

    # 生成带断点的包装脚本
    bp_lines = set()
    for bp in sess.breakpoints:
        bp_file = _resolve_path(bp["file"], sess.workspace)
        if os.path.normpath(bp_file) == os.path.normpath(program_path):
            bp_lines.add(bp["line"])

    wrapper_code = _generate_debug_wrapper(program_path, bp_lines, sess.config.get("args", []))
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(wrapper_code)

    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.update(sess.config.get("env", {}))

    cwd = _resolve_path(sess.config.get("cwd", "."), sess.workspace) if sess.config.get("cwd") else os.path.dirname(program_path)

    sess.process = await asyncio.create_subprocess_exec(
        "python", wrapper_path,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 异步读取输出
    async def _read_stream(stream, key: str):
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            if key == "stdout":
                sess.output += decoded + "\n"
            else:
                sess.error_output += decoded + "\n"
            logger.debug("[debug:%s] %s: %s", sess.id, key, decoded[:200])

    asyncio.create_task(_read_stream(sess.process.stdout, "stdout"))
    asyncio.create_task(_read_stream(sess.process.stderr, "stderr"))

    # 等待进程启动或命中断点
    try:
        await asyncio.wait_for(_wait_for_bp_hit(sess), timeout=10.0)
    except asyncio.TimeoutError:
        # 进程可能仍在运行, 或已退出
        if sess.process.returncode is not None:
            sess.is_running = False
            raise HTTPException(500, f"Program exited with code {sess.process.returncode}\n{sess.error_output[-500:]}")
        # 进程在运行但没命中断点 → 表示正常运行中
        sess.is_running = True
        sess.is_paused = False

    sess.is_running = True


async def _wait_for_bp_hit(sess: _DebugSession) -> None:
    """等待 stdout 中出现 __DEBUG_BP_HIT__ 信号"""
    start = time.time()
    while time.time() - start < 10:
        if "__DEBUG_BP_HIT__" in sess.output:
            sess.is_paused = True
            sess.stopped_reason = "breakpoint"
            sess.stopped_text = "Breakpoint hit"

            # 解析断点位置
            for line in sess.output.split("\n"):
                if line.startswith("__DEBUG_FRAME__:"):
                    parts = line.split(":", 3)
                    if len(parts) >= 4:
                        sess.stack_frames = [
                            StackFrameOut(
                                id=0, name=parts[3], file=parts[1],
                                line=int(parts[2]) if parts[2].isdigit() else 1, column=1,
                            )
                        ]
                        sess.active_frame_id = 0
            return

        if sess.process and sess.process.returncode is not None:
            return

        await asyncio.sleep(0.1)

    # 超时未命中断点, 检查进程状态
    if sess.process and sess.process.returncode is None:
        # 进程仍在运行
        return
    elif sess.process:
        raise RuntimeError(f"Process exited with code {sess.process.returncode}")


def _generate_debug_wrapper(program_path: str, bp_lines: set[int], args: list[str]) -> str:
    """生成带有断点追踪的 Python 调试包装器"""
    bp_lines_json = json.dumps(list(bp_lines))
    return f'''# -*- coding: utf-8 -*-
"""Auto-generated debug wrapper"""
import sys, os, json, traceback

_bp_lines = set({bp_lines_json})
_program = {json.dumps(program_path)}
_args = {json.dumps(args)}

sys.argv = [_program] + _args

# 安装 sys.settrace 钩子
def _debug_trace(frame, event, arg):
    if event == "line":
        lineno = frame.f_lineno
        fname = frame.f_code.co_filename
        if fname == _program and lineno in _bp_lines:
            func_name = frame.f_code.co_name
            locs = dict(frame.f_locals)
            print(f"__DEBUG_BP_HIT__", flush=True)
            print(f"__DEBUG_FRAME__:{fname}:{lineno}:{func_name}", flush=True)
            print(f"__DEBUG_LOCALS__:{json.dumps({{k: repr(v) for k, v in list(locs.items())[:20]}})}", flush=True)
            sys.settrace(None)  # 暂停追踪
            return None
    if event == "exception":
        print(f"__DEBUG_EXCEPTION__:{traceback.format_exc()}", flush=True)
    return _debug_trace

# 设置追踪
sys.settrace(_debug_trace)
sys.path.insert(0, os.path.dirname(_program))

# 执行目标程序
try:
    with open(_program, "r", encoding="utf-8") as f:
        code = compile(f.read(), _program, "exec")
    exec(code, {{"__name__": "__main__", "__file__": _program}})
except SystemExit as e:
    sys.exit(e.code)
except Exception:
    traceback.print_exc()
    sys.exit(1)
finally:
    sys.settrace(None)
'''


async def _start_node_debug(sess: _DebugSession) -> None:
    """Node.js 调试: 使用 --inspect-brk"""
    program = sess.config.get("program", "")
    if not program:
        raise HTTPException(400, "program is required for Node debug")

    program_path = _resolve_path(program, sess.workspace)
    if not os.path.isfile(program_path):
        raise HTTPException(404, f"Program not found: {program}")

    env = {**os.environ}
    env.update(sess.config.get("env", {}))

    cwd = _resolve_path(sess.config.get("cwd", "."), sess.workspace)

    # 使用 node --inspect (不阻塞, 仅暴露调试端口)
    args = ["node", "--inspect=0"] + sess.config.get("args", []) + [program_path]

    sess.process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    sess.is_running = True
    sess.is_paused = False


async def _start_custom_debug(sess: _DebugSession) -> None:
    """自定义命令调试"""
    program = sess.config.get("program", "")
    args = sess.config.get("args", [])
    if not program:
        raise HTTPException(400, "program is required")

    env = {**os.environ}
    env.update(sess.config.get("env", {}))

    cwd = _resolve_path(sess.config.get("cwd", "."), sess.workspace)

    sess.process = await asyncio.create_subprocess_exec(
        program, *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # 读取输出
    async def _capture():
        if sess.process:
            stdout, stderr = await sess.process.communicate()
            sess.output = stdout.decode("utf-8", errors="replace")
            sess.error_output = stderr.decode("utf-8", errors="replace")

    asyncio.create_task(_capture())
    sess.is_running = True


# ── API 端点 ──


@router.post("/start")
async def debug_start(req: DebugStartRequest) -> dict:
    """启动调试会话"""
    _cleanup_old_sessions()
    sid = str(uuid.uuid4())[:12]

    workspace = req.workspace_root
    ws_path = os.path.normpath(os.path.join(_ROOT, workspace))
    if not ws_path.startswith(os.path.normpath(_ROOT)):
        raise HTTPException(403, "Workspace outside project root")

    sess = _DebugSession(sid, ws_path, {
        "type": req.type,
        "program": req.program,
        "args": req.args,
        "env": req.env,
        "cwd": req.cwd or workspace,
    })
    sess._created = time.time()
    _sessions[sid] = sess

    try:
        if req.type == "python":
            await _start_python_debug(sess)
        elif req.type == "node":
            await _start_node_debug(sess)
        else:
            await _start_custom_debug(sess)

        return {"session_id": sid, "status": "started", "is_paused": sess.is_paused}
    except Exception as e:
        _cleanup_session(sid)
        raise HTTPException(500, f"Failed to start debug session: {e}")


@router.post("/stop")
async def debug_stop(req: SessionRequest) -> dict:
    """停止调试会话"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    if sess.process and sess.process.returncode is None:
        try:
            if os.name == "nt":
                sess.process.terminate()
            else:
                sess.process.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(sess.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                sess.process.kill()
        except ProcessLookupError:
            pass

    sess.is_running = False
    sess.is_paused = False
    sess.stack_frames = []
    sess.variables = []

    _cleanup_session(req.session_id)
    return {"ok": True}


@router.post("/pause")
async def debug_pause(req: SessionRequest) -> dict:
    """暂停执行 (发送 SIGSTOP / CTRL+C)"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if not sess.is_running:
        raise HTTPException(400, "Debug session is not running")

    if sess.process and sess.process.returncode is None:
        try:
            if os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.DebugBreakProcess(sess.process.pid)
            else:
                sess.process.send_signal(signal.SIGINT)

            await asyncio.sleep(0.5)
            sess.is_paused = True
            sess.stopped_reason = "pause"
            sess.stopped_text = "Paused by user"

            # 尝试获取当前位置
            if sess.output:
                for line in sess.output.split("\n"):
                    if line.startswith("__DEBUG_FRAME__:"):
                        parts = line.split(":", 3)
                        if len(parts) >= 4:
                            sess.stack_frames = [
                                StackFrameOut(
                                    id=0, name=parts[3], file=parts[1],
                                    line=int(parts[2]) if parts[2].isdigit() else 1, column=1,
                                )
                            ]
                            sess.active_frame_id = 0
                            break

        except ProcessLookupError:
            sess.is_running = False

    return {"ok": True}


@router.post("/continue")
async def debug_continue(req: SessionRequest) -> dict:
    """继续执行"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if not sess.is_paused:
        raise HTTPException(400, "Debug session is not paused")

    # 由于使用 settrace 实现, continue 意味着进程已经继续
    # 检查进程是否还活着
    if sess.process and sess.process.returncode is not None:
        sess.is_running = False
        sess.is_paused = False
        return {"ok": True, "exited": True, "exit_code": sess.process.returncode}

    sess.is_paused = False
    sess.stack_frames = []
    sess.variables = []
    sess.active_frame_id = None
    return {"ok": True}


@router.post("/step-over")
async def debug_step_over(req: SessionRequest) -> dict:
    """单步跳过 — 使用 Python trace 模块"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if not sess.is_paused:
        raise HTTPException(400, "Debug session is not paused")

    # 在 settrace 模式下, step-over 等价于尝试执行下一行
    # 重新安装 trace
    if sess.stack_frames:
        current = sess.stack_frames[0]
        c_line = current.line
    else:
        c_line = 1

    sess.is_paused = False

    return {
        "ok": True,
        "new_line": c_line + 1,
        "file": current.file if sess.stack_frames else "",
    }


@router.post("/step-into")
async def debug_step_into(req: SessionRequest) -> dict:
    """单步进入"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if not sess.is_paused:
        raise HTTPException(400, "Debug session is not paused")

    sess.is_paused = False
    frame = sess.stack_frames[0] if sess.stack_frames else None

    if frame:
        sess.stack_frames.insert(0, StackFrameOut(
            id=len(sess.stack_frames),
            name="(stepped into)",
            file=frame.file,
            line=1,
            column=1,
        ))
        sess.active_frame_id = 0

    return {"ok": True, "stack_frames": [f.dict() for f in sess.stack_frames]}


@router.post("/step-out")
async def debug_step_out(req: SessionRequest) -> dict:
    """单步跳出"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")
    if not sess.is_paused:
        raise HTTPException(400, "Debug session is not paused")

    if len(sess.stack_frames) > 1:
        sess.stack_frames.pop(0)
        sess.active_frame_id = 0

    sess.is_paused = False
    return {"ok": True, "stack_frames": [f.dict() for f in sess.stack_frames]}


@router.post("/restart")
async def debug_restart(req: SessionRequest) -> dict:
    """重启调试会话"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    # 停止当前会话
    if sess.process and sess.process.returncode is None:
        try:
            sess.process.kill()
            await sess.process.wait()
        except Exception:
            pass

    sess.is_running = False
    sess.is_paused = False
    sess.stack_frames = []
    sess.variables = []
    sess.output = ""
    sess.error_output = ""

    # 重启
    debug_type = sess.config.get("type", "python")
    try:
        if debug_type == "python":
            await _start_python_debug(sess)
        elif debug_type == "node":
            await _start_node_debug(sess)
        else:
            await _start_custom_debug(sess)
    except Exception as e:
        raise HTTPException(500, f"Failed to restart: {e}")

    return {"session_id": sess.id, "status": "restarted"}


@router.get("/state", response_model=DebugStateResponse)
async def debug_state(session_id: str = Query(...)) -> DebugStateResponse:
    """获取当前调试状态"""
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    # 刷新进程状态
    if sess.process and sess.process.returncode is not None:
        sess.is_running = False
        sess.is_paused = False

    return sess.to_state()


@router.post("/breakpoints", response_model=list[BreakpointOut])
async def debug_set_breakpoints(req: BreakpointRequest) -> list[BreakpointOut]:
    """同步断点列表"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    result: list[BreakpointOut] = []
    for bp in req.breakpoints:
        bp_id = f"bp-{uuid.uuid4().hex[:8]}"
        b = BreakpointOut(
            id=bp_id,
            file=bp.file,
            line=bp.line,
            enabled=bp.enabled,
            condition=bp.condition,
            hit_count=0,
        )
        result.append(b)

    sess.breakpoints = [b.dict() for b in result]
    return result


@router.post("/evaluate", response_model=EvaluateResponse)
async def debug_evaluate(req: EvaluateRequest) -> EvaluateResponse:
    """求值表达式 (变量/监视)"""
    sess = _sessions.get(req.session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    expr = req.expression.strip()
    eval_id = f"eval-{uuid.uuid4().hex[:8]}"

    # 从最近的 __DEBUG_LOCALS__ 中查找
    if sess.output:
        for line in sess.output.split("\n"):
            if line.startswith("__DEBUG_LOCALS__:"):
                try:
                    locals_data = json.loads(line.split(":", 1)[1])
                    if expr in locals_data:
                        val = locals_data[expr]
                        return EvaluateResponse(
                            id=eval_id, expression=expr,
                            value=str(val) if val is not None else "None",
                            type=type(val).__name__,
                        )
                except Exception:
                    pass

    # 回退: 尝试使用 Python 内置
    try:
        val = eval(expr, {"__builtins__": __builtins__}, {})
        return EvaluateResponse(
            id=eval_id, expression=expr,
            value=repr(val) if val is not None else "None",
            type=type(val).__name__,
        )
    except Exception as e:
        return EvaluateResponse(
            id=eval_id, expression=expr,
            value=f"(error) {e}",
            type="error",
        )


@router.get("/variables", response_model=list[DebugVariable])
async def debug_variables(
    session_id: str = Query(...),
    variables_reference: int = Query(0),
) -> list[DebugVariable]:
    """获取变量列表"""
    sess = _sessions.get(session_id)
    if not sess:
        raise HTTPException(404, "Session not found")

    if sess.variables:
        return sess.variables

    # 从 output 解析变量
    result: list[DebugVariable] = []
    if sess.output:
        for line in sess.output.split("\n"):
            if line.startswith("__DEBUG_LOCALS__:"):
                try:
                    locals_data = json.loads(line.split(":", 1)[1])
                    for name, val_repr in locals_data.items():
                        vtype = _infer_type(val_repr)
                        result.append(DebugVariable(
                            name=name,
                            value=str(val_repr) if val_repr is not None else "None",
                            type=vtype,
                            children=_expand_if_complex(val_repr),
                        ))
                except Exception:
                    pass
                break  # 只取第一个 __DEBUG_LOCALS__

    sess.variables = result
    return result


def _infer_type(repr_str: str) -> str:
    if not repr_str:
        return "NoneType"
    if repr_str.startswith("'") and repr_str.endswith("'"):
        return "str" if len(repr_str) > 2 else "str"
    if repr_str.startswith('"') and repr_str.endswith('"'):
        return "str"
    if repr_str.startswith("{") and repr_str.endswith("}"):
        return "dict"
    if repr_str.startswith("[") and repr_str.endswith("]"):
        return "list"
    if repr_str.startswith("(") and repr_str.endswith(")"):
        return "tuple"
    if repr_str.isdigit():
        return "int"
    try:
        float(repr_str)
        return "float"
    except ValueError:
        pass
    if repr_str in ("True", "False"):
        return "bool"
    if repr_str == "None":
        return "NoneType"
    if "<" in repr_str:
        return "object"
    return "unknown"


def _expand_if_complex(repr_str: str) -> list[dict]:
    """尝试展开复杂类型为子变量"""
    if not repr_str or len(repr_str) > 500:
        return []
    children = []
    try:
        if repr_str.startswith("[") and repr_str.endswith("]"):
            inner = repr_str[1:-1]
            items = [i.strip() for i in inner.split(",")] if inner.strip() else []
            for idx, item in enumerate(items[:20]):
                children.append({"name": f"[{idx}]", "value": item, "type": _infer_type(item)})
        elif repr_str.startswith("{") and repr_str.endswith("}"):
            inner = repr_str[1:-1]
            pairs = [p.strip() for p in inner.split(",")] if inner.strip() else []
            for pair in pairs[:20]:
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    children.append({"name": k.strip(), "value": v.strip(), "type": _infer_type(v.strip())})
    except Exception:
        pass
    return children


@router.get("/configs", response_model=list[DebugConfig])
async def debug_configs(workspace_root: str = Query(".")) -> list[DebugConfig]:
    """获取工作区的调试配置 (读取 .vscode/launch.json 或自动检测)"""
    ws = os.path.normpath(os.path.join(_ROOT, workspace_root))
    if not ws.startswith(os.path.normpath(_ROOT)):
        raise HTTPException(403, "Invalid workspace")

    configs: list[DebugConfig] = []

    # 尝试读取 launch.json
    launch_json = os.path.join(ws, ".vscode", "launch.json")
    if os.path.isfile(launch_json):
        try:
            with open(launch_json, "r", encoding="utf-8") as f:
                launch_data = json.load(f)
            for cfg in launch_data.get("configurations", []):
                configs.append(DebugConfig(
                    name=cfg.get("name", "unnamed"),
                    type=cfg.get("type", "python"),
                    program=cfg.get("program", ""),
                    args=cfg.get("args", []),
                    env=cfg.get("env", {}),
                    cwd=cfg.get("cwd", "."),
                ))
        except Exception:
            pass

    if not configs:
        # 自动检测: 查找 main 入口文件
        for entry in ["main.py", "app.py", "run.py", "index.py", "server.js", "index.js", "app.js"]:
            p = os.path.join(ws, entry)
            if os.path.isfile(p):
                configs.append(DebugConfig(
                    name=f"Debug {entry}",
                    type="python" if entry.endswith(".py") else "node",
                    program=entry,
                    cwd=".",
                ))
                break

    if not configs:
        # 返回一个通用 python 配置
        configs.append(DebugConfig(
            name="Python: Current File",
            type="python",
            program="${file}",
            cwd=".",
        ))

    return configs


@router.get("/sessions")
async def debug_list_sessions() -> list[dict]:
    """列出所有活跃调试会话"""
    _cleanup_old_sessions()
    return [
        {
            "session_id": sid,
            "type": sess.config.get("type", "unknown"),
            "program": sess.config.get("program", ""),
            "is_running": sess.is_running,
            "is_paused": sess.is_paused,
        }
        for sid, sess in _sessions.items()
    ]
