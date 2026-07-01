"""
Sandbox 抽象基类 — 统一的沙箱接口

借鉴 DeerFlow sandbox/sandbox.py Sandbox ABC 设计：
- 可插拔 Provider 架构（Local / Docker / 未来 K8s 等）
- 路径安全策略通过子类实现
- 所有 I/O 操作必须经过此接口
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxConfig:
    """沙箱配置"""
    type: str = "local"  # local | docker
    workspace_dir: str = "."
    """工作区目录（宿主机路径）"""
    allowed_paths: list[str] = field(default_factory=list)
    """白名单路径（空 = 允许工作区所有路径）"""
    denied_paths: list[str] = field(default_factory=list)
    """黑名单路径（如 /etc /sys /proc）"""
    command_timeout: float = 120.0
    """命令执行超时（秒）"""
    max_output_bytes: int = 1024 * 1024
    """命令输出最大字节数（1MB）"""
    # Session 09: 进程资源限制 (0 = 不限制)
    resource_memory_limit_mb: int = 512
    """内存限制 (MB)，0 为不限制。Unix: ulimit -v, Windows: 忽略"""
    resource_cpu_limit_seconds: int = 60
    """CPU 时间限制 (秒)，0 为不限制。Unix: ulimit -t"""
    resource_max_processes: int = 50
    """最大进程数限制，0 为不限制。Unix: ulimit -u"""
    resource_max_file_size_mb: int = 500
    """最大写入文件大小 (MB)，0 为不限制。Unix: ulimit -f"""
    # Docker 专用
    docker_image: str = "python:3.11-slim"
    docker_container_id: str = ""
    docker_network_disabled: bool = True
    # K8s 专用 (Session 09)
    k8s_namespace: str = "ai-sandbox"
    k8s_image: str = "python:3.12-slim"
    k8s_cpu_limit: str = "2"
    k8s_memory_limit: str = "4Gi"
    k8s_cpu_request: str = "500m"
    k8s_memory_request: str = "1Gi"
    k8s_ttl_seconds: int = 3600
    k8s_network_policy: str = "deny-all"


@dataclass
class CommandResult:
    """命令执行结果"""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    truncated: bool = False
    latency_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        """合并输出"""
        return (self.stdout + "\n" + self.stderr).strip()


@dataclass
class FileInfo:
    """文件元信息"""
    path: str
    size: int = 0
    is_dir: bool = False
    modified_at: float = 0.0


class Sandbox(ABC):
    """沙箱抽象基类

    所有工具调用的文件/Shell 操作必须通过此接口，子类实现隔离策略。
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    # ── 命令执行 ────────────────────────────────────

    @abstractmethod
    async def execute_command(self, command: str, cwd: str | None = None) -> CommandResult:
        """在沙箱中执行 Shell 命令"""
        ...

    # ── 文件操作 ─────────────────────────────────────

    @abstractmethod
    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        """读取文件内容"""
        ...

    @abstractmethod
    async def write_file(self, path: str, content: str, encoding: str = "utf-8") -> None:
        """写入文件（覆盖）"""
        ...

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """检查文件/目录是否存在"""
        ...

    @abstractmethod
    async def list_dir(self, path: str, max_depth: int = 1) -> list[FileInfo]:
        """列出目录内容"""
        ...

    @abstractmethod
    async def delete_file(self, path: str) -> None:
        """删除文件"""
        ...

    @abstractmethod
    async def glob(self, path: str, pattern: str) -> tuple[list[str], bool]:
        """按通配符查找文件，返回 (matches, truncated)"""
        ...

    @abstractmethod
    async def grep(self, path: str, pattern: str) -> list[dict[str, Any]]:
        """在文件中搜索文本，返回 [{path, line_number, line}]"""
        ...

    # ── 安全校验 ─────────────────────────────────────

    def validate_path(self, path: str) -> str:
        """校验路径安全性，返回规范化的绝对路径。

        若路径在黑名单中，抛出 PermissionError。
        """
        import os

        abs_path = os.path.abspath(os.path.join(self.config.workspace_dir, path))

        # 检查黑名单
        for denied in self.config.denied_paths:
            denied_abs = os.path.abspath(denied)
            if abs_path.startswith(denied_abs):
                raise PermissionError(
                    f"Path '{path}' is in denied paths ({denied})"
                )

        # 检查白名单（若配置了白名单）
        if self.config.allowed_paths:
            for allowed in self.config.allowed_paths:
                allowed_abs = os.path.abspath(allowed)
                if abs_path.startswith(allowed_abs):
                    return abs_path
            raise PermissionError(
                f"Path '{path}' is not in allowed paths"
            )

        # 默认：仅允许工作区路径
        workspace_abs = os.path.abspath(self.config.workspace_dir)
        if not abs_path.startswith(workspace_abs):
            raise PermissionError(
                f"Path '{path}' is outside workspace '{self.config.workspace_dir}'"
            )

        return abs_path

    async def close(self) -> None:
        """清理沙箱资源"""
        pass


class SandboxProvider:
    """沙箱工厂 — 根据配置类型创建对应的 Sandbox 实例"""

    _registry: dict[str, type[Sandbox]] = {}

    @classmethod
    def register(cls, name: str, sandbox_cls: type[Sandbox]) -> None:
        cls._registry[name] = sandbox_cls

    @classmethod
    def create(cls, config: SandboxConfig) -> Sandbox:
        sandbox_cls = cls._registry.get(config.type)
        if sandbox_cls is None:
            raise ValueError(f"Unknown sandbox type: '{config.type}'. Available: {list(cls._registry.keys())}")
        return sandbox_cls(config)
