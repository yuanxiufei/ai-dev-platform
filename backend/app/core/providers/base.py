"""
Provider 基类 — 所有第三方 API 提供商的抽象基类

设计原则：
1. 每个 Provider 是独立的模块文件，放在 providers/ 目录
2. 自动发现：providers/__init__.py 扫描目录自动注册
3. Provider 需实现 generate() 方法（同步/异步）
4. 通过 ProviderConfig 配置 API 端点和密钥
5. 统一的健康检查接口
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.model_router import (
    ICandidateModel,
    ModelRequest,
    ModelResponse,
)


@dataclass
class ProviderConfig:
    """单个 API 提供商的配置"""
    name: str                          # 内部标识: openai, anthropic, ...
    display_name: str                  # 展示名称
    base_url: str                      # API 基础 URL
    api_key: str = ""                  # API 密钥
    models: list[str] = field(default_factory=list)  # 支持的模型列表
    is_active: bool = True
    priority: int = 50                 # 优先级（越高越优先）
    strengths: list[str] = field(default_factory=list)  # 擅长方向
    extra_config: dict[str, Any] = field(default_factory=dict)  # 额外配置


class BaseProvider(ICandidateModel):
    """
    API 提供商基类

    子类需要重写：
    - generate(): 核心推理逻辑
    - _build_headers(): 构建 HTTP 请求头（可选）
    - health_check(): 健康检查（可选）
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(
            name=config.name,
            provider=config.name,
            priority=config.priority,
            strengths=config.strengths,
        )
        self.config = config
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """懒加载 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> dict[str, str]:
        """构建默认请求头（子类可重写）"""
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        """验证 API 密钥是否有效"""
        self.is_available = bool(self.config.api_key)
        return self.is_available

    def _build_messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        """
        构建标准消息列表（大多数 LLM API 通用）

        支持 tool role 消息（通过 history 传入）。
        当 request 包含 tools 时，会自动适应多轮工具调用场景。
        """
        msgs: list[dict[str, Any]] = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})
        if request.history:
            for msg in request.history:
                # 保留原始结构（含 tool_call_id / tool_calls / name 等字段）
                entry: dict[str, Any] = {"role": msg.get("role", "user")}
                if "content" in msg:
                    entry["content"] = msg["content"]
                # 透传工具相关字段
                if "tool_call_id" in msg:
                    entry["tool_call_id"] = msg["tool_call_id"]
                if "tool_calls" in msg:
                    entry["tool_calls"] = msg["tool_calls"]
                if "name" in msg:
                    entry["name"] = msg["name"]
                msgs.append(entry)
        msgs.append({"role": "user", "content": request.prompt})
        return msgs

    def _parse_tool_calls(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """
        从 API 响应中提取 tool_calls（OpenAI 格式）

        子类可重写以适配 Anthropic 等其他格式。
        """
        return []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """子类实现具体推理逻辑"""
        raise NotImplementedError(f"{self.__class__.__name__}.generate() not implemented")

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
