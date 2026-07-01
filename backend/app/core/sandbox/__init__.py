"""
Sandbox 沙箱执行环境

借鉴 DeerFlow sandbox/ + Trae Agent docker_tool_executor 设计：
- Sandbox ABC：统一的沙箱接口抽象
- LocalSandbox：宿主机执行（路径白名单 + 安全策略）
- DockerSandbox：Docker 容器隔离（透明路径翻译）
- K8sSandbox：Kubernetes Pod 隔离 (Session 09)

所有文件/Shell 工具调用 MUST 经过 Sandbox 层，确保安全隔离。
"""

from app.core.sandbox.base import Sandbox, SandboxConfig, SandboxProvider  # noqa: F401
from app.core.sandbox.local import LocalSandbox  # noqa: F401
from app.core.sandbox.docker import DockerSandbox  # noqa: F401

# 全局单例
_sandbox_instance: "Sandbox | None" = None


def get_sandbox() -> "Sandbox":
    """获取全局沙箱实例（默认 LocalSandbox）"""
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = LocalSandbox()
    return _sandbox_instance


def init_sandbox(config: "SandboxConfig | None" = None) -> "Sandbox":
    """初始化沙箱实例

    支持类型: local | docker | k8s (Session 09)
    """
    global _sandbox_instance
    from app.core.config import settings

    if config is None:
        config = SandboxConfig(
            type=settings.SANDBOX_TYPE if hasattr(settings, "SANDBOX_TYPE") else "local",
            workspace_dir=settings.MODELS_DIR,
        )

    sandbox_type = config.type.lower()
    if sandbox_type == "docker":
        _sandbox_instance = DockerSandbox(config)
    elif sandbox_type == "k8s":
        # Session 09: K8s 沙箱 — 需要 kubernetes 客户端
        from app.core.sandbox.k8s import K8sSandbox  # noqa: F811
        k8s_sandbox = K8sSandbox(config)
        if k8s_sandbox.is_available:
            _sandbox_instance = k8s_sandbox
        else:
            import logging
            logging.getLogger("sandbox").warning(
                "K8s sandbox unavailable — falling back to LocalSandbox"
            )
            _sandbox_instance = LocalSandbox(config)
    else:
        _sandbox_instance = LocalSandbox(config)

    import logging
    logger = logging.getLogger("sandbox")
    logger.info("Sandbox initialized: type=%s workspace=%s", config.type, config.workspace_dir)

    return _sandbox_instance
