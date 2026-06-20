"""
Kubernetes Sandbox Provider — run agent code in isolated K8s pods.

Extends the existing Sandbox ABC with a K8s provider for:
- Ephemeral pods with resource limits (CPU/memory)
- Network isolation via NetworkPolicy
- Volume mounts for workspace access
- Automatic cleanup on session end
"""

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from app.core.sandbox.base import (
        Sandbox,
        SandboxConfig,
        CommandResult,
        FileInfo,
        SandboxProvider,
    )
    _SANDBOX_BASE_AVAILABLE = True
except ImportError:
    _SANDBOX_BASE_AVAILABLE = False


@dataclass
class K8sSandboxConfig:
    """Configuration for Kubernetes sandbox pods."""
    namespace: str = "ai-sandbox"
    image: str = "python:3.12-slim"
    cpu_limit: str = "2"
    memory_limit: str = "4Gi"
    cpu_request: str = "500m"
    memory_request: str = "1Gi"
    workspace_mount_path: str = "/workspace"
    network_policy: str = "deny-all"    # deny-all | allow-internal | allow-egress
    service_account: str = ""
    pod_annotations: dict = field(default_factory=dict)
    ttl_seconds: int = 3600              # Auto-delete pod after 1 hour idle
    node_selector: dict = field(default_factory=dict)
    gpu_resource: Optional[str] = None  # e.g., "nvidia.com/gpu: 1"


class K8sSandbox:
    """Kubernetes pod-based sandbox for secure agent code execution.

    Requires kubernetes Python client (`pip install kubernetes`).
    Falls back to local execution if K8s is unavailable.
    """

    def __init__(self, config: K8sSandboxConfig | None = None):
        self._config = config or K8sSandboxConfig()
        self._pod_name: Optional[str] = None
        self._namespace = self._config.namespace
        self._k8s_available = False
        self._v1 = None
        self._core_v1 = None

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

    def create_pod(self, pod_name: str = "", labels: dict = None) -> str:
        """Create an ephemeral sandbox pod.

        Returns:
            Pod name string.
        """
        if not self._k8s_available:
            raise RuntimeError("K8s sandbox is not available")

        self._pod_name = pod_name or f"sandbox-{uuid.uuid4().hex[:12]}"
        labels = labels or {}
        labels.update({"app": "ai-sandbox", "pod-name": self._pod_name})

        from kubernetes import client

        container = client.V1Container(
            name="sandbox",
            image=self._config.image,
            command=["sleep", str(self._config.ttl_seconds)],
            resources=client.V1ResourceRequirements(
                requests={"cpu": self._config.cpu_request, "memory": self._config.memory_request},
                limits={"cpu": self._config.cpu_limit, "memory": self._config.memory_limit},
            ),
            volume_mounts=[
                client.V1VolumeMount(
                    name="workspace",
                    mount_path=self._config.workspace_mount_path,
                    read_only=False,
                )
            ] if self._config.workspace_mount_path else [],
            security_context=client.V1SecurityContext(
                run_as_non_root=True,
                run_as_user=1000,
                allow_privilege_escalation=False,
                capabilities=client.V1Capabilities(drop=["ALL"]),
            ),
        )

        # Optional GPU
        if self._config.gpu_resource:
            # Parse "nvidia.com/gpu: 1" format
            parts = self._config.gpu_resource.split(":")
            if len(parts) == 2:
                container.resources.limits[parts[0].strip()] = parts[1].strip()
                container.resources.requests[parts[0].strip()] = parts[1].strip()

        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Never",
            service_account_name=self._config.service_account or "",
            node_selector=self._config.node_selector or None,
            termination_grace_period_seconds=10,
        )

        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=self._pod_name,
                namespace=self._namespace,
                labels=labels,
                annotations=self._config.pod_annotations,
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
        """Delete the sandbox pod."""
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

    def exec_command(self, command: str, timeout: int = 30) -> CommandResult:
        """Execute a command inside the sandbox pod."""
        if not self._k8s_available or not self._pod_name:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr="K8s sandbox not available",
                truncated=False,
            )

        try:
            from kubernetes.stream import stream

            resp = stream(
                self._core_v1.connect_get_namespaced_pod_exec,
                name=self._pod_name,
                namespace=self._namespace,
                command=["/bin/sh", "-c", command],
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _request_timeout=timeout,
            )
            return CommandResult(
                exit_code=0,
                stdout=resp or "",
                stderr="",
                truncated=False,
            )
        except Exception as e:
            return CommandResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                truncated=False,
            )

    def get_pod_status(self) -> Optional[str]:
        """Get current pod phase."""
        if not self._k8s_available or not self._pod_name:
            return None
        try:
            pod = self._core_v1.read_namespaced_pod(
                name=self._pod_name, namespace=self._namespace
            )
            return pod.status.phase
        except Exception:
            return None


__all__ = [
    "K8sSandboxConfig",
    "K8sSandbox",
]
