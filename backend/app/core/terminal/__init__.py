"""
终端/PTY 管理 — 借鉴 OpenVSCode Server 远程终端架构

核心组件:
  - TerminalProcessManager  — 进程生命周期管理（进程状态机）
  - RemotePtyChannel         — 远程终端 IPC 通道（RPC 协议）
  - PTYProcessBackend        — 伪终端后端（pty 创建/I/O 复用）

注意: PTY 功能仅 Linux/macOS 可用，Windows 下自动降级为 NoOp 后端。
"""
from __future__ import annotations

import asyncio
import os
import signal
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import logging

logger = logging.getLogger(__name__)

# PTY 仅在 Unix 平台可用
_PTY_AVAILABLE = sys.platform != "win32"
if _PTY_AVAILABLE:
    import pty


# ══════════════════════════════════════════════
# 数据类型定义
# ══════════════════════════════════════════════

class TerminalProcessState(str, Enum):
    """终端进程状态机 — 借鉴 VS Code TerminalProcessManager"""
    UNINITIALIZED = "uninitialized"
    LAUNCHING = "launching"
    RUNNING = "running"
    KILLED = "killed"


@dataclass
class TerminalSize:
    """终端窗口尺寸"""
    rows: int = 24
    cols: int = 80


@dataclass
class PTYProcess:
    """PTY 进程描述"""
    pid: int
    fd: int  # master fd
    process: subprocess.Popen | None = None
    state: TerminalProcessState = TerminalProcessState.UNINITIALIZED


# ══════════════════════════════════════════════
# RPC 协议定义 — 借鉴 RemoteTerminalChannel
# ══════════════════════════════════════════════

class RemotePtyRequest(str, Enum):
    """远程PTY RPC请求类型"""
    CREATE_PROCESS = "create_process"
    START = "start"
    INPUT = "input"
    RESIZE = "resize"
    SHUTDOWN = "shutdown"
    GET_CWD = "get_cwd"


class RemotePtyEvent(str, Enum):
    """远程PTY RPC事件类型"""
    ON_DATA = "on_data"
    ON_EXIT = "on_exit"
    ON_READY = "on_ready"
    ON_TITLE_CHANGED = "on_title_changed"


# ══════════════════════════════════════════════
# PTY 进程后端 — 借鉴 LocalPty + BasePty
# ══════════════════════════════════════════════

