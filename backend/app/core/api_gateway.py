"""
第三方 API 统一网关

职责：
1. 统一管理所有第三方 AI API（OpenAI / Anthropic / Azure / Replicate / DeepSeek）
2. 从数据库读取加密的 API 密钥
3. 自动选择可用提供商（按优先级）
4. 对上层 ModelRouter 暴露统一的 generate() 接口

支持的提供商（可扩展）：
  - openai:     GPT-4o, GPT-4-turbo, GPT-3.5-turbo, o1, o3 等
  - anthropic:  Claude 3.5 Sonnet, Claude 3 Opus 等
  - azure:      Azure OpenAI Service
  - replicate:  CogVideoX, SDXL, Stable-Video-Diffusion 等
  - deepseek:   DeepSeek-V3, DeepSeek-R1 等
  - groq:       Llama 3 70B, Mixtral 等高速推理
  - zhipu:      智谱 GLM-4 (国内可用)
  - qwen:       通义千问 (国内可用)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.model_router import (
    ICandidateModel,
    ModelCapability,
    ModelRequest,
    ModelResponse,
)

logger = logging.getLogger("api_gateway")


# ── 提供商配置 ─────────────────────────────────────────────

@dataclass
class ProviderConfig:
    """单个 API 提供商的配置"""
    name: str                    # 内部标识：openai, anthropic, ...
    display_name: str            # 展示名称
    base_url: str                # API 基础URL
    api_key: str = ""            # 解密后的 API 密钥
    models: list[str] = field(default_factory=list)  # 该提供商支持的模型列表
    is_active: bool = True
    priority: int = 50           # 提供商优先级（越高越优先）
    strengths: list[str] = field(default_factory=list)  # 擅长方向


# ── 各提供商的适配器 ──────────────────────────────────────────

class BaseApiProvider(ICandidateModel):
    """API 提供商基类"""

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
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers=self._build_headers(),
            )
        return self._client

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        """验证 API 密钥是否有效"""
        self.is_available = bool(self.config.api_key)
        return self.is_available

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class OpenAIProvider(BaseApiProvider):
    """OpenAI API 适配"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self.config.models[0] if self.config.models else "gpt-4o"
        messages = self._build_messages(request)

        resp = await self.client.post("/v1/chat/completions", json={
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        })
        resp.raise_for_status()
        data = resp.json()

        return ModelResponse(
            content=data["choices"][0]["message"]["content"],
            model_used=data.get("model", model_name),
            provider="openai",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
        )

    def _build_messages(self, request: ModelRequest) -> list[dict]:
        msgs: list[dict] = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})

        # 处理图片输入 (Vision)
        if request.images and request.capability == ModelCapability.VISION_LANGUAGE:
            content: list[dict] = [{"type": "text", "text": request.prompt}]
            for img in request.images:
                import base64
                b64 = base64.b64encode(img).decode()
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64}",
                        "detail": "high",
                    },
                })
            msgs.append({"role": "user", "content": content})
        else:
            if request.history:
                msgs.extend(request.history)
            msgs.append({"role": "user", "content": request.prompt})

        return msgs


class AnthropicProvider(BaseApiProvider):
    """Anthropic Claude API 适配"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self.config.models[0] if self.config.models else "claude-sonnet-4-20250514"

        resp = await self.client.post("/v1/messages", json={
            "model": model_name,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system_prompt if request.system_prompt else None,
            "messages": [{"role": "user", "content": request.prompt}],
        })
        resp.raise_for_status()
        data = resp.json()

        return ModelResponse(
            content=data["content"][0]["text"],
            model_used=data.get("model", model_name),
            provider="anthropic",
            tokens_used=data.get("usage", {}).get("input_tokens", 0)
            + data.get("usage", {}).get("output_tokens", 0),
            finish_reason=data.get("stop_reason", "stop"),
        )

    def _build_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.config.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }


class DeepSeekProvider(BaseApiProvider):
    """DeepSeek API 适配 (兼容 OpenAI 格式)"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self.config.models[0] if self.config.models else "deepseek-chat"

        messages: list[dict] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        if request.history:
            messages.extend(request.history)
        messages.append({"role": "user", "content": request.prompt})

        resp = await self.client.post("/v1/chat/completions", json={
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        })
        resp.raise_for_status()
        data = resp.json()

        return ModelResponse(
            content=data["choices"][0]["message"]["content"],
            model_used=data.get("model", model_name),
            provider="deepseek",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
        )


