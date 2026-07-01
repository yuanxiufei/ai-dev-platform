"""
第三方 API 统一网关（v2 — 委托给 ProviderRegistry）

职责：
1. 向后兼容：保留 ApiGateway 接口给已有代码使用
2. 内部委托给 app.core.providers.ProviderRegistry 做自动发现
3. 所有 Provider 实现在 providers/ 目录下独立管理

支持的提供商（自动发现）：
  - openai:     GPT-4o, GPT-4-turbo, GPT-3.5-turbo, o1, o3
  - anthropic:  Claude Sonnet 4, Claude 3 Opus
  - deepseek:   DeepSeek-V3, DeepSeek-Coder
  - replicate:  CogVideoX, Stable-Video-Diffusion
  - zhipu:      智谱 GLM-4 (国内可用)
  - qwen:       通义千问 (国内可用)
  - ollama:     Ollama 本地推理
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.model_router import ModelRequest, ModelResponse

logger = logging.getLogger("api_gateway")


class ApiGateway:
    """
    第三方 API 统一网关（v2 — 兼容层）

    内部委托给 ProviderRegistry，保持向后兼容的 API。
    """

    def __init__(self):
        from app.core.providers import get_provider_registry
        self._registry = get_provider_registry()

    @property
    def providers(self):
        return self._registry._providers

    def get_candidates(self) -> list:
        """获取所有可用的 API 候选模型"""
        return self._registry.get_candidates()

    def list_providers(self) -> list[dict]:
        """列出所有支持的提供商（含配置状态）"""
        return self._registry.list_all()

    def update_credential(self, name: str, api_key: str):
        """动态更新提供商密钥"""
        self._registry.update_key(name, api_key)

    async def generate(
        self, request: ModelRequest, provider: str | None = None
    ) -> ModelResponse:
        """调用指定提供商，不指定则自动选择"""
        if provider:
            p = self._registry.get_by_name(provider)
            if p:
                return await p.generate(request)
            raise ValueError(f"Provider '{provider}' not available")

        # 自动选择优先级最高的可用提供商
        for p in self._registry.get_candidates():
            try:
                return await p.generate(request)
            except Exception as e:
                logger.warning("Provider %s failed: %s", p.name, e)
                continue

        raise RuntimeError("No API provider available")

    async def close(self):
        """关闭所有 HTTP 客户端"""
        for p in self.providers:
            try:
                await p.close()
            except Exception:
                pass

    # ── 工厂方法 ────────────────────────────────────────

    @classmethod
    def auto_init(cls) -> "ApiGateway":
        """自动初始化（触发 ProviderRegistry 自动发现）"""
        from app.core.providers import init_provider_registry
        init_provider_registry()  # 确保注册表已初始化
        return cls()

    @classmethod
    async def from_database(cls, session) -> "ApiGateway":
        """从数据库加载加密的 API 密钥"""
        from app.models.system_models import ApiCredential

        gateway = cls.auto_init()

        credentials = session.exec(
            session.query(ApiCredential)
            .where(ApiCredential.is_active == True)
            .limit(50)  # 活跃凭证安全上限
        ).all()

        for cred in credentials:
            decrypted_key = cred.api_key_encrypted
            gateway.update_credential(cred.provider, decrypted_key)

        return gateway


# ── 全局网关单例 ────────────────────────────────────────

_global_gateway: ApiGateway | None = None


def init_api_gateway() -> ApiGateway:
    """初始化全局 API 网关"""
    global _global_gateway
    _global_gateway = ApiGateway.auto_init()
    return _global_gateway


def get_api_gateway() -> ApiGateway:
    """获取全局 API 网关"""
    if _global_gateway is None:
        return init_api_gateway()
    return _global_gateway
