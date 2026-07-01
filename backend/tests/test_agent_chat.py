"""
Agent 对话集成测试 — 使用 mock 模型验证 Agent 循环正确性
"""
import pytest

from app.core.model_router import ModelRequest, ModelResponse, ModelCapability, ICandidateModel
from app.core.agent.agent_config import AgentConfig
from app.core.agent.agent_runner import AgentRunner, AgentRunResult


# ── Mock 模型：模拟一个简单的 Agent 对话 ──

class _SimpleMockModel(ICandidateModel):
    """简单 mock：直接返回答案，不调用工具"""

    def __init__(self, answer="42"):
        super().__init__(name="mock-simple", provider="test", priority=100)
        self._answer = answer

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=self._answer,
            model_used="mock-simple",
            provider="test",
            finish_reason="stop",
        )

    async def generate_stream(self, request: ModelRequest):
        for char in self._answer:
            yield char


class _ToolCallModel(ICandidateModel):
    """模拟工具调用循环：第一轮返回 tool_calls，第二轮返回最终答案"""

    def __init__(self, final_answer="done"):
        super().__init__(name="mock-tool", provider="test", priority=100)
        self._call_count = 0
        self._final = final_answer

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self._call_count += 1
        if self._call_count == 1 and request.tools:
            # 第一轮：返回一个 tool call
            return ModelResponse(
                content="",
                model_used="mock-tool",
                provider="test",
                finish_reason="tool_calls",
                tool_calls=[{
                    "id": "call_mock_001",
                    "type": "function",
                    "function": {
                        "name": "mock_tool",
                        "arguments": '{"key":"value"}',
                    },
                }],
            )
        # 第二轮及以后：返回最终答案
        return ModelResponse(
            content=self._final,
            model_used="mock-tool",
            provider="test",
            finish_reason="stop",
        )

    async def generate_stream(self, request: ModelRequest):
        for char in self._final:
            yield char


# ── Mock Tool Registry & Executor ──

class _MockToolRegistry:
    def resolve_manifest(self, name):
        return {
            "name": "mock_tool",
            "description": "A mock tool for testing",
            "parameters": {"type": "object", "properties": {"key": {"type": "string"}}},
        }

    def get_schemas(self, names=None, categories=None):
        return [{
            "type": "function",
            "function": {
                "name": "mock_tool",
                "description": "Mock tool",
                "parameters": {"type": "object", "properties": {"key": {"type": "string"}}},
            },
        }]


# ── 测试 ──

class TestAgentBasic:
    async def test_simple_answer(self, monkeypatch):
        """无工具的简单对话"""
        config = AgentConfig(
            name="test-agent",
            instructions="You are a helpful assistant.",
            max_turns=1,
        )

        # Mock router
        monkeypatch.setattr(
            "app.core.agent.agent_runner.get_model_router",
            lambda: _FakeRouter(_SimpleMockModel(answer="Hello, world!")),
        )
        monkeypatch.setattr(
            "app.core.agent.agent_runner.get_tool_registry",
            lambda: _MockToolRegistry(),
        )

        runner = AgentRunner()
        result = await runner.run(config=config, user_message="hi")

        assert result.final_answer == "Hello, world!"
        assert result.turns == 1
        assert result.error == ""

    async def test_tool_call_loop(self, monkeypatch):
        """带工具调用的多轮对话"""
        config = AgentConfig(
            name="test-agent",
            instructions="You are a test agent.",
            max_turns=3,
            tools=["mock_tool"],
        )

        monkeypatch.setattr(
            "app.core.agent.agent_runner.get_model_router",
            lambda: _FakeRouter(_ToolCallModel(final_answer="weather is sunny")),
        )
        monkeypatch.setattr(
            "app.core.agent.agent_runner.get_tool_registry",
            lambda: _MockToolRegistry(),
        )

        # 还需要 mock executor
        monkeypatch.setattr(
            "app.core.tools.registry.get_tool_registry",
            lambda: _MockToolRegistry(),
        )

        runner = AgentRunner()
        result = await runner.run(config=config, user_message="What is the weather?")

        assert result.final_answer == "weather is sunny"
        # 至少 2 turns（tool call + final answer）
        assert result.turns >= 2

    async def test_streaming_events(self, monkeypatch):
        """流式 Agent 正确产出 token 事件"""
        from app.core.agent.agent_runner import StreamingAgentRunner

        config = AgentConfig(
            name="test-agent",
            instructions="Be helpful.",
            max_turns=1,
        )

        monkeypatch.setattr(
            "app.core.agent.agent_runner.get_model_router",
            lambda: _FakeRouter(_SimpleMockModel(answer="Hello")),
        )
        monkeypatch.setattr(
            "app.core.agent.agent_runner.get_tool_registry",
            lambda: _MockToolRegistry(),
        )

        runner = StreamingAgentRunner()
        events = []
        async for event in runner.run_stream(config=config, user_message="hi"):
            events.append(event)

        event_types = [e["type"] for e in events]
        assert "turn_start" in event_types
        assert "final_answer" in event_types or "token" in event_types


# ── 辅助 ──

class _FakeRouter:
    def __init__(self, model):
        self._model = model

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return await self._model.generate(request)

    async def generate_stream(self, request: ModelRequest):
        async for t in self._model.generate_stream(request):
            yield t

    @property
    def local_models(self):
        return [self._model]
