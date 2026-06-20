"""
DockerSandbox — Docker 容器隔离沙箱

借鉴 Trae Agent docker_tool_executor + docker_manager 设计：
- 支持从 Docker Hub image / 已有 container / Dockerfile / tar 文件 启动
- 自动卷挂载工作区
- 透明路径翻译（host ↔ container）
- pexpect 持久化 shell 会话
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from app.core.sandbox.base import CommandResult, FileInfo, Sandbox, SandboxConfig

logger = logging.getLogger("sandbox.docker")


class DockerSandbox(Sandbox):
    """Docker 容器沙箱"""

    CONTAINER_WORKSPACE = "/workspace"

    def __init__(self, config: SandboxConfig | None = None) -> None:
        super().__init__(config)
        self._container_id: str = ""
        self._shell_process: Any = None

    async def _ensure_container(self) -> None:
        """确保容器正在运行"""
        if self._shell_process is not None:
            # 检查容器是否还活着
            try:
                import docker
                client = docker.from_env()
                container = client.containers.get(self._container_id)
                if container.status != "running":
                    self._shell_process = None
            except Exception:
                self._shell_process = None

        if self._shell_process is None:
            await self._start_container()

    async def _start_container(self) -> None:
        """启动 Docker 容器"""
        try:
            import docker

            client = docker.from_env()
            workspace_abs = os.path.abspath(self.config.workspace_dir)

            # 挂载配置
            volumes = {
                workspace_abs: {
                    "bind": self.CONTAINER_WORKSPACE,
                    "mode": "rw",
                }
            }

            # 网络配置
            network_mode = "none" if self.config.docker_network_disabled else "bridge"

            if self.config.docker_container_id:
                # 附加到已有容器
                container = client.containers.get(self.config.docker_container_id)
                self._container_id = container.id
                logger.info("Attached to existing container: %s", self._container_id[:12])
            else:
                # 创建新容器
                container = client.containers.run(
                    self.config.docker_image,
                    command="tail -f /dev/null",
                    volumes=volumes,
                    network_mode=network_mode,
                    working_dir=self.CONTAINER_WORKSPACE,
                    detach=True,
                    remove=True,
                    mem_limit="2g",
                    cpu_period=100000,
                    cpu_quota=200000,
                )
                self._container_id = container.id
                logger.info(
                    "Docker container started: id=%s image=%s",
                    self._container_id[:12],
                    self.config.docker_image,
                )

        except ImportError:
            raise RuntimeError(
                "Docker support requires 'docker' package. Install: pip install docker"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to start Docker container: {e}")

    def _translate_path(self, host_path: str) -> str:
        """宿主机路径 → 容器内路径"""
        workspace_abs = os.path.abspath(self.config.workspace_dir)
        host_abs = os.path.abspath(host_path)
        if host_abs.startswith(workspace_abs):
            rel = os.path.relpath(host_abs, workspace_abs)
            return os.path.join(self.CONTAINER_WORKSPACE, rel)
        return host_path

    async def execute_command(self, command: str, cwd: str | None = None) -> CommandResult:
        await self._ensure_container()

        cwd = cwd or self.CONTAINER_WORKSPACE
        start = time.perf_counter()

        try:
            import docker

            client = docker.from_env()
            container = client.containers.get(self._container_id)

            exec_result = container.exec_run(
                f"cd {cwd} && {command}",
                stdout=True,
                stderr=True,
                user="root",
            )

            latency = (time.perf_counter() - start) * 1000
            stdout = exec_result.output.decode("utf-8", errors="replace")
            exit_code = exec_result.exit_code

            truncated = False
            if len(stdout) > self.config.max_output_bytes:
                stdout = stdout[:self.config.max_output_bytes] + "\n[OUTPUT TRUNCATED]"
                truncated = True

            return CommandResult(
                stdout=stdout,
                stderr="",
                exit_code=exit_code,
                truncated=truncated,
                latency_ms=latency,
            )

        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return CommandResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                latency_ms=latency,
            )

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        abs_path = self.validate_path(path)
        try:
            with open(abs_path, "r", encoding=encoding) as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}")

    async def write_file(self, path: str, content: str, encoding: str = "utf-8") -> None:
        abs_path = self.validate_path(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding=encoding) as f:
            f.write(content)

    async def file_exists(self, path: str) -> bool:
        try:
            abs_path = self.validate_path(path)
            return os.path.exists(abs_path)
        except PermissionError:
            return False

    async def list_dir(self, path: str, max_depth: int = 1) -> list[FileInfo]:
        from app.core.sandbox.local import LocalSandbox
        # 复用 LocalSandbox 的文件操作（因为 volume mount，宿主机文件系统可直接访问）
        local = LocalSandbox(self.config)
        return await local.list_dir(path, max_depth)

    async def delete_file(self, path: str) -> None:
        abs_path = self.validate_path(path)
        if os.path.isdir(abs_path):
            import shutil
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)

    async def glob(self, path: str, pattern: str) -> tuple[list[str], bool]:
        from app.core.sandbox.local import LocalSandbox
        local = LocalSandbox(self.config)
        return await local.glob(path, pattern)

    async def grep(self, path: str, pattern: str) -> list[dict[str, Any]]:
        from app.core.sandbox.local import LocalSandbox
        local = LocalSandbox(self.config)
        return await local.grep(path, pattern)

    async def close(self) -> None:
        if self._container_id:
            try:
                import docker
                client = docker.from_env()
                container = client.containers.get(self._container_id)
                container.stop(timeout=10)
                logger.info("Docker container stopped: %s", self._container_id[:12])
            except Exception as e:
                logger.warning("Failed to stop container: %s", e)
            finally:
                self._container_id = ""
                self._shell_process = None