class ReplicateProvider(BaseApiProvider):
    """Replicate API 适配 — 视频/图片生成"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.capability == ModelCapability.VIDEO_GENERATION:
            return await self._generate_video(request)
        return await self._generate_text(request)

    async def _generate_video(self, request: ModelRequest) -> ModelResponse:
        model_ref = request.extra_params.get(
            "replicate_model", "lucataco/cogvideox-5b:xxx"
        )

        resp = await self.client.post("/v1/predictions", json={
            "version": model_ref,
            "input": {
                "prompt": request.prompt,
                "num_frames": request.extra_params.get("num_frames", 49),
                "fps": request.extra_params.get("fps", 8),
                "num_inference_steps": request.extra_params.get("num_inference_steps", 50),
            },
        })
        resp.raise_for_status()
        data = resp.json()

        # Replicate 是异步的，返回 prediction_id 用于轮询
        return ModelResponse(
            content=json.dumps({
                "type": "video_generation",
                "prediction_id": data.get("id"),
                "status": data.get("status"),
                "output_url": data.get("output"),
            }),
            model_used=model_ref,
            provider="replicate",
            finish_reason="pending" if data.get("status") == "processing" else "stop",
            metadata={"prediction_id": data.get("id")},
        )

    async def _generate_text(self, request: ModelRequest) -> ModelResponse:
        model_ref = request.extra_params.get("replicate_model", "meta/llama-3-70b-instruct")
        resp = await self.client.post("/v1/predictions", json={
            "version": model_ref,
            "input": {
                "prompt": request.prompt,
                "system_prompt": request.system_prompt or "",
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
        })
        resp.raise_for_status()
        data = resp.json()

        return ModelResponse(
            content="".join(data.get("output", [])),
            model_used=model_ref,
            provider="replicate",
            finish_reason="stop",
        )

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }


# ── 提供商注册表 ──────────────────────────────────────────

def _default_providers_config() -> list[ProviderConfig]:
    """默认提供商配置（密钥为空，需用户配置）"""
    import os
    return [
        ProviderConfig(
            name="openai",
            display_name="OpenAI",
            base_url="https://api.openai.com",
            models=["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            priority=80,
            strengths=["ui_design", "frontend_code", "general_code"],
        ),
        ProviderConfig(
            name="anthropic",
            display_name="Anthropic Claude",
            base_url="https://api.anthropic.com",
            models=["claude-sonnet-4-20250514", "claude-3-opus-20240229"],
            priority=75,
            strengths=["ui_design", "frontend_code", "general_code"],
        ),
        ProviderConfig(
            name="deepseek",
            display_name="DeepSeek",
            base_url="https://api.deepseek.com",
            models=["deepseek-chat", "deepseek-coder"],
            priority=70,
            strengths=["backend_code", "general_code"],
        ),
        ProviderConfig(
            name="azure",
            display_name="Azure OpenAI",
            base_url="https://{resource}.openai.azure.com",
            models=["gpt-4o"],
            priority=65,
            strengths=["general_code"],
        ),
        ProviderConfig(
            name="ollama",
            display_name="Ollama (本地推理)",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            models=["hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_M"],
            priority=60,
            api_key="ollama-local-no-key",  # Ollama 本地运行无需密钥
            strengths=["ui_design", "frontend_code", "general_code"],
        ),
        ProviderConfig(
            name="replicate",
            display_name="Replicate",
            base_url="https://api.replicate.com",
            models=["cogvideox-5b", "stable-video-diffusion"],
            priority=60,
            strengths=["short_video"],
        ),
        ProviderConfig(
            name="zhipu",
            display_name="智谱 GLM-4",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            models=["glm-4-plus", "glm-4v"],
            priority=55,
            strengths=["general_code"],
        ),
        ProviderConfig(
            name="qwen",
            display_name="通义千问",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            models=["qwen-max", "qwen-plus"],
            priority=55,
            strengths=["general_code"],
        ),
    ]


def _provider_map(config: ProviderConfig) -> BaseApiProvider | None:
    """根据配置创建对应的 Provider 实例"""
    if not config.api_key:
        logger.debug(f"Provider {config.name} has no API key, skipping")
        return None

    provider_cls = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "deepseek": DeepSeekProvider,
        "azure": OpenAIProvider,       # Azure 兼容 OpenAI 格式
        "replicate": ReplicateProvider,
        "zhipu": OpenAIProvider,       # 智谱兼容 OpenAI SDK
        "qwen": OpenAIProvider,        # 通义千问兼容 OpenAI SDK
        "ollama": OpenAIProvider,      # Ollama 兼容 OpenAI SDK
    }.get(config.name)

    if provider_cls is None:
        logger.warning(f"Unknown provider: {config.name}")
        return None

    try:
        return provider_cls(config)
    except Exception as e:
        logger.error(f"Failed to init provider {config.name}: {e}")
        return None


# ── ApiGateway 核心 ───────────────────────────────────────

class ApiGateway:
    """
    第三方 API 统一网关

    使用方式：
      gateway = ApiGateway.auto_init()          # 从 DB 加载密钥
      response = await gateway.generate(request, "openai")
      # 或让 ModelRouter 自动选择
      candidates = gateway.get_candidates()
    """

    def __init__(self, configs: list[ProviderConfig] | None = None):
        configs = configs or _default_providers_config()
        self._configs = configs
        self._providers: list[BaseApiProvider] = []
        self._init_providers()

    def _init_providers(self):
        """初始化所有已配置密钥的提供商"""
        for cfg in self._configs:
            provider = _provider_map(cfg)
            if provider:
                self._providers.append(provider)

        # 按优先级排序
        self._providers.sort(key=lambda p: p.priority, reverse=True)
        logger.info(
            "ApiGateway initialized with %d providers: %s",
            len(self._providers),
            [p.name for p in self._providers],
        )

    def update_credential(self, provider: str, api_key: str):
        """动态更新提供商密钥"""
        for cfg in self._configs:
            if cfg.name == provider:
                cfg.api_key = api_key
                break
        # 重建 providers 列表
        self._init_providers()

    def get_candidates(self) -> list[BaseApiProvider]:
        """获取所有可用的 API 候选模型"""
        return [p for p in self._providers if p.is_available]

    def list_providers(self) -> list[dict]:
        """列出所有支持的提供商（含配置状态）"""
        return [
            {
                "name": cfg.name,
                "display_name": cfg.display_name,
                "models": cfg.models,
                "is_configured": bool(cfg.api_key),
                "is_active": cfg.is_active,
                "priority": cfg.priority,
            }
            for cfg in self._configs
        ]

    async def generate(
        self, request: ModelRequest, provider: str | None = None
    ) -> ModelResponse:
        """调用指定提供商，不指定则自动选择"""
        if provider:
            for p in self._providers:
                if p.name == provider:
                    return await p.generate(request)
            raise ValueError(f"Provider '{provider}' not available")

        # 自动选择优先级最高的可用提供商
        for p in self._providers:
            try:
                return await p.generate(request)
            except Exception as e:
                logger.warning(f"Provider {p.name} failed: {e}")
                continue

        raise RuntimeError("No API provider available")

    async def close(self):
        """关闭所有 HTTP 客户端"""
        for p in self._providers:
            await p.close()

    # ── 工厂方法 ────────────────────────────────────────

    @classmethod
    def auto_init(cls) -> "ApiGateway":
        """
        自动初始化：从环境变量或数据库加载 API 密钥

        优先级：
          1. 环境变量（OPENAI_API_KEY, ANTHROPIC_API_KEY, ...）
          2. 数据库 api_credentials 表（需 SQLModel Session）
        """
        configs = _default_providers_config()

        # 从环境变量注入密钥
        env_keys = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "azure": "AZURE_OPENAI_API_KEY",
            "replicate": "REPLICATE_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "qwen": "QWEN_API_KEY",
            "ollama": "OLLAMA_API_KEY",  # Ollama 本地运行用占位值，无需真实密钥
        }

        import os
        for cfg in configs:
            env_var = env_keys.get(cfg.name)
            if env_var:
                cfg.api_key = os.getenv(env_var, "")

        return cls(configs)

    @classmethod
    async def from_database(cls, session) -> "ApiGateway":
        """从数据库加载加密的 API 密钥"""
        from app.models.system_models import ApiCredential

        gateway = cls.auto_init()

        # 查询所有用户的活跃凭证
        credentials = session.exec(
            session.query(ApiCredential).where(ApiCredential.is_active == True)
        ).all()

        for cred in credentials:
            # TODO: 解密 api_key_encrypted (AES-256 解密)
            decrypted_key = cred.api_key_encrypted  # 简化：直接使用（实际需解密）
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
