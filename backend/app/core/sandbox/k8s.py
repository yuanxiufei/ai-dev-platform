"""
Kubernetes Sandbox Provider — run agent code in isolated K8s pods.

Session 09: K8sSandbox 现在继承 Sandbox ABC，已注册到 SandboxProvider。
文件操作通过 kubectl exec 实现（cat/ls/rm/mkdir/find/grep）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

from app.core.sandbox.base import (
    Sandbox,
    SandboxConfig,
    CommandResult,
    FileInfo,
    SandboxProvider,
)


@dataclass
class K8sSandboxConfig:
    """独立 K8s 配置（向后兼容，可直接注入 SandboxConfig 替代）。"""
    namespace: str = "ai-sandbox"
    image: str = "python:3.12-slim"
    cpu_limit: str = "2"
    memory_limit: str = "4Gi"
    cpu_request: str = "500m"
    memory_request: str = "1Gi"
    workspace_mount_path: str = "/workspace"
    network_policy: str = "deny-all"
    service_account: str = ""
    pod_annotations: dict = field(default_factory=dict)
    ttl_seconds: int = 3600
    node_selector: dict = field(default_factory=dict)
    gpu_resource: Optional[str] = None


class K8sSandbox(Sandbox):
    """Kubernetes pod-based sandbox for secure agent code execution.

    Session 09: 继承 Sandbox ABC，已注册到 SandboxProvider。
    文件操作通过 kubectl exec 实现，不需要 volume mount。

    Requires kubernetes Python client (`pip install kubernetes`).
    """

    CONTAINER_WORKSPACE = "/workspace"

    def __init__(self, config: SandboxConfig | None = None) -> None:
        super().__init__(config)
        self._pod_name: Optional[str] = None
        self._namespace = self.config.k8s_namespace
        self._k8s_available = False
        self._v1 = None
        self._core_v1 = None
        # 从 SandboxConfig 提取 K8s 参数
        self._k8s_image = self.config.k8s_image
        self._k8s_cpu_limit = self.config.k8s_cpu_limit
        self._k8s_memory_limit = self.config.k8s_memory_limit
        self._k8s_cpu_request = self.config.k8s_cpu_request
        self._k8s_memory_request = self.config.k8s_memory_request
        self._k8s_ttl = self.config.k8s_ttl_seconds
        self._network_policy = self.config.k8s_network_policy
        self._gpu_resource: Optional[str] = None  # 可由 setter 覆盖

        self._init_k8s_client()

    def _init_k8s_client(self) -> None:
        """初始化 K8s 客户端（in-cluster → kubeconfig 回退）。"""
        try:
            from kubernetes import client, config as k8s_config
            k8s_config.load_incluster_config()
            self._v1 = client.AppsV1Api()
            self._core_v1 = client.CoreV1Api()
            self._k8s_available = True
            logger.info("K8s sandbox: in-cluster config loaded")
        except Exception:
            try:
                from kubernetes import client, config as k8s_config
                k8s_config.load_kube_config()
                self._v1 = client.AppsV1Api()
                self._core_v1 = client.CoreV1Api()
                self._k8s_available = True
                logger.info("K8s sandbox: kubeconfig loaded")
            except ImportError:
                logger.warning("kubernetes package not installed — K8s sandbox unavailable")
            except Exception as e:
                logger.warning("K8s config load failed: %s — sandbox unavailable", e)

    @property
    def is_available(self) -> bool:
        return self._k8s_available

    # ── Pod 生命周期 ─────────────────────────────────

    def create_pod(self, pod_name: str = "", labels: dict = None) -> str:
        """创建临时沙箱 Pod。"""
        if not self._k8s_available:
            raise RuntimeError("K8s sandbox is not available")

        self._pod_name = pod_name or f"sandbox-{uuid.uuid4().hex[:12]}"
        labels = labels or {}
        labels.update({"app": "ai-sandbox", "pod-name": self._pod_name})

        from kubernetes import client

        container = client.V1Container(
            name="sandbox",
            image=self._k8s_image,
            command=["sleep", str(self._k8s_ttl)],
            resources=client.V1ResourceRequirements(
                requests={"cpu": self._k8s_cpu_request, "memory": self._k8s_memory_request},
                limits={"cpu": self._k8s_cpu_limit, "memory": self._k8s_memory_limit},
            ),
            security_context=client.V1SecurityContext(
                run_as_non_root=True,
                run_as_user=1000,
                allow_privilege_escalation=False,
                capabilities=client.V1Capabilities(drop=["ALL"]),
            ),
        )

        if self._gpu_resource:
            parts = self._gpu_resource.split(":")
            if len(parts) == 2:
                container.resources.limits[parts[0].strip()] = parts[1].strip()
                container.resources.requests[parts[0].strip()] = parts[1].strip()

        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Never",
            termination_grace_period_seconds=10,
        )

        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=self._pod_name,
                namespace=self._namespace,
                labels=labels,
            ),
            spec=pod_spec,
        )

        try:
            self._core_v1.create_namespaced_pod(namespace=self._namespace, body=pod)
            logger.info("K8s sandbox pod created: %s/%s", self._namespace, self._pod_name)
            return self._pod_name
        except client.ApiException as e:
            logger.error("K8s pod creation failed: %s", e)
            raise

    def delete_pod(self) -> bool:
        """删除沙箱 Pod。"""
        if not self._pod_name or not self._k8s_available:
            return False
        try:
            self._core_v1.delete_namespaced_pod(
                name=self._pod_name,
                namespace=self._namespace,
                body={"propagationPolicy": "Background"},
            )
            logger.info("K8s sandbox pod deleted: %s/%s", self._namespace, self._pod_name)
            return True
        except Exception as e:
            logger.warning("K8s pod deletion failed: %s", e)
            return False

    def get_pod_status(self) -> Optional[str]:
        """获取 Pod 当前 phase。"""
        if not self._k8s_available or not self._pod_name:
            return None
        try:
            pod = self._core_v1.read_namespaced_pod(
                name=self._pod_name, namespace=self._namespace
            )
            return pod.status.phase
        except Exception:
            return None

    # ── Sandbox ABC: 命令执行 ────────────────────────

    async def execute_command(self, command: str, cwd: str | None = None) -> CommandResult:
        """在 Pod 内执行命令。"""
        if not self._k8s_available or not self._pod_name:
            return CommandResult(
                exit_code=-1, stdout="", stderr="K8s sandbox not available",
            )

        # 注入工作目录
        target_cwd = cwd or self.CONTAINER_WORKSPACE
        full_command = f"cd {target_cwd} && {command}" if cwd else command

        start = time.perf_counter()

        def _exec_cmd() -> CommandResult:
            try:
                from kubernetes.stream import stream
                resp = stream(
                    self._core_v1.connect_get_namespaced_pod_exec,
                    name=self._pod_name,
                    namespace=self._namespace,
                    command=["/bin/sh", "-c", full_command],
                    stderr=True, stdin=False, stdout=True, tty=False,
                    _request_timeout=self.config.command_timeout,
                )
                return CommandResult(
                    exit_code=0,
                    stdout=resp or "",
                    stderr="",
                    truncated=False,
                    latency_ms=(time.perf_counter() - start) * 1000,
                )
            except Exception as e:
                return CommandResult(
                    exit_code=-1,
                    stdout="",
                    stderr=str(e),
                    truncated=False,
                    latency_ms=(time.perf_counter() - start) * 1000,
                )

        # 在线程池中运行（kubernetes stream 是同步的）
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _exec_cmd)

    # ── Sandbox ABC: 文件操作 (通过 kubectl exec) ─────

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        result = await self.execute_command(f"cat {_sh_quote(path)}")
        if result.exit_code != 0:
            raise FileNotFoundError(f"File not found: {path} ({result.stderr})")
        return result.stdout

    async def write_file(self, path: str, content: str, encoding: str = "utf-8") -> None:
        # 确保父目录存在后写入
        dirname = os.path.dirname(path)
        if dirname:
            await self.execute_command(f"mkdir -p {_sh_quote(dirname)}")
        # 用 Python 写文件，避免 shell 转义问题
        encoded = json.dumps(content)
        result = await self.execute_command(
            f"python3 -c \"import json,os;"
            f"os.makedirs(os.path.dirname({_sh_quote(path)}), exist_ok=True);"
            f"open({_sh_quote(path)},'w').write(json.loads('''{encoded}'''))\""
        )
        if result.exit_code != 0:
            raise OSError(f"Write failed: {result.stderr}")

    async def file_exists(self, path: str) -> bool:
        result = await self.execute_command(f"test -e {_sh_quote(path)}")
        return result.exit_code == 0

    async def list_dir(self, path: str, max_depth: int = 1) -> list[FileInfo]:
        results: list[FileInfo] = []
        if max_depth >= 1:
            # 解析 ls -la 输出: drwxr-xr-x 2 root root 4096 Jan 1 12:00 name
            result = await self.execute_command(
                f"ls -la --time-style=+%s {_sh_quote(path)} 2>/dev/null"
            )
            if result.exit_code != 0:
                return results
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("total"):
                    continue
                parts = line.split()
                if len(parts) < 7:
                    continue
                perms = parts[0]
                size = int(parts[4])
                mtime = float(parts[5])
                name = " ".join(parts[6:])
                if name in (".", ".."):
                    continue
                results.append(FileInfo(
                    path=os.path.join(path, name),
                    size=size,
                    is_dir=perms.startswith("d"),
                    modified_at=mtime,
                ))
        return results

    async def delete_file(self, path: str) -> None:
        await self.execute_command(f"rm -rf {_sh_quote(path)}")

    async def glob(self, path: str, pattern: str) -> tuple[list[str], bool]:
        result = await self.execute_command(
            f"find {_sh_quote(path)} -name {_sh_quote(pattern)} 2>/dev/null"
        )
        if result.exit_code != 0:
            return [], False
        matches = [m for m in result.stdout.strip().split("\n") if m]
        truncated = len(matches) > 1000
        if truncated:
            matches = matches[:1000]
        return matches, truncated

    async def grep(self, path: str, pattern: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        escaped = pattern.replace("'", "'\"'\"'")
        result = await self.execute_command(
            f"grep -rn '{escaped}' {_sh_quote(path)} 2>/dev/null"
        )
        if result.exit_code not in (0, 1):
            return results
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # 格式: path:lineno:content
            idx1 = line.find(":")
            if idx1 == -1:
                continue
            idx2 = line.find(":", idx1 + 1)
            if idx2 == -1:
                continue
            results.append({
                "path": line[:idx1],
                "line_number": int(line[idx1 + 1:idx2]),
                "line": line[idx2 + 1:],
            })
            if len(results) >= 500:
                results.append({"path": "...", "line_number": 0, "line": "[GREP TRUNCATED at 500 matches]"})
                break
        return results

    async def close(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self.delete_pod)


def _sh_quote(s: str) -> str:
    """Shell 安全引号包裹。"""
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ── 注册到 SandboxProvider ──────────────────────────

SandboxProvider.register("k8s", K8sSandbox)
logger.info("K8sSandbox registered in SandboxProvider")


__all__ = [
    "K8sSandboxConfig",
    "K8sSandbox",
]