class PTYProcessBackend:
    """PTY 进程后端

    管理伪终端进程的整个生命周期，包括:
    - 进程创建（fork pty + exec shell）
    - I/O 多路复用（主从端读写）
    - 进程退出检测
    - 窗口大小调整
    """

    def __init__(self) -> None:
        self._processes: dict[str, PTYProcess] = {}
        self._read_tasks: dict[str, asyncio.Task] = {}
        self._data_callbacks: dict[str, Callable[[str, bytes], Any]] = {}
        self._exit_callbacks: dict[str, Callable[[str, int], Any]] = {}

    def create_process(
        self,
        session_id: str,
        shell: str = "/bin/bash",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        size: TerminalSize | None = None,
    ) -> str:
        """创建伪终端进程

        Args:
            session_id: 终端会话 ID
            shell: 使用的 shell
            cwd: 工作目录
            env: 环境变量
            size: 初始窗口大小

        Returns:
            终端 ID（Windows 下返回占位 ID 并标记为 UNINITIALIZED）
        """
        terminal_id = f"{session_id}_{id(self)}_{len(self._processes)}"
        size = size or TerminalSize()

        if not _PTY_AVAILABLE:
            logger.warning("PTY not available on Windows, terminal=%s", terminal_id)
            self._processes[terminal_id] = PTYProcess(
                pid=-1,
                fd=-1,
                state=TerminalProcessState.UNINITIALIZED,
            )
            return terminal_id

        try:
            # 使用 pty.openpty() 创建伪终端
            master_fd, slave_fd = pty.openpty()

            shell_path = shell
            if not os.path.isabs(shell_path):
                # 尝试从 PATH 查找
                import shutil
                found = shutil.which(shell)
                shell_path = found or "/bin/sh"

            proc_env = os.environ.copy()
            if cwd:
                proc_env["HOME"] = cwd
            if env:
                proc_env.update(env)

            process = subprocess.Popen(
                [shell_path],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=cwd or os.getcwd(),
                env=proc_env,
                preexec_fn=os.setsid,
                close_fds=True,
            )

            # 关闭从端 fd（已交给子进程）
            os.close(slave_fd)

            self._processes[terminal_id] = PTYProcess(
                pid=process.pid,
                fd=master_fd,
                process=process,
                state=TerminalProcessState.LAUNCHING,
            )

            # 启动读取循环
            self._start_read_loop(terminal_id)

            # 标记为运行中
            self._processes[terminal_id].state = TerminalProcessState.RUNNING
            logger.info(
                "PTY created: terminal_id=%s pid=%d shell=%s",
                terminal_id, process.pid, shell_path,
            )

        except OSError:
            # 降级: 无 pty 时使用 subprocess pipe
            logger.warning("pty.openpty() failed, falling back to pipe")
            process = subprocess.Popen(
                ["/bin/sh"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=cwd or os.getcwd(),
                env=env,
            )
            self._processes[terminal_id] = PTYProcess(
                pid=process.pid,
                fd=-1,  # 无 pty fd
                process=process,
                state=TerminalProcessState.RUNNING,
            )

        return terminal_id

    def write(self, terminal_id: str, data: str) -> None:
        """向终端进程写入数据"""
        proc = self._processes.get(terminal_id)
        if not proc or proc.state != TerminalProcessState.RUNNING:
            return

        try:
            if proc.fd > 0:
                os.write(proc.fd, data.encode())
            elif proc.process and proc.process.stdin:
                proc.process.stdin.write(data.encode())
                proc.process.stdin.flush()
        except (OSError, BrokenPipeError) as e:
            logger.warning("Write to terminal %s failed: %s", terminal_id, e)

    def resize(self, terminal_id: str, rows: int, cols: int) -> None:
        """调整终端窗口大小（SIGWINCH）"""
        if not _PTY_AVAILABLE:
            return
        proc = self._processes.get(terminal_id)
        if not proc or proc.fd <= 0:
            return

        try:
            import fcntl
            import termios

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(proc.fd, termios.TIOCSWINSZ, winsize)
            if proc.pid > 0:
                os.kill(proc.pid, signal.SIGWINCH)
        except (ImportError, OSError) as e:
            logger.debug("Terminal resize not supported: %s", e)

    def shutdown(self, terminal_id: str, force: bool = False) -> None:
        """关闭终端进程"""
        proc = self._processes.get(terminal_id)
        if not proc:
            return

        proc.state = TerminalProcessState.KILLED

        # 发送信号
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            if proc.pid > 0:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(proc.pid), sig)
                else:
                    os.kill(proc.pid, sig)
        except OSError:
            pass

        # 关闭 fd
        if proc.fd > 0:
            try:
                os.close(proc.fd)
            except OSError:
                pass

        # 等待进程
        if proc.process:
            try:
                proc.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.process.kill()

        # 清理
        self._processes.pop(terminal_id, None)
        task = self._read_tasks.pop(terminal_id, None)
        if task and not task.done():
            task.cancel()
        logger.info("PTY shutdown: terminal_id=%s", terminal_id)

    def on_data(self, terminal_id: str, callback: Callable[[str, bytes], Any]) -> None:
        """注册数据回调"""
        self._data_callbacks[terminal_id] = callback

    def on_exit(self, terminal_id: str, callback: Callable[[str, int], Any]) -> None:
        """注册退出回调"""
        self._exit_callbacks[terminal_id] = callback

    def _start_read_loop(self, terminal_id: str) -> None:
        """启动异步读取循环"""
        loop = asyncio.get_event_loop()
        self._read_tasks[terminal_id] = loop.create_task(
            self._read_loop(terminal_id)
        )

    async def _read_loop(self, terminal_id: str) -> None:
        """异步读取 PTY 输出"""
        proc = self._processes.get(terminal_id)
        if not proc or proc.fd <= 0:
            return

        loop = asyncio.get_event_loop()
        data_cb = self._data_callbacks.get(terminal_id)
        exit_cb = self._exit_callbacks.get(terminal_id)

        try:
            while proc.state == TerminalProcessState.RUNNING:
                try:
                    data = await loop.run_in_executor(
                        None, os.read, proc.fd, 4096
                    )
                    if not data:
                        break
                    if data_cb:
                        await data_cb(terminal_id, data) if asyncio.iscoroutinefunction(data_cb) else data_cb(terminal_id, data)
                except OSError:
                    break

            # 进程退出
            if proc.process:
                exit_code = proc.process.wait()
                if exit_cb:
                    await exit_cb(terminal_id, exit_code) if asyncio.iscoroutinefunction(exit_cb) else exit_cb(terminal_id, exit_code)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("PTY read loop error for %s: %s", terminal_id, e)

    def get_cwd(self, terminal_id: str) -> str | None:
        """获取终端当前工作目录（通过 /proc 或 cwd 属性）"""
        if not _PTY_AVAILABLE:
            return None
        proc = self._processes.get(terminal_id)
        if not proc or proc.pid <= 0:
            return None
        try:
            cwd_link = f"/proc/{proc.pid}/cwd"
            if os.path.exists(cwd_link):
                return os.readlink(cwd_link)
        except OSError:
            pass
        return None

    def list_terminals(self) -> list[dict[str, Any]]:
        """列出所有活跃终端"""
        result: list[dict[str, Any]] = []
        for tid, proc in self._processes.items():
            result.append({
                "terminal_id": tid,
                "pid": proc.pid,
                "state": proc.state.value,
                "cwd": self.get_cwd(tid),
            })
        return result

    def shutdown_all(self) -> None:
        """关闭所有终端"""
        for tid in list(self._processes.keys()):
            self.shutdown(tid, force=True)


# ══════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════

_pty_backend: PTYProcessBackend | None = None


def init_pty_backend() -> PTYProcessBackend:
    """初始化 PTY 后端"""
    global _pty_backend
    _pty_backend = PTYProcessBackend()
    return _pty_backend


def get_pty_backend() -> PTYProcessBackend | None:
    """获取 PTY 后端（全局单例）"""
    return _pty_backend
