"""
Provider 核心测试 — 验证所有 provider 的 generate / generate_stream / health_check
"""
import pytest

from app.core.model_router import ModelRequest, ModelResponse, ModelCapability
from app.core.providers.base import BaseProvider, ProviderConfig


# ── Mock Provider（用于基类测试） ──

class _DummyProvider(BaseProvider):
    """最小实现，仅用于测试基类方法"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=f"[{self.config.name}] {request.prompt[:50]}",
            model_used=self.config.models[0] if self.config.models else self.config.name,
            provider=self.config.name,
            finish_reason="stop",
        )

    async def generate_stream(self, request: ModelRequest):
        for char in request.prompt:
            yield char


# ── Fixtures ──

@pytest.fixture
def text_request() -> ModelRequest:
    return ModelRequest(
        capability=ModelCapability.TEXT_GENERATION,
        prompt="Hello world",
    )


@pytest.fixture
def tool_request() -> ModelRequest:
    return ModelRequest(
        capability=ModelCapability.TOOL_USE,
        prompt="What is the weather in Tokyo?",
        tools=[{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }],
        tool_choice="auto",
    )


@pytest.fixture
def openai_config() -> ProviderConfig:
    return ProviderConfig(
        name="openai",
        display_name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="sk-test-key",
        models=["gpt-4o"],
        priority=90,
        strengths=["general_code", "ui_design"],
    )


# ── 测试：ProviderConfig ──

class TestProviderConfig:
    def test_defaults(self):
        cfg = ProviderConfig(name="test", display_name="Test", base_url="http://localhost")
        assert cfg.is_active is True
        assert cfg.priority == 50
        assert cfg.models == []
        assert cfg.api_key == ""
        assert cfg.strengths == []

    def test_custom(self, openai_config):
        assert openai_config.name == "openai"
        assert openai_config.priority == 90
        assert "gpt-4o" in openai_config.models


# ── 测试：BaseProvider ──

class TestBaseProvider:
    def test_init_from_config(self, openai_config):
        provider = _DummyProvider(openai_config)
        assert provider.name == "openai"
        assert provider.priority == 90
        assert provider.is_available is True

    def test_get_model_name_from_config(self, openai_config):
        provider = _DummyProvider(openai_config)
        name = provider._get_model_name(text_request)
        assert name == "gpt-4o"

    def test_get_model_name_from_extra_params(self, openai_config):
        provider = _DummyProvider(openai_config)
        req = ModelRequest(
            capability=ModelCapability.TEXT_GENERATION,
            prompt="hi",
            extra_params={"api_model_id": "gpt-4-turbo"},
        )
        name = provider._get_model_name(req)
        assert name == "gpt-4-turbo"

    def test_build_messages_simple(self, openai_config, text_request):
        provider = _DummyProvider(openai_config)
        msgs = provider._build_messages(text_request)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello world"

    def test_build_messages_with_system(self, openai_config):
        provider = _DummyProvider(openai_config)
        req = ModelRequest(
            capability=ModelCapability.TEXT_GENERATION,
            prompt="hi",
            system_prompt="You are helpful.",
        )
        msgs = provider._build_messages(req)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are helpful."

    def test_build_messages_with_history(self, openai_config):
        provider = _DummyProvider(openai_config)
        req = ModelRequest(
            capability=ModelCapability.TEXT_GENERATION,
            prompt="what about Paris?",
            history=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "Hello! How can I help?"},
            ],
        )
        msgs = provider._build_messages(req)
        assert len(msgs) == 3
        assert msgs[-1]["content"] == "what about Paris?"

    def test_build_messages_with_tool_history(self, openai_config):
        """验证 tool role 消息正确处理（多轮工具调用）"""
        provider = _DummyProvider(openai_config)
        req = ModelRequest(
            capability=ModelCapability.TOOL_USE,
            prompt="now check London",
            tools=[{"type": "function", "function": {"name": "weather"}}],
            history=[
                {"role": "user", "content": "Tokyo weather?"},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "call_1", "type": "function", "function": {"name": "weather", "arguments": '{"city":"Tokyo"}'}},
                ]},
                {"role": "tool", "content": "sunny 22°C", "tool_call_id": "call_1", "name": "weather"},
            ],
        )
        msgs = provider._build_messages(req)
        assert len(msgs) == 4
        # tool role 消息应保留 tool_call_id 和 name
        tool_msg = msgs[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_1"
        assert tool_msg["name"] == "weather"

    def test_build_headers_default(self):
        cfg = ProviderConfig(name="test", display_name="T", base_url="http://x", api_key="key123")
        provider = _DummyProvider(cfg)
        headers = provider._build_headers()
        assert headers["Authorization"] == "Bearer key123"
        assert headers["Content-Type"] == "application/json"

    async def test_generate_basic(self, openai_config, text_request):
        provider = _DummyProvider(openai_config)
        resp = await provider.generate(text_request)
        assert isinstance(resp, ModelResponse)
        assert resp.provider == "openai"

    async def test_generate_stream_char_by_char(self, openai_config, text_request):
        provider = _DummyProvider(openai_config)
        chars = []
        async for c in provider.generate_stream(text_request):
            chars.append(c)
        assert "".join(chars) == "Hello world"


# ── 测试：Provider 自动发现 ──

class TestProviderDiscovery:
    def test_all_providers_exported(self):
        """验证 __init__.py 导出了所有 provider 类"""
        from app.core.providers import (
            BaseProvider, ProviderConfig, OllamaProvider,
            OpenAIProvider, AnthropicProvider, DeepSeekProvider,
            QwenProvider, ZhipuProvider, LlamaCppProvider,
        )
        assert OllamaProvider is not None
        assert OpenAIProvider is not None
        assert AnthropicProvider is not None
        assert DeepSeekProvider is not None
        assert QwenProvider is not None
        assert ZhipuProvider is not None
        assert LlamaCppProvider is not None

    def test_providers_are_subclasses(self):
        """验证所有 provider 都是 BaseProvider 的子类"""
        from app.core.providers import (
            OllamaProvider, OpenAIProvider, AnthropicProvider,
            DeepSeekProvider, QwenProvider, ZhipuProvider, LlamaCppProvider,
        )
        for cls in [OllamaProvider, OpenAIProvider, AnthropicProvider,
                     DeepSeekProvider, QwenProvider, ZhipuProvider, LlamaCppProvider]:
            assert issubclass(cls, BaseProvider), f"{cls.__name__} is not a BaseProvider subclass"


# ── 测试：Ollama 头部定制 ──

class TestOllamaSpecific:
    def test_no_auth_header(self):
        from app.core.providers.ollama import OllamaProvider
        cfg = ProviderConfig(
            name="ollama", display_name="Ollama",
            base_url="http://localhost:11434/v1",
        )
        provider = OllamaProvider(cfg)
        headers = provider._build_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"


# ── 测试：Anthropic 工具转换 ──

class TestAnthropicToolConversion:
    def test_openai_to_anthropic_tools(self):
        from app.core.providers.anthropic import AnthropicProvider
        openai_tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]
        result = AnthropicProvider._to_anthropic_tools(openai_tools)
        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["description"] == "Get weather for a city"
        assert "input_schema" in result[0]
        assert result[0]["input_schema"]["type"] == "object"

    def test_tool_choice_auto(self):
        from app.core.providers.anthropic import AnthropicProvider
        result = AnthropicProvider._to_anthropic_tool_choice("auto")
        assert result == {"type": "auto"}

    def test_tool_choice_none(self):
        from app.core.providers.anthropic import AnthropicProvider
        result = AnthropicProvider._to_anthropic_tool_choice("none")
        assert result == {"type": "none"}

    def test_tool_choice_specific(self):
        from app.core.providers.anthropic import AnthropicProvider
        result = AnthropicProvider._to_anthropic_tool_choice(
            {"type": "function", "function": {"name": "get_weather"}}
        )
        assert result == {"type": "tool", "name": "get_weather"}
